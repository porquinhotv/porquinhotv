"""Extracao generica de dados estruturados.

O que importa aqui e que nao ha um unico seletor de nenhum site: le-se
schema.org e OpenGraph, e por isso o mesmo codigo serve os nove canais e
sobrevive a uma remodelacao de qualquer um deles.
"""

import unittest

from tests.apoio import ler

from recolha import extracao


class TestDuracao(unittest.TestCase):
    def test_iso(self):
        self.assertEqual(extracao.duracao_para_segundos("PT1H12M30S"), 4350)
        self.assertEqual(extracao.duracao_para_segundos("PT45M"), 2700)
        self.assertEqual(extracao.duracao_para_segundos("PT90S"), 90)

    def test_relogio(self):
        self.assertEqual(extracao.duracao_para_segundos("01:12:30"), 4350)
        self.assertEqual(extracao.duracao_para_segundos("12:30"), 750)

    def test_numero(self):
        self.assertEqual(extracao.duracao_para_segundos(4350), 4350)
        self.assertEqual(extracao.duracao_para_segundos("4350"), 4350)

    def test_zero_nunca_e_duracao(self):
        """Zero seria um numero publicado que nao veio de uma medicao."""
        self.assertIsNone(extracao.duracao_para_segundos(0))
        self.assertIsNone(extracao.duracao_para_segundos("PT0S"))
        self.assertIsNone(extracao.duracao_para_segundos(""))
        self.assertIsNone(extracao.duracao_para_segundos("qualquer coisa"))
        self.assertIsNone(extracao.duracao_para_segundos(None))


class TestData(unittest.TestCase):
    def test_formas(self):
        self.assertEqual(extracao.data_para_iso("2021-03-15T21:30:00+00:00"), "2021-03-15")
        self.assertEqual(extracao.data_para_iso("15/03/2021"), "2021-03-15")
        self.assertEqual(extracao.data_para_iso("15-03-2021"), "2021-03-15")

    def test_invalida_fica_vazia(self):
        self.assertEqual(extracao.data_para_iso("32/13/2021"), "")
        self.assertEqual(extracao.data_para_iso("ontem"), "")
        self.assertEqual(extracao.data_para_iso(""), "")


class TestExtrair(unittest.TestCase):
    def test_video_com_duracao(self):
        r = extracao.extrair(ler("artigo_video.html"), "https://exemplo.pt/a")
        self.assertEqual(r["duracao_s"], 4350)
        self.assertEqual(r["publicado_em"], "2021-03-15")
        self.assertTrue(r["e_video"])
        self.assertIn("Pessoa Exemplo", r["titulo"])

    def test_artigo_sem_duracao(self):
        r = extracao.extrair(ler("artigo_sem_duracao.html"), "https://exemplo.pt/b")
        self.assertIsNone(r["duracao_s"])
        self.assertEqual(r["publicado_em"], "2021-03-15")
        self.assertFalse(r["e_video"])

    def test_pagina_sem_nada(self):
        r = extracao.extrair("<html><body>nada</body></html>", "https://exemplo.pt/c")
        self.assertIsNone(r["duracao_s"])
        self.assertEqual(r["publicado_em"], "")

    def test_jsonld_malformado_nao_rebenta(self):
        html = '<script type="application/ld+json">{isto nao e json}</script><title>T</title>'
        r = extracao.extrair(html, "https://exemplo.pt/d")
        self.assertEqual(r["titulo"], "T")


class TestLigacoes(unittest.TestCase):
    def test_colhe_so_do_dominio_e_sem_navegacao(self):
        html = ler("pesquisa_resultados.html")
        achados = extracao.ligacoes(html, "https://exemplo.pt/pesquisa", "exemplo.pt")
        self.assertEqual(achados, [
            "https://exemplo.pt/play/p1234/entrevista-a-pessoa-exemplo",
            "https://exemplo.pt/noticias/pessoa-exemplo-em-entrevista",
        ])

    def test_padrao_aperta(self):
        html = ler("pesquisa_resultados.html")
        achados = extracao.ligacoes(html, "https://exemplo.pt/pesquisa", "exemplo.pt", r"/play/p[0-9]+/")
        self.assertEqual(achados, ["https://exemplo.pt/play/p1234/entrevista-a-pessoa-exemplo"])

    def test_subdominio_conta_como_mesmo_dominio(self):
        html = '<a href="https://tvi.iol.pt/noticias/uma-noticia-qualquer">x</a>'
        self.assertEqual(
            extracao.ligacoes(html, "https://iol.pt/", "iol.pt"),
            ["https://tvi.iol.pt/noticias/uma-noticia-qualquer"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
