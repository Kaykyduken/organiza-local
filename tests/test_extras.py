"""Testes das funções extras: PDF, compactados, segurança, agendador, configurações."""
import io
import json
import tarfile
import unittest
import zipfile
from datetime import datetime, timedelta

from helpers import TempEnv, make_file
from organizalocal import archives, sysinfo
from organizalocal.reports import write_pdf


class TestRelatorios(TempEnv):
    def test_pdf_valido(self):
        path = self.root / "teste.pdf"
        write_pdf(path, "Relatório de teste", [f"linha {i} com acentuação" for i in range(150)])
        data = path.read_bytes()
        self.assertTrue(data.startswith(b"%PDF-1.4"))
        self.assertIn(b"/Count 3", data)                          # 150 linhas -> 3 páginas
        self.assertTrue(data.rstrip().endswith(b"%%EOF"))

    def test_relatorio_diario(self):
        self.app.store.event("move", "ok", source="/a", destination="/b")
        result = self.app.reports.daily_pdf()
        self.assertGreaterEqual(result["events"], 1)

    def test_estatisticas(self):
        self.app.store.event("move", "ok", source="/a/x.pdf", destination="/b/x.pdf", bytes=10, rule_name="PDF")
        stats = self.app.reports.stats()
        self.assertEqual(stats["moves"], 1)
        self.assertEqual(stats["by_rule"], {"PDF": 1})

    def test_vencimentos_e_limites(self):
        soon = (datetime.now() + timedelta(days=3)).date().isoformat()
        self.app.save_list("due_dates", [{"description": "CNH", "due": soon}])
        self.assertEqual(self.app.reports.due_documents()[0]["days_remaining"], 3)
        make_file(self.downloads / "grande.bin", b"x" * 2000)
        self.app.save_list("limits", [{"path": str(self.downloads), "max_bytes": 1000}])
        self.assertEqual(self.app.reports.check_limits()[0]["severity"], "excedido")


class TestCompactados(TempEnv):
    def test_zip_inspecionar_e_extrair(self):
        z = self.downloads / "pacote.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("docs/a.txt", "a")
            f.writestr("b.pdf", "%PDF")
        info = archives.inspect(self.org, str(z))
        self.assertEqual(info["count"], 2)
        out = archives.extract(self.org, str(z), str(self.home / "extraido"))
        self.assertEqual(out["extracted"], 2)
        self.assertTrue((self.home / "extraido" / "docs" / "a.txt").exists())

    def test_zip_com_caminho_perigoso_e_bloqueado(self):
        z = self.downloads / "mal.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("../../fora.txt", "x")
        with self.assertRaises(ValueError):
            archives.extract(self.org, str(z), str(self.home / "extraido"))
        self.assertFalse((self.root / "fora.txt").exists())

    def test_tar_inspecionar(self):
        t = self.downloads / "pacote.tar.gz"
        with tarfile.open(t, "w:gz") as f:
            data = b"conteudo"
            member = tarfile.TarInfo("x.txt")
            member.size = len(data)
            f.addfile(member, io.BytesIO(data))
        self.assertEqual(archives.inspect(self.org, str(t))["count"], 1)


class TestSeguranca(TempEnv):
    def test_perfil_com_pin(self):
        s = self.app.security
        s.save_profile("Convidado", ["read"], pin="1234")
        with self.assertRaises(PermissionError):
            s.switch_profile("Convidado", "0000")
        s.switch_profile("Convidado", "1234")
        self.assertFalse(s.allowed("organize"))
        self.assertTrue(s.allowed("read"))

    def test_senha_critica(self):
        s = self.app.security
        s.set_critical_password("segredo123")
        with self.assertRaises(PermissionError):
            s.require_critical({"confirm": True, "password": "errada"})
        s.require_critical({"confirm": True, "password": "segredo123"})
        self.assertNotIn("segredo123", self.app.store.config_path.read_text())   # só o hash é salvo


class TestConfiguracao(TempEnv):
    def test_padroes_downloads_e_de_hora_em_hora(self):
        cfg = self.app.store.config
        self.assertEqual(cfg["watch_dirs"], [str(self.downloads)])
        self.assertEqual(cfg["organize_schedule"]["frequency"], "interval")
        self.assertEqual(cfg["organize_schedule"]["interval_minutes"], 60)
        self.assertEqual(cfg["default_max_versions"], 5)

    def test_versoes_da_configuracao(self):
        self.rule("PDF", {"extensions": [".pdf"]}, "PDFs")
        versions = self.app.store.config_versions()
        self.assertTrue(versions)
        self.app.store.restore_config_version(versions[-1]["filename"])

    def test_exportar_importar(self):
        self.rule("PDF", {"extensions": [".pdf"]}, "PDFs")
        exported = self.app.export_config()["data"]
        self.app.store.config["rules"] = []
        self.app.import_config(json.loads(json.dumps(exported)))
        self.assertEqual(self.app.store.config["rules"][0]["name"], "PDF")

    def test_migracao_da_versao_09(self):
        from organizalocal.storage import Store
        path = self.root / "antigo"
        path.mkdir()
        (path / "config.json").write_text(json.dumps({"monitor_dirs": ["/x"], "backup_sources": ["/y"],
                                                      "backup_limit": 7, "rules": []}))
        store = Store(path)
        self.assertEqual(store.config["watch_dirs"], ["/x"])
        self.assertEqual(store.config["backup_jobs"][0]["max_versions"], 7)

    def test_agendador_intervalo_e_diario(self):
        sch = self.app.scheduler
        cfg = self.app.store.config
        cfg["last_runs"]["organize"] = (datetime.now() - timedelta(minutes=61)).astimezone().isoformat()
        self.assertTrue(sch.organize_due())
        cfg["last_runs"]["organize"] = datetime.now().astimezone().isoformat()
        self.assertFalse(sch.organize_due())
        cfg["organize_schedule"] = {"frequency": "daily", "time": "00:00", "interval_minutes": 60, "weekday": 0}
        cfg["last_runs"]["organize"] = (datetime.now() - timedelta(days=2)).astimezone().isoformat()
        self.assertTrue(sch.organize_due())
        cfg["organize_schedule"]["frequency"] = "off"
        self.assertFalse(sch.organize_due())

    def test_informacoes_do_sistema(self):
        data = sysinfo.collect(self.app.store)
        self.assertGreater(data["process"]["pid"], 0)
        self.assertGreater(data["memory"]["total"], 0)
        self.assertTrue(data["disks"])


if __name__ == "__main__":
    unittest.main()
