"""Jornadas guiadas e limites das operações do painel."""
from pathlib import Path
from unittest.mock import patch

from helpers import TempEnv, make_file


class TestFluxos(TempEnv):
    def test_escopos_distintos_e_regra_legada(self):
        images = self.home / "Fotos de trabalho"
        pdf = make_file(self.downloads / "contrato.pdf", b"%PDF-1.4")
        image = make_file(images / "frente.jpg", b"\xff\xd8\xff")
        other = make_file(images / "extras.pdf", b"%PDF-1.4")
        nested = make_file(images / "projeto" / "verso.jpg", b"\xff\xd8\xff")
        docs = self.home / "PDFs"
        output = self.home / "Imagens organizadas"
        self.rule("PDFs", {"extensions": [".pdf"]}, docs)
        rule = self.rule("Fotos de trabalho", {"extensions": [".jpg"]}, output,
                         sources=[str(images)], source_recursive=False)
        result = self.org.simulate()
        self.assertEqual(result["would_move"], 2)
        self.assertTrue(all(file.exists() for file in (pdf, image, other, nested)))

        self.org.save_rule({**rule, "source_recursive": True}, rule["id"])
        self.assertEqual(self.org.organize()["moved"], 3)
        self.assertTrue((docs / pdf.name).is_file())
        self.assertTrue((output / image.name).is_file())
        self.assertTrue((output / nested.name).is_file())
        self.assertTrue(other.is_file())

    def test_edicao_por_interface_antiga_preserva_escopo(self):
        source = self.home / "Origem"
        source.mkdir()
        rule = self.rule("PDFs", {"extensions": [".pdf"]}, self.home / "PDFs",
                         sources=[str(source)], source_recursive=True)
        edit = {key: value for key, value in rule.items() if key not in ("sources", "source_recursive")}
        saved = self.org.save_rule({**edit, "name": "PDFs revisados"}, rule["id"])
        self.assertEqual(saved["sources"], [str(source)])
        self.assertTrue(saved["source_recursive"])

        saved = self.org.save_rule({**edit, "sources": [], "source_recursive": False}, rule["id"])
        self.assertEqual(saved["sources"], [])
        self.assertFalse(saved["source_recursive"])

    def test_rascunho_le_arquivos_e_avisa_empate_sem_salvar(self):
        file = make_file(self.downloads / "rascunho.pdf", b"%PDF-1.4")
        first = self.rule("Regra existente", {"extensions": [".pdf"]}, self.home / "Antigo",
                          sources=[str(self.downloads)])
        draft = {**first, "name": "Regra proposta", "destination": str(self.home / "Novo")}
        before = self.app.store.config_path.read_bytes()
        result = self.app.dispatch("simulate_draft", {"rule": draft})
        self.assertEqual(result["would_move"], 0)
        self.assertEqual(result["summary"]["tie"], 1)
        self.assertIn("Regra existente", result["warnings"][0])
        self.assertTrue(file.is_file())
        self.assertEqual(self.app.store.config_path.read_bytes(), before)
        self.assertFalse((self.home / "Novo").exists())

    def test_escopo_recursivo_impede_destino_dentro_da_origem(self):
        with self.assertRaisesRegex(ValueError, "sobrepõe"):
            self.rule("Loop", {"extensions": [".pdf"]}, self.downloads / "PDFs",
                      sources=[str(self.downloads)], source_recursive=True)

    def test_teste_de_regra_inativa_usa_sua_origem(self):
        src = self.home / "Segunda origem"
        file = make_file(src / "nota.txt")
        target = self.home / "Notas"
        rule = self.rule("Notas", {"extensions": [".txt"]}, target, sources=[str(src)], enabled=False)
        self.assertEqual(self.org.simulate()["count"], 0)
        self.assertEqual(self.org.simulate(only_rule=rule["id"])["would_move"], 1)
        self.assertTrue(file.is_file())
        self.assertFalse(target.exists())

    def test_historico_filtra_periodo_e_simulacao(self):
        self.app.store.event("simulate", "ok", timestamp="2026-11-20T12:00:00")
        self.app.store.event("move", "ok", timestamp="2026-11-21T12:00:00")
        self.app.store.event("simulate", "ok", timestamp="2026-11-22T12:00:00")
        filters = {"operations": ["simulate"], "from_date": "2026-11-21", "to_date": "2026-11-22"}
        result = self.app.dispatch("history", {"filters": filters})
        self.assertEqual([item["timestamp"] for item in result], ["2026-11-22T12:00:00"])
        report = self.app.dispatch("history_pdf", {"filters": filters})
        self.assertEqual(report["events"], 1)
        self.assertTrue(Path(report["path"]).read_bytes().startswith(b"%PDF"))

    def test_previa_de_nome_e_colisao_preservam_arquivo(self):
        file = make_file(self.downloads / "nota.txt")
        target = self.downloads / "revisada-nota.txt"
        preview = self.org.rename_preview(str(file), "revisada-{name}")
        self.assertEqual(Path(preview["destination"]), target)
        self.assertTrue(file.is_file())
        make_file(target, "original do destino")
        with self.assertRaises(FileExistsError):
            self.org.rename_file(str(file), "revisada-{name}", expected=preview["destination"])
        self.assertTrue(file.is_file())
        self.assertEqual(target.read_text(), "original do destino")

    def test_seletor_e_delegado_sem_perder_o_caminho(self):
        chosen = {"path": str(self.downloads)}
        with patch("organizalocal.server.native_picker.select_path", return_value=chosen) as picker:
            self.assertEqual(self.app.dispatch("select_path", {"kind": "folder"}), chosen)
        picker.assert_called_once_with("folder")

    def test_perfil_invalido_nao_remove_acesso_administrativo(self):
        before = self.app.security.active_profile().copy()
        with self.assertRaisesRegex(ValueError, "configurações"):
            self.app.security.save_profile(before["name"], ["read"])
        self.assertEqual(self.app.security.active_profile(), before)
