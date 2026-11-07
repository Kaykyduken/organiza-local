"""Testes das regras: HU01–HU05, HU09 e RF11 (conflitos)."""
import unittest

from helpers import TempEnv, make_file
from organizalocal import rules as R


class TestCondicoes(TempEnv):
    def test_hu01_extensao_sem_diferenciar_maiusculas(self):
        f = make_file(self.downloads / "RELATORIO.PDF")
        self.assertTrue(R.matches(f, {"extensions": [".pdf"]}))
        self.assertTrue(R.matches(f, {"extensions": ["PDF"]}))          # sem ponto e maiúsculo
        self.assertFalse(R.matches(f, {"extensions": [".docx", ".xlsx"]}))

    def test_hu01_varias_extensoes(self):
        self.assertTrue(R.matches(make_file(self.downloads / "a.xlsx"), {"extensions": [".docx", ".xlsx"]}))

    def test_extensao_dupla_tar_gz(self):
        self.assertEqual(R.extension("backup.TAR.GZ"), ".tar.gz")

    def test_hu02_palavra_em_qualquer_posicao(self):
        for name in ("faculdade_SO.pdf", "trabalho-FACULDADE.docx", "minhaFaculdadeX.txt"):
            self.assertTrue(R.matches(make_file(self.downloads / name), {"keywords": ["faculdade"]}), name)
        self.assertFalse(R.matches(make_file(self.downloads / "outro.pdf"), {"keywords": ["faculdade"]}))

    def test_condicoes_combinadas_com_e(self):
        f = make_file(self.downloads / "faculdade.txt")
        self.assertFalse(R.matches(f, {"keywords": ["faculdade"], "extensions": [".pdf"]}))
        self.assertTrue(R.matches(f, {"keywords": ["faculdade"], "extensions": [".txt"]}))

    def test_categoria_glob_regex_prefixo_sufixo(self):
        f = make_file(self.downloads / "NF_2026-11_mercado.pdf")
        self.assertTrue(R.matches(f, {"categories": ["Documentos"]}))
        self.assertTrue(R.matches(f, {"glob": "nf_*.pdf"}))
        self.assertTrue(R.matches(f, {"regex": r"\d{4}-\d{2}"}))
        self.assertTrue(R.matches(f, {"prefix": "nf_"}))
        self.assertTrue(R.matches(f, {"suffix": "mercado"}))

    def test_tamanho_e_idade(self):
        f = make_file(self.downloads / "grande.bin", b"x" * 2048, age_seconds=10 * 86400)
        self.assertTrue(R.matches(f, {"size_min": 1024}))
        self.assertFalse(R.matches(f, {"size_max": 1000}))
        self.assertTrue(R.matches(f, {"age_days_min": 5}))
        self.assertFalse(R.matches(f, {"age_days_max": 5}))

    def test_formato_real_pelos_bytes_iniciais(self):
        self.assertEqual(R.detect_format(make_file(self.downloads / "x.pdf", b"%PDF-1.7")), "pdf")
        self.assertEqual(R.detect_format(make_file(self.downloads / "x.png", b"\x89PNG\r\n\x1a\n..")), "png")
        self.assertEqual(R.detect_format(make_file(self.downloads / "x.docx", b"PK\x03\x04[Content_Types].xml")), "office")
        self.assertTrue(R.matches(make_file(self.downloads / "sem_extensao", b"%PDF-1.4"), {"formats": ["pdf"]}))

    def test_executavel_disfarcado(self):
        self.assertTrue(R.is_disguised(make_file(self.downloads / "foto.jpg", b"MZ\x90\x00")))
        self.assertFalse(R.is_disguised(make_file(self.downloads / "setup.exe", b"MZ\x90\x00")))

    def test_regra_sem_condicao_nao_casa(self):
        self.assertFalse(R.matches(make_file(self.downloads / "a.pdf"), {}))


class TestPrioridadeEExcecoes(TempEnv):
    def test_hu03_maior_prioridade_vence(self):
        self.rule("PDF", {"extensions": [".pdf"]}, "PDFs", priority=3)
        self.rule("Faculdade", {"keywords": ["fatec"]}, "Faculdade", priority=8)
        row = self.org.decide(make_file(self.downloads / "trabalho_fatec.pdf"))
        self.assertEqual(row["rule_name"], "Faculdade")
        self.assertEqual(len(row["matched"]), 2)              # RF11: conflito identificado
        self.assertIn("vale a de maior prioridade", row["reason"])

    def test_hu03_empate_e_indicado(self):
        self.rule("A", {"extensions": [".pdf"]}, "A", priority=5)
        self.rule("B", {"keywords": ["nota"]}, "B", priority=5)
        row = self.org.decide(make_file(self.downloads / "nota.pdf"))
        self.assertEqual(row["action"], "tie")
        self.assertIn("Empate", row["reason"])
        self.assertTrue(any("Mesma prioridade" in p["error"] for p in self.org.validate_all()))

    def test_hu04_aumentar_diminuir_e_salvar_ordem(self):
        a = self.rule("A", {"extensions": [".pdf"]}, "A", priority=5)
        b = self.rule("B", {"extensions": [".txt"]}, "B", priority=4)
        self.org.change_priority(b["id"], delta=+2)
        self.org.change_priority(a["id"], delta=-1)
        self.assertEqual([r["name"] for r in self.org.ordered_rules()], ["B", "A"])
        reloaded = type(self.app.store)(self.app.store.root)    # RNF08: persiste em disco
        self.assertEqual({r["name"]: r["priority"] for r in reloaded.config["rules"]}, {"A": 4, "B": 6})

    def test_prioridade_limitada_entre_0_e_10(self):
        r = self.rule("A", {"extensions": [".pdf"]}, "A", priority=10)
        self.assertEqual(self.org.change_priority(r["id"], delta=+1)["priority"], 10)

    def test_hu05_excecao_impede_movimento(self):
        self.rule("PDF", {"extensions": [".pdf"]}, "PDFs",
                  exceptions=[{"conditions": {"keywords": ["boleto"]}, "action": "skip"}])
        self.assertEqual(self.org.decide(make_file(self.downloads / "boleto_luz.pdf"))["action"], "exception")
        self.assertEqual(self.org.decide(make_file(self.downloads / "livro.pdf"))["action"], "move")

    def test_hu05_excecao_redireciona(self):
        self.rule("PDF", {"extensions": [".pdf"]}, "PDFs",
                  exceptions=[{"conditions": {"keywords": ["boleto"]}, "action": "move",
                               "destination": str(self.home / "Contas")}])
        row = self.org.decide(make_file(self.downloads / "boleto.pdf"))
        self.assertTrue(row["destination"].startswith(str(self.home / "Contas")))

    def test_hu05_editar_e_excluir_excecao(self):
        r = self.rule("PDF", {"extensions": [".pdf"]}, "PDFs",
                      exceptions=[{"conditions": {"keywords": ["boleto"]}, "action": "skip"}])
        r["exceptions"] = []
        self.org.save_rule(r, r["id"])
        self.assertEqual(self.org.decide(make_file(self.downloads / "boleto.pdf"))["action"], "move")

    def test_hu09_regra_desativada_nao_aplica_e_estado_persiste(self):
        r = self.rule("PDF", {"extensions": [".pdf"]}, "PDFs")
        self.org.set_enabled(r["id"], False)
        self.assertEqual(self.org.decide(make_file(self.downloads / "a.pdf"))["action"], "no_match")
        self.assertFalse(type(self.app.store)(self.app.store.root).config["rules"][0]["enabled"])


class TestValidacao(TempEnv):
    def test_destino_relativo_e_regex_invalida(self):
        with self.assertRaises(ValueError):
            self.org.save_rule({"name": "x", "conditions": {"extensions": [".pdf"]}, "destination": "pasta/relativa"})
        with self.assertRaises(ValueError):
            self.rule("x", {"regex": "("}, "X")

    def test_destino_na_pasta_de_dados_e_bloqueado(self):
        with self.assertRaises(ValueError):
            self.org.save_rule({"name": "x", "conditions": {"extensions": [".pdf"]},
                                "destination": str(self.app.store.root / "history"), "create_destination": True})

    def test_sem_condicao_e_recusada(self):
        with self.assertRaises(ValueError):
            self.rule("x", {}, "X")


if __name__ == "__main__":
    unittest.main()
