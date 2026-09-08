"""Colheita do Google Noticias, sem rede.

O que importa travar: uma janela cheia truncada em silencio, um item
duplicado por duas consultas contado duas vezes, e a pasta de saida a
cair dentro do repositorio. O resto e leitura de XML.
"""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from tests.apoio import RAIZ, ler

from ferramentas import gnews

CONFIG = {
    "base": "https://motor.exemplo/rss/search",
    "parametros": {"hl": "pt-PT", "gl": "PT", "ceid": "PT:pt-150"},
    "consultas": ["Pessoa Exemplo entrevista"],
    "limiar_divisao": 90,
    "pausa_s": 0,
    "canais_por_texto": {"canal-generalista": ["Canal Exemplo"], "canal-noticias": ["Canal Notícias", "Canal Noticias"]},
    "canais_por_dominio": {"canal-noticias": ["canalnoticias.exemplo"], "canal-generalista": ["canal.exemplo"]},
    "marcadores_formato": {"entrevista": ["entrevista", "entrevistado"], "debate": ["debate"]},
}


class TestJanelas(unittest.TestCase):
    def test_primeira_janela_comeca_no_inicio_do_tema_e_nao_no_dia_um(self):
        janelas = gnews.janelas_mensais(date(2019, 5, 16), date(2019, 7, 10))
        self.assertEqual(janelas, [(date(2019, 5, 16), date(2019, 5, 31)), (date(2019, 6, 1), date(2019, 6, 30)), (date(2019, 7, 1), date(2019, 7, 10))])

    def test_dividir_uma_janela_nao_perde_nem_repete_dias(self):
        a, b = gnews.dividir((date(2024, 1, 1), date(2024, 1, 31)))
        self.assertEqual(a[0], date(2024, 1, 1))
        self.assertEqual(b[1], date(2024, 1, 31))
        self.assertEqual(a[1] + (b[0] - a[1]), b[0])
        self.assertEqual((b[0] - a[1]).days, 1)

    def test_url_leva_um_dia_de_folga_de_cada_lado(self):
        url = gnews.url_da_consulta(CONFIG, "x", (date(2024, 1, 1), date(2024, 1, 31)))
        self.assertIn("after%3A2023-12-31", url)
        self.assertIn("before%3A2024-02-01", url)
        self.assertIn("ceid=PT%3Apt-150", url)


class TestLeituraDoRss(unittest.TestCase):
    def test_le_titulo_fonte_data_e_ligacao(self):
        itens = gnews.ler_rss(ler("gnews_exemplo.xml"))
        self.assertEqual(len(itens), 3)
        self.assertEqual(itens[0]["data"], "2024-01-13")
        self.assertEqual(itens[0]["fonte"], "Canal Notícias")
        self.assertEqual(itens[0]["dominio_fonte"], "canalnoticias.exemplo")
        self.assertEqual(itens[0]["url_google"], "https://news.google.com/rss/articles/AAA111?oc=5")

    def test_titulo_sem_o_sufixo_da_fonte(self):
        """O RSS escreve 'Titulo - Fonte'. Guardado assim, a fonte
        apareceria duas vezes e a deteccao de canal no titulo daria o
        canal da fonte em vez do canal da entrevista."""
        itens = gnews.ler_rss(ler("gnews_exemplo.xml"))
        self.assertEqual(itens[0]["titulo"], 'Pessoa Exemplo: "Queremos uma taxa sobre lucros da banca"')
        self.assertFalse(itens[0]["titulo"].endswith("Canal Notícias"))


class TestClassificacao(unittest.TestCase):
    def test_canal_da_fonte_e_canal_do_titulo_sao_colunas_distintas(self):
        """Dois sites do mesmo grupo publicam o mesmo video um no outro: o
        canal que emitiu esta no titulo, nao no dominio que o alojou."""
        item = {"titulo": "A entrevista na Canal Notícias na íntegra", "fonte": "Canal Exemplo", "dominio_fonte": "www.canal.exemplo"}
        c = gnews.classificar(CONFIG, item)
        self.assertEqual(c["canal_por_fonte"], "canal-generalista")
        self.assertEqual(c["canal_no_titulo"], "canal-noticias")

    def test_nome_longo_ganha_ao_curto(self):
        self.assertEqual(gnews.canal_por_texto(CONFIG, "visto na Canal Noticias ontem"), "canal-noticias")

    def test_formato_indicado_e_so_indicativo(self):
        self.assertEqual(gnews.formato_no_titulo(CONFIG, "Entrevista e debate com X"), "entrevista+debate")
        self.assertEqual(gnews.formato_no_titulo(CONFIG, "Foram à convenção"), "")


class TestColheita(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name) / "saida"
        self.pedidos: list[str] = []

    def tearDown(self):
        self.tmp.cleanup()

    def _obter(self, resposta_por_url):
        def obter(url):
            self.pedidos.append(url)
            return resposta_por_url(url)
        return obter

    def test_janela_cheia_e_dividida_em_vez_de_truncada(self):
        """O RSS devolve no maximo cerca de cem itens. Um mes de campanha
        que devolvesse cem ficaria truncado sem aviso nenhum."""
        xml = ler("gnews_exemplo.xml")
        vazio = xml.split("<item>")[0] + "</channel></rss>"

        def resposta(url):
            # So a janela do mes inteiro tem as duas pontas; as metades vem vazias.
            return xml if "after%3A2023-12-31" in url and "before%3A2024-02-01" in url else vazio

        config = {**CONFIG, "limiar_divisao": 3}
        resumo = gnews.colher(config, self.pasta, date(2024, 1, 1), date(2024, 1, 31), obter=self._obter(resposta), dormir=lambda s: None)
        self.assertEqual(resumo["divisoes"], 1)
        self.assertEqual(len(self.pedidos), 3)

    def test_retomar_nao_repete_o_que_ja_foi_pedido(self):
        obter = self._obter(lambda url: ler("gnews_exemplo.xml"))
        gnews.colher(CONFIG, self.pasta, date(2024, 2, 1), date(2024, 2, 29), obter=obter, dormir=lambda s: None)
        gnews.colher(CONFIG, self.pasta, date(2024, 2, 1), date(2024, 2, 29), obter=obter, dormir=lambda s: None)
        self.assertEqual(len(self.pedidos), 1)

    def test_item_visto_por_duas_consultas_e_uma_linha(self):
        config = {**CONFIG, "consultas": ["a", "b"]}
        obter = self._obter(lambda url: ler("gnews_exemplo.xml"))
        resumo = gnews.colher(config, self.pasta, date(2024, 2, 1), date(2024, 2, 29), obter=obter, dormir=lambda s: None)
        self.assertEqual(resumo["linhas"], 3)
        linhas = gnews.ler_csv(self.pasta)
        self.assertEqual(linhas["https://news.google.com/rss/articles/AAA111?oc=5"]["consultas"], "a | b")

    def test_csv_ordenado_por_data_e_com_todas_as_colunas(self):
        obter = self._obter(lambda url: ler("gnews_exemplo.xml"))
        gnews.colher(CONFIG, self.pasta, date(2024, 2, 1), date(2024, 2, 29), obter=obter, dormir=lambda s: None)
        texto = (self.pasta / "candidatos.csv").read_text(encoding="utf-8-sig")
        cabecalho = texto.splitlines()[0]
        self.assertEqual(cabecalho.split(","), gnews.COLUNAS)
        datas = [l["data"] for l in gnews.ler_csv(self.pasta).values()]
        self.assertEqual(datas, sorted(datas))

    def test_resposta_bruta_fica_guardada(self):
        obter = self._obter(lambda url: ler("gnews_exemplo.xml"))
        gnews.colher(CONFIG, self.pasta, date(2024, 2, 1), date(2024, 2, 29), obter=obter, dormir=lambda s: None)
        self.assertEqual(len(list((self.pasta / "bruto").glob("*.xml"))), 1)


class TestPastaDeSaida(unittest.TestCase):
    def test_recusa_pasta_dentro_do_repositorio(self):
        """O CSV tem caminhos locais e o ritmo de trabalho de uma pessoa.
        Um commit por distracao punha isso no site."""
        with self.assertRaises(SystemExit):
            gnews.pasta_de_saida(str(RAIZ / "saida-local"))

    def test_aceita_pasta_fora(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(gnews.pasta_de_saida(tmp), Path(tmp).resolve())


class TestResolver(unittest.TestCase):
    def test_redirecionamento_http_e_seguido(self):
        final = gnews.resolver_url("https://news.google.com/rss/articles/X?oc=5", seguir_fn=lambda u: ("https://canal.exemplo/peca", ""))
        self.assertEqual(final, "https://canal.exemplo/peca")

    def test_pagina_do_motor_com_destino_no_atributo(self):
        corpo = '<html><body><c-wiz><a data-n-au="https://canal.exemplo/peca?a=1&amp;b=2">x</a></c-wiz></body></html>'
        final = gnews.resolver_url("https://news.google.com/rss/articles/X?oc=5", seguir_fn=lambda u: ("https://news.google.com/rss/articles/X", corpo))
        self.assertEqual(final, "https://canal.exemplo/peca?a=1&b=2")

    def test_sem_destino_fica_vazio_e_nao_inventa(self):
        final = gnews.resolver_url("https://news.google.com/rss/articles/X?oc=5", seguir_fn=lambda u: ("https://news.google.com/rss/articles/X", "<html></html>"))
        self.assertEqual(final, "")

    def test_falha_de_rede_deixa_vazio(self):
        def parte(u):
            raise OSError("sem rede")
        self.assertEqual(gnews.resolver_url("https://x", seguir_fn=parte), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
