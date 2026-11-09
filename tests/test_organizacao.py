"""Testes da organização: HU06–HU12, RNF04, RNF05, RNF09 e RNF10."""
import json
import unittest

from helpers import TempEnv, make_file
from organizalocal.storage import sha256


class TestCrudRegras(TempEnv):
    def test_hu06_listar_com_condicao_destino_prioridade_estado_excecoes(self):
        self.rule("PDF", {"extensions": [".pdf"]}, "PDFs", priority=7,
                  exceptions=[{"conditions": {"keywords": ["boleto"]}}])
        rule = self.app.state()["rules"][0]
        for key in ("conditions", "destination", "priority", "enabled", "exceptions"):
            self.assertIn(key, rule)
        self.assertEqual(len(rule["exceptions"]), 1)

    def test_hu07_editar_regra(self):
        r = self.rule("PDF", {"extensions": [".pdf"]}, "PDFs")
        r["destination"] = str(self.home / "Outra")
        self.org.save_rule(r, r["id"])
        self.assertIn("Outra", self.org.decide(make_file(self.downloads / "a.pdf"))["destination"])

    def test_hu08_excluir_exige_confirmacao(self):
        r = self.rule("PDF", {"extensions": [".pdf"]}, "PDFs")
        with self.assertRaises(PermissionError):
            self.app.dispatch("rule_delete", {"id": r["id"]})
        self.app.dispatch("rule_delete", {"id": r["id"], "confirm": True})
        self.assertEqual(self.org.decide(make_file(self.downloads / "a.pdf"))["action"], "no_match")

    def test_duplicar_regra_nasce_desativada(self):
        r = self.rule("PDF", {"extensions": [".pdf"]}, "PDFs")
        copy = self.org.duplicate_rule(r["id"])
        self.assertFalse(copy["enabled"])
        self.assertNotEqual(copy["id"], r["id"])


class TestSimulacaoEExecucao(TempEnv):
    def test_hu10_simulacao_nao_move_nem_modifica(self):
        self.rule("PDF", {"extensions": [".pdf"]}, "PDFs")
        f = make_file(self.downloads / "a.pdf", "abc")
        before = (sha256(f), f.stat().st_mtime)
        sim = self.org.simulate()
        self.assertEqual(sim["would_move"], 1)
        self.assertTrue(sim["rows"][0]["destination"].endswith("a.pdf"))
        self.assertTrue(f.exists())
        self.assertEqual((sha256(f), f.stat().st_mtime), before)
        self.assertFalse((self.home / "PDFs").exists())

    def test_hu11_executa_e_preserva_conteudo(self):
        self.rule("PDF", {"extensions": [".pdf"]}, "PDFs")
        f = make_file(self.downloads / "a.pdf", "conteudo importante")
        digest = sha256(f)
        result = self.org.organize()
        target = self.home / "PDFs" / "a.pdf"
        self.assertEqual(result["moved"], 1)
        self.assertEqual(result["status"], "ok")
        self.assertFalse(f.exists())
        self.assertEqual(sha256(target), digest)                      # RNF05
        event = self.app.store.history({"operation": "move"})[0]
        self.assertEqual(event["sha256"], digest)
        self.assertEqual(event["rule_name"], "PDF")

    def test_rnf10_conflito_renomeia_sem_sobrescrever(self):
        self.rule("PDF", {"extensions": [".pdf"]}, "PDFs")
        existing = make_file(self.home / "PDFs" / "a.pdf", "antigo")
        make_file(self.downloads / "a.pdf", "novo")
        self.org.organize()
        self.assertEqual(existing.read_text(), "antigo")
        self.assertEqual((self.home / "PDFs" / "a (1).pdf").read_text(), "novo")

    def test_conflito_politica_revisao_e_ignorar(self):
        self.rule("PDF", {"extensions": [".pdf"]}, "PDFs")
        make_file(self.home / "PDFs" / "a.pdf", "antigo")
        make_file(self.downloads / "a.pdf", "novo")
        self.assertEqual(self.org.organize(conflict="skip")["skipped"], 1)
        result = self.org.organize(conflict="review")
        self.assertEqual(result["reviewed"], 1)
        item = self.org.review_list()[0]
        with self.assertRaises(PermissionError):
            self.org.resolve_review(item["id"], "replace")             # precisa de confirmação
        self.org.resolve_review(item["id"], "replace", confirm=True)
        self.assertEqual((self.home / "PDFs" / "a.pdf").read_text(), "novo")
        # o arquivo substituído foi preservado antes
        preserved = list((self.app.store.root / "protected_versions").iterdir())
        self.assertEqual(preserved[0].read_text(), "antigo")

    def test_empate_vai_para_revisao(self):
        self.rule("A", {"extensions": [".pdf"]}, "A", priority=5)
        self.rule("B", {"keywords": ["x"]}, "B", priority=5)
        make_file(self.downloads / "x.pdf")
        self.assertEqual(self.org.organize()["reviewed"], 1)
        self.assertEqual(self.org.review_list()[0]["reason"], "priority_tie")

    def test_hu12_falha_e_informada_e_nao_conta_como_sucesso(self):
        self.rule("PDF", {"extensions": [".pdf"]}, "PDFs")
        (self.home / "PDFs").write_text("isto é um arquivo, não uma pasta")   # destino impossível
        make_file(self.downloads / "a.pdf")
        result = self.org.organize()
        self.assertEqual(result["moved"], 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["status"], "error")
        self.assertTrue((self.downloads / "a.pdf").exists())            # origem intacta
        self.assertTrue(result["errors"][0]["reason"])
        self.assertEqual(self.app.store.history({"operation": "organize"})[0]["status"], "error")

    def test_ignora_temporarios_recentes_e_ocultos(self):
        self.rule("Tudo", {"glob": "*"}, "Tudo")
        make_file(self.downloads / "video.mp4.crdownload")
        make_file(self.downloads / "recente.pdf", age_seconds=0)
        make_file(self.downloads / ".oculto")
        self.assertEqual({r["action"] for r in self.org.simulate()["rows"]}, {"busy"})

    def test_protegidos_e_exclusoes(self):
        self.rule("PDF", {"extensions": [".pdf"]}, "PDFs")
        f = make_file(self.downloads / "contrato.pdf")
        self.app.store.config["protected_paths"] = [str(f)]
        self.assertEqual(self.org.decide(f)["action"], "excluded")
        self.app.store.config["protected_paths"] = []
        self.app.store.config["exclusions"]["names"] = ["contrato.pdf"]
        self.assertEqual(self.org.decide(f)["action"], "excluded")

    def test_disfarcado_vai_para_revisao_ou_quarentena(self):
        self.rule("Imagens", {"categories": ["Imagens"]}, "Imagens")
        make_file(self.downloads / "foto.jpg", b"MZ\x90\x00")
        self.assertEqual(self.org.organize()["reviewed"], 1)
        self.app.store.config["quarantine_risky"] = True
        self.org.resolve_review(self.org.review_list()[0]["id"], "ignore")
        self.assertEqual(self.org.organize()["quarantined"], 1)
        self.assertEqual(self.org.quarantine_list()[0]["name"], "foto.jpg")

    def test_desfazer_movimentacao(self):
        self.rule("PDF", {"extensions": [".pdf"]}, "PDFs")
        make_file(self.downloads / "a.pdf", "x")
        self.org.organize()
        move = self.app.store.history({"operation": "move"})[0]
        self.org.undo(move["id"])
        self.assertTrue((self.downloads / "a.pdf").exists())
        self.assertFalse((self.home / "PDFs" / "a.pdf").exists())

    def test_renomear_ao_mover(self):
        self.rule("PDF", {"extensions": [".pdf"]}, "PDFs", rename_pattern="{year}_{name}")
        make_file(self.downloads / "nota.pdf")
        self.org.organize()
        self.assertEqual(len(list((self.home / "PDFs").glob("20*_nota.pdf"))), 1)


class TestInventarioExtensoes(TempEnv):
    """Lista de extensões da pasta monitorada usada nos checkboxes do formulário de regra."""

    def test_lista_extensoes_com_contagem_categoria_e_exemplos(self):
        make_file(self.downloads / "a.PDF", "x" * 10)
        make_file(self.downloads / "b.pdf", "y" * 5)
        make_file(self.downloads / "foto.jpg")
        make_file(self.downloads / "backup.tar.gz")
        make_file(self.downloads / "LEIAME")                       # sem extensão
        inv = self.org.extension_inventory()
        by_ext = {i["ext"]: i for i in inv["extensions"]}
        self.assertEqual(list(by_ext)[0], ".pdf")                  # mais frequente primeiro
        self.assertEqual(by_ext[".pdf"]["count"], 2)               # sem diferenciar maiúsculas
        self.assertEqual(by_ext[".pdf"]["bytes"], 15)
        self.assertEqual(by_ext[".pdf"]["category"], "Documentos")
        self.assertIn(".tar.gz", by_ext)                           # extensão dupla
        self.assertEqual(inv["without_extension"], 1)
        self.assertEqual(inv["total_files"], 5)
        self.assertLessEqual(len(by_ext[".pdf"]["examples"]), 3)

    def test_indica_regras_ativas_que_ja_usam_a_extensao(self):
        make_file(self.downloads / "a.pdf")
        r = self.rule("PDF", {"extensions": [".pdf"]}, "PDFs", priority=7)
        inv = self.org.extension_inventory()
        self.assertEqual(inv["extensions"][0]["used_by"][0]["name"], "PDF")
        self.org.set_enabled(r["id"], False)                       # desativada não conta
        self.assertEqual(self.org.extension_inventory()["extensions"][0]["used_by"], [])

    def test_ignora_downloads_em_andamento(self):
        make_file(self.downloads / "video.mp4.crdownload")
        make_file(self.downloads / "jogo.part")
        inv = self.org.extension_inventory()
        self.assertEqual(inv["extensions"], [])
        self.assertEqual(inv["temporary"], 2)

    def test_nao_lista_pasta_de_dados_nem_excluidos(self):
        make_file(self.downloads / "a.iso")
        self.app.store.config["exclusions"]["extensions"] = [".iso"]
        self.assertEqual(self.org.extension_inventory()["extensions"], [])

    def test_acao_da_api(self):
        make_file(self.downloads / "a.docx")
        result = self.app.dispatch("extensions_scan", {})
        self.assertEqual(result["extensions"][0]["ext"], ".docx")


class TestFerramentas(TempEnv):
    def test_duplicados_e_remocao_segura(self):
        a = make_file(self.downloads / "a.txt", "igual")
        b = make_file(self.downloads / "b.txt", "igual")
        make_file(self.downloads / "c.txt", "diferente")
        groups = self.org.duplicates()
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["files"]), 2)
        self.org.remove_duplicate(str(b), keep=str(a))
        self.assertFalse(b.exists())
        with self.assertRaises(ValueError):
            self.org.remove_duplicate(str(self.downloads / "c.txt"), keep=str(a))

    def test_sandbox_nao_toca_originais(self):
        self.rule("PDF", {"extensions": [".pdf"]}, "PDFs")
        f = make_file(self.downloads / "a.pdf")
        result = self.org.sandbox_run()
        self.assertTrue(f.exists())
        self.assertEqual(result["results"][0]["rule"], "PDF")

    def test_sugestoes_para_arquivos_sem_regra(self):
        make_file(self.downloads / "foto.png", b"\x89PNG\r\n\x1a\n")
        s = self.org.suggestions()[0]
        self.assertEqual(s["category"], "Imagens")

    def test_exportar_simulacao(self):
        make_file(self.downloads / "a.pdf")
        out = self.app.reports.export_simulation(self.org.simulate())
        self.assertIn("rows", json.loads(open(out["path"], encoding="utf-8").read()))


if __name__ == "__main__":
    unittest.main()
