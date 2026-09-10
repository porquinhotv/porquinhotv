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

    def test_le_candidatos_com_data_e_canal(self):
        itens = list(busca_site.FonteBuscaSite(FONTE).obter(termos=["Pessoa Exemplo"]))
        self.assertEqual(len(itens), 2)
        self.assertEqual(itens[0].canal, "rtp1")
        self.assertEqual(itens[1].publicado_em, "2021-03-15")
        for item in itens:
            self.assertFalse(hasattr(item, "duracao_s"), "a duracao saiu do modelo a 2026-09-10")

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


class TestListaDeEpisodiosNaConfiguracaoReal(unittest.TestCase):
    """A lista de episodios do programa de entrevistas da RTP.

    Tres coisas que, se mudarem, tiram valor a fonte sem partir nada, e
    por isso passam sem se dar por elas:

    1. sem o nome do programa escrito na fonte, a prova positiva de
       formato recusa os episodios que o canal titula so com o nome do
       convidado, que sao muitos;
    2. sem `{pagina}` no endereco, a fonte pede sempre a primeira pagina
       e a corrida de historico nao vai a lado nenhum. Medido a
       2026-09-10: doze episodios por pagina, e a lista acaba entre a
       pagina 12 e a 20;
    3. o identificador tem de ser o do programa. Com o de uma temporada,
       o sujeito nao aparece na lista.
    """

    def setUp(self):
        from recolha.modelos import carregar_config

        self.fonte = next(f for f in carregar_config().fontes if f.id == "lista-rtp-grande-entrevista")

    def test_declara_o_programa(self):
        self.assertTrue(self.fonte.programa, "sem programa, metade dos episodios cai na quarentena")

    def test_o_programa_esta_na_lista_de_programas_de_entrevista(self):
        from recolha.modelos import carregar_config

        config = carregar_config()
        self.assertIn(self.fonte.programa, config.prova_de_formato.programas)

    def test_pagina_e_um_parametro_do_endereco(self):
        self.assertTrue(any("{pagina}" in u for u in self.fonte.busca), "sem {pagina} a fonte le sempre a mesma")

    def test_uma_consulta_so(self):
        self.assertEqual(len(self.fonte.termos_busca), 1, "o endereco nao usa {termo}: mais termos so repetem o pedido")


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


class TestRitmoPorFonte(unittest.TestCase):
    """O ritmo e por fonte: um motor externo responde 429 a uma cadencia
    que o site de um canal aceita sem se queixar."""

    def test_pausa_da_fonte_e_a_usada(self):
        esperas = []
        mock.patch.object(busca_site, "obter_texto", side_effect=obter_falso).start()
        mock.patch.object(busca_site.time, "sleep", esperas.append).start()
        self.addCleanup(mock.patch.stopall)
        f = Fonte(id="m", tipo="busca_site", canal="rtp1", dominio="exemplo.pt",
                  busca=("https://exemplo.pt/pesquisa?q={termo}",), pausa_s=8.0)
        list(busca_site.FonteBuscaSite(f).obter(termos=["Ventura"]))
        self.assertTrue(esperas)
        self.assertEqual(set(esperas), {8.0})

    def test_configuracao_real_poupa_o_motor_externo(self):
        """As fontes que passam por um motor externo tem de esperar mais
        entre pedidos do que as que falam com o site de um canal."""
        from recolha.modelos import carregar_config

        for fonte_real in carregar_config().fontes:
            if fonte_real.tipo != "busca_site" or not fonte_real.busca:
                continue
            externo = any("brave" in u for u in fonte_real.busca)
            if externo:
                self.assertGreaterEqual(fonte_real.pausa_s, 5.0, fonte_real.id)
                self.assertEqual(len(fonte_real.termos_busca), 1, f"{fonte_real.id}: uma consulta por canal")