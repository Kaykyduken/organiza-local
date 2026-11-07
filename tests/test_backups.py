"""Testes dos backups por regras com versões (padrão 5) e retenção."""
import time
import unittest

from helpers import TempEnv, make_file


class TestBackups(TempEnv):
    def setUp(self):
        super().setUp()
        self.src = self.home / "Documents" / "Faculdade"
        make_file(self.src / "tcc.md", "v1")
        make_file(self.src / "sub" / "resumo.txt", "resumo")
        make_file(self.src / "lixo.tmp", "temp")
        self.b = self.app.backups

    def job(self, **extra):
        payload = {"name": "Faculdade", "sources": [str(self.src)], "exclude_patterns": ["*.tmp"], **extra}
        return self.b.save_job(payload)

    def test_padrao_5_versoes(self):
        self.assertEqual(self.job()["max_versions"], 5)

    def test_cria_versao_com_manifesto_e_filtros(self):
        job = self.job()
        result = self.b.run(job["id"])
        self.assertTrue(result["created"])
        files = {f["rel"] for f in self.b.manifest(job["id"], result["version"]["id"])["files"]}
        self.assertEqual(files, {"tcc.md", "sub/resumo.txt"})                 # .tmp excluído
        self.assertTrue(self.b.verify(job["id"], result["version"]["id"])["ok"])

    def test_nao_cria_versao_sem_mudancas(self):
        job = self.job()
        self.b.run(job["id"])
        self.assertFalse(self.b.run(job["id"])["created"])

    def test_retencao_mantem_no_maximo_n_versoes_e_respeita_travadas(self):
        job = self.job(max_versions=3)
        ids = []
        for i in range(5):
            make_file(self.src / "tcc.md", f"versao {i}")
            ids.append(self.b.run(job["id"])["version"]["id"])
            time.sleep(1.05)                                   # ids de versão são por segundo
            if i == 0:
                self.b.set_locked(job["id"], ids[0], True)     # a primeira fica travada
        kept = [v["id"] for v in self.b.versions(job["id"])]
        self.assertEqual(len(kept), 3)
        self.assertIn(ids[0], kept)                            # travada sobreviveu
        self.assertEqual(kept[1:], ids[-2:])
        with self.assertRaises(PermissionError):
            self.b.delete_version(job["id"], ids[0])

    def test_reduzir_maximo_exige_confirmacao(self):
        job = self.job(skip_unchanged=False)
        for _ in range(3):
            self.b.run(job["id"])
            time.sleep(1.05)
        with self.assertRaises(PermissionError):
            self.b.save_job({**job, "max_versions": 1}, job["id"])
        self.b.save_job({**job, "max_versions": 1, "confirm": True}, job["id"])
        self.assertEqual(len(self.b.versions(job["id"])), 1)

    def test_restaurar_no_local_original_preserva_atual(self):
        job = self.job()
        v1 = self.b.run(job["id"])["version"]["id"]
        make_file(self.src / "tcc.md", "v2 estragado")
        with self.assertRaises(PermissionError):
            self.b.restore(job["id"], v1)
        result = self.b.restore(job["id"], v1, confirm=True)
        self.assertEqual((self.src / "tcc.md").read_text(), "v1")
        self.assertEqual(len(result["preserved_current"]), 1)

    def test_restaurar_em_outra_pasta_e_um_arquivo(self):
        job = self.job(mode="copy")
        v1 = self.b.run(job["id"])["version"]["id"]
        out = self.home / "restaurado"
        self.b.restore(job["id"], v1, target_dir=str(out), only=["01_Faculdade/tcc.md"], confirm=True)
        self.assertEqual((out / "01_Faculdade" / "tcc.md").read_text(), "v1")
        self.assertFalse((out / "01_Faculdade" / "sub").exists())

    def test_comparar_versoes(self):
        job = self.job()
        a = self.b.run(job["id"])["version"]["id"]
        time.sleep(1.05)
        make_file(self.src / "tcc.md", "v2")
        make_file(self.src / "novo.txt", "n")
        (self.src / "sub" / "resumo.txt").unlink()
        b = self.b.run(job["id"])["version"]["id"]
        diff = self.b.compare(job["id"], a, b)
        self.assertEqual(diff["changed"], ["01_Faculdade/tcc.md"])
        self.assertEqual(diff["added"], ["01_Faculdade/novo.txt"])
        self.assertEqual(diff["removed"], ["01_Faculdade/sub/resumo.txt"])

    def test_destino_dentro_da_origem_e_recusado(self):
        with self.assertRaises(ValueError):
            self.job(destination=str(self.src / "backups"))

    def test_agendamento_por_intervalo(self):
        job = self.job(interval_hours=24)
        self.assertTrue(self.b.is_due(job))
        self.b.run(job["id"])
        self.assertFalse(self.b.is_due(self.b.job(job["id"])))

    def test_historico_de_um_arquivo(self):
        job = self.job()
        self.b.run(job["id"])
        self.assertEqual(len(self.b.file_history(str(self.src / "tcc.md"))), 1)


if __name__ == "__main__":
    unittest.main()
