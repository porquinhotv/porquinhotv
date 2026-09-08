"""Fonte de pesquisa do proprio site, ponta a ponta, sem rede.

Duas fases: colher candidatos da pagina de pesquisa e ler cada candidato.
Uma pagina que falhe nao derruba as outras, e o limite de candidatos
existe para uma pesquisa mal apertada nao gerar milhares de pedidos.
"""

import unittest
from unittest import mock

from tests.apoio import ler

from recolha.fontes import busca_site
from recolha.modelos import Fonte
from recolha.rede import ErroDeRede

FONTE = Fonte(
    id="busca-rtp1", tipo="busca_site", canal="rtp1", dominio="exemplo.pt",
    busca=("https://exemplo.pt/pesquisa?q={termo}",), max_candidatos=40,
)


def obter_falso(url):
    if "pesquisa" in url or "/search" in url:
        return ler("pesquisa_resultados.html")
    if "noticias" in url:
        return ler("artigo_sem_duracao.html")
    return ler("artigo_video.html")


class TestBuscaSite(unittest.TestCase):
    def setUp(self):
        self.patcher = mock.patch.object(busca_site, "obter_texto", side_effect=obter_falso)
        self.obter = self.patcher.start()
        self.addCleanup(self.patcher.stop)
        mock.patch.object(busca_site.time, "sleep", lambda s: None).start()
        self.addCleanup(mock.patch.stopall)

    def test_le_candidatos_e_duracao(self):
        itens = list(busca_site.FonteBuscaSite(FONTE).obter(termos=["Pessoa Exemplo"]))
        self.assertEqual(len(itens), 2)
        self.assertEqual(itens[0].duracao_s, 4350)
        self.assertEqual(itens[0].canal, "rtp1")
        self.assertIsNone(itens[1].duracao_s)
        self.assertEqual(itens[1].publicado_em, "2021-03-15")

    def test_prova_e_o_url_do_canal(self):
        itens = list(busca_site.FonteBuscaSite(FONTE).obter(termos=["Pessoa Exemplo"]))
        for item in itens:
            self.assertTrue(item.prova_url.startswith("https://exemplo.pt/"))

    def test_um_termo_por_pedido_de_pesquisa(self):
        list(busca_site.FonteBuscaSite(FONTE).obter(termos=["Ventura", "André Ventura"]))
        pesquisas = [c.args[0] for c in self.obter.call_args_list if "pesquisa" in c.args[0]]
        self.assertEqual(len(pesquisas), 2)
        self.assertIn("Andr%C3%A9%20Ventura", pesquisas[1])

    def test_paginacao(self):
        fonte = Fonte(id="x", tipo="busca_site", canal="rtp1", dominio="exemplo.pt",
                      busca=("https://exemplo.pt/pesquisa?q={termo}&p={pagina}",), paginas_max=3)
        list(busca_site.FonteBuscaSite(fonte).obter(termos=["Ventura"]))
        pesquisas = [c.args[0] for c in self.obter.call_args_list if "pesquisa" in c.args[0]]
        self.assertEqual(len(pesquisas), 3)
        self.assertTrue(pesquisas[2].endswith("&p=3"))

    def test_limite_de_candidatos(self):
        fonte = Fonte(id="x", tipo="busca_site", canal="rtp1", dominio="exemplo.pt",
                      busca=("https://exemplo.pt/pesquisa?q={termo}",), max_candidatos=1)
        itens = list(busca_site.FonteBuscaSite(fonte).obter(termos=["Ventura"]))
        self.assertEqual(len(itens), 1)

    def test_candidato_que_falha_nao_derruba_os_outros(self):
        def com_falha(url):
            if "noticias" in url:
                raise ErroDeRede("falhou")
            return obter_falso(url)

        self.obter.side_effect = com_falha
        registo = []
        itens = list(busca_site.FonteBuscaSite(FONTE).obter(termos=["Ventura"], registo=registo))
        self.assertEqual(len(itens), 1)
        self.assertTrue(any("candidato falhou" in linha for linha in registo))

    def test_fonte_sem_configuracao_devolve_nada(self):
        vazia = Fonte(id="x", tipo="busca_site", canal="rtp1")
        self.assertEqual(list(busca_site.FonteBuscaSite(vazia).obter(termos=["Ventura"])), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestConsultasEPaginacao(unittest.TestCase):
    """Duas coisas que a sondagem obrigou a acrescentar."""

    def setUp(self):
        self.patcher = mock.patch.object(busca_site, "obter_texto", side_effect=obter_falso)
        self.obter = self.patcher.start()
        self.addCleanup(self.patcher.stop)
        mock.patch.object(busca_site.time, "sleep", lambda s: None).start()
        self.addCleanup(mock.patch.stopall)

    def test_pagina0_conta_a_partir_de_zero(self):
        """Ha motores que numeram a primeira pagina como zero. Usar
        {pagina} nesses saltava a primeira pagina de resultados."""
        f = Fonte(id="m", tipo="busca_site", canal="rtp1", dominio="exemplo.pt",
                  busca=("https://exemplo.pt/pesquisa?q={termo}&offset={pagina0}",), paginas_max=3)
        list(busca_site.FonteBuscaSite(f).obter(termos=["Ventura"]))
        offsets = [c.args[0].split("offset=")[1] for c in self.obter.call_args_list if "offset=" in c.args[0]]
        self.assertEqual(offsets, ["0", "1", "2"])

    def test_termos_busca_substituem_os_do_sujeito(self):
        """Num motor externo, tres consultas por canal sao tres vezes mais
        pedidos sem tres vezes mais resultados."""
        f = Fonte(id="m", tipo="busca_site", canal="rtp1", dominio="exemplo.pt",
                  busca=("https://exemplo.pt/pesquisa?q={termo}",), termos_busca=("Nome Completo entrevista",))
        list(busca_site.FonteBuscaSite(f).obter(termos=["Ventura", "André Ventura", "Andre Ventura"]))
        pesquisas = [c.args[0] for c in self.obter.call_args_list if "pesquisa" in c.args[0]]
        self.assertEqual(len(pesquisas), 1)
        self.assertIn("Nome%20Completo%20entrevista", pesquisas[0])

    def test_ligacoes_sao_do_dominio_alvo_e_nao_do_motor(self):
        """A prova de cada linha e o endereco do canal, nunca o do motor."""
        f = Fonte(id="m", tipo="busca_site", canal="rtp1", dominio="exemplo.pt",
                  busca=("https://motor.externo/search?q={termo}",))
        itens = list(busca_site.FonteBuscaSite(f).obter(termos=["Ventura"]))
        self.assertTrue(itens)
        for i in itens:
            self.assertTrue(i.prova_url.startswith("https://exemplo.pt/"), i.prova_url)
