"""Testes da abertura do painel pelo atalho do aplicativo."""
from argparse import Namespace
from unittest.mock import patch

from helpers import TempEnv
from organizalocal import cli


class TestCLI(TempEnv):
    def test_abre_pareamento_se_sessao_sumiu_ou_pertence_a_outro_servico(self):
        for session in ({}, {"pid": 21, "port": cli.port(), "token": "antigo"}):
            with self.subTest(session_pid=session.get("pid")):
                with (
                    patch.object(cli, "running", return_value={"pid": 22}),
                    patch.object(cli, "session", return_value=session),
                    patch.object(cli, "webbrowser") as browser,
                ):
                    self.assertEqual(cli.cmd_open(Namespace(local=False)), 0)
                    browser.open.assert_called_once_with(f"http://127.0.0.1:{cli.port()}/")

    def test_inicia_servico_e_abre_painel_autenticado(self):
        info = self.app.security.start_session(cli.port())
        with (
            patch.object(cli, "running", side_effect=[None, {"pid": info["pid"]}]),
            patch.object(cli, "spawn_background") as spawn,
            patch.object(cli, "site_reachable", return_value=True),
            patch.object(cli, "webbrowser") as browser,
        ):
            self.assertEqual(cli.cmd_open(Namespace(local=False)), 0)
            spawn.assert_called_once_with()
            site = self.app.store.config["site_url"]
            browser.open.assert_called_once_with(
                f"{site}/#token={info['token']}&api=http://127.0.0.1:{cli.port()}"
            )

    def test_reporta_falha_do_navegador(self):
        with (
            patch.object(cli, "running", return_value={"pid": 22}),
            patch.object(cli, "webbrowser") as browser,
            patch.object(cli, "launch_error", return_value=1) as error,
        ):
            browser.open.return_value = False
            self.assertEqual(cli.cmd_open(Namespace(local=False)), 1)
            error.assert_called_once()

    def test_stop_aguarda_limpeza_da_sessao_quando_conexao_expira(self):
        with (
            patch.object(cli, "running", return_value={"pid": 22}),
            patch.object(cli, "action") as action,
            patch.object(cli, "session", side_effect=[{"pid": 22}, {}]),
            patch.object(cli.socket, "create_connection", side_effect=TimeoutError) as connect,
            patch.object(cli.time, "sleep"),
        ):
            self.assertEqual(cli.cmd_stop(None), 0)
            action.assert_called_once_with("shutdown")
            self.assertEqual(connect.call_count, 2)
