"""Testes da API HTTP local: token, origens (CORS), pareamento e interface estática."""
import hashlib
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from helpers import TempEnv
from organizalocal.server import make_server


class TestServidor(TempEnv):
    def setUp(self):
        super().setUp()
        self.app.store.config["site_url"] = "https://organiza-local.vercel.app"
        self.server = make_server(self.app, 0)                  # porta livre escolhida pelo SO
        self.port = self.server.server_address[1]
        self.app.port = self.port
        self.session = self.app.security.start_session(self.port)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def request(self, path, body=None, token=None, origin=None, method=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        if origin:
            req.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, dict(e.headers), e.read()

    def test_ping_publico(self):
        status, _, body = self.request("/api/ping")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])

    def test_acao_sem_token_e_negada(self):
        self.assertEqual(self.request("/api/action/state", {})[0], 401)

    def test_acao_com_token(self):
        status, _, body = self.request("/api/action/state", {}, token=self.session["token"])
        self.assertEqual(status, 200)
        self.assertIn("rules", json.loads(body)["result"])

    def test_origem_desconhecida_bloqueada(self):
        status, _, _ = self.request("/api/action/state", {}, token=self.session["token"], origin="https://site-malicioso.com")
        self.assertEqual(status, 403)

    def test_site_da_vercel_autorizado_com_cors_e_rede_privada(self):
        origin = "https://organiza-local.vercel.app"
        status, headers, _ = self.request("/api/action/state", None, origin=origin, method="OPTIONS")
        self.assertEqual(status, 204)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), origin)
        self.assertEqual(headers.get("Access-Control-Allow-Private-Network"), "true")
        status, headers, _ = self.request("/api/action/state", {}, token=self.session["token"], origin=origin)
        self.assertEqual(status, 200)

    def test_troca_para_painel_local_confirma_salvamento_a_origem_anterior(self):
        origin = "https://organiza-local.vercel.app"
        token = self.session["token"]
        status, headers, body = self.request(
            "/api/action/config_update", {"changes": {"site_url": ""}}, token=token, origin=origin,
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), origin)
        self.assertEqual(json.loads(body)["result"]["site_url"], "")
        status, headers, _ = self.request("/api/action/state", {}, token=token, origin=origin)
        self.assertEqual(status, 403)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(self.request("/api/action/state", {}, token=token)[0], 200)

    def test_troca_para_site_publicado_autoriza_nova_origem(self):
        local = f"http://127.0.0.1:{self.port}"
        site = "https://novo-painel.vercel.app"
        token = self.session["token"]
        self.assertEqual(self.request(
            "/api/action/config_update", {"changes": {"site_url": site}}, token=token, origin=local,
        )[0], 200)
        status, headers, _ = self.request("/api/action/state", {}, token=token, origin=site)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), site)

    def test_pareamento_por_codigo(self):
        self.assertEqual(self.request("/api/pair", {"code": "000000"})[0], 403)
        status, _, body = self.request("/api/pair", {"code": self.session["code"]})
        self.assertEqual(status, 200)
        token = json.loads(body)["token"]
        self.assertEqual(self.request("/api/action/state", {}, token=token)[0], 200)

    def test_abre_terminal_para_parear_com_codigo_atualizado(self):
        path = "/api/pair/show-code"
        origin = "https://organiza-local.vercel.app"
        security = self.app.security
        security.code_created = time.monotonic() - 1801
        with patch("organizalocal.server.open_pairing_terminal") as terminal:
            status, _, body = self.request(path, {}, origin=origin)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body), {"ok": True})
            self.assertEqual(self.request(path, {}, origin=origin)[0], 429)
            terminal.assert_called_once_with(self.app.store.root)

        session = self.app.store.read(self.app.store.session_path, {})
        self.assertGreater(security.code_created, time.monotonic() - 1800)
        self.assertEqual(self.request("/api/pair", {"code": session["code"]})[0], 200)
        self.assertEqual(self.request("/api/action/state", {}, token=self.session["token"])[0], 200)

    def test_terminal_rejeita_origem_ausente_e_nao_autorizada(self):
        path = "/api/pair/show-code"
        with patch("organizalocal.server.open_pairing_terminal") as terminal:
            self.assertEqual(self.request(path, {})[0], 403)
            self.assertEqual(self.request(path, {}, origin="https://site-malicioso.com")[0], 403)
            terminal.assert_not_called()

    def test_revogar_invalida_tokens(self):
        token = self.session["token"]
        self.request("/api/action/pairing_revoke", {}, token=token)
        self.assertEqual(self.request("/api/action/state", {}, token=token)[0], 401)

    def test_interface_estatica_e_bloqueio_de_caminho(self):
        status, headers, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"OrganizaLocal", body)
        self.assertEqual(self.request("/../src/organizalocal/server.py")[0], 404)

    def test_download_dos_instaladores_pelo_painel_local(self):
        installers = Path(__file__).resolve().parents[1] / "Instaladores"
        status, _, manifest = self.request("/downloads/SHA256SUMS.txt")
        self.assertEqual(status, 200)
        self.assertEqual(manifest, (installers / "SHA256SUMS.txt").read_bytes())
        for line in manifest.decode("ascii").splitlines():
            checksum, filename = line.split()
            with self.subTest(filename=filename):
                status, _, body = self.request(f"/downloads/{filename}")
                self.assertEqual(status, 200)
                self.assertEqual(hashlib.sha256(body).hexdigest(), checksum)

    def test_permissao_do_perfil(self):
        self.app.security.save_profile("Visitante", ["read"])
        self.app.security.switch_profile("Visitante")
        status, _, body = self.request("/api/action/organize", {}, token=self.session["token"])
        self.assertEqual(status, 403)
        self.assertIn("permissão", json.loads(body)["error"])

    def test_sessao_gravada_com_permissao_restrita(self):
        import os
        import stat
        if os.name != "nt":
            mode = stat.S_IMODE(self.app.store.session_path.stat().st_mode)
            self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
