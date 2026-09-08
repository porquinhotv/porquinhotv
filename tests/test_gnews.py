"""Colheita do Google Noticias, sem rede.

O que importa travar: uma janela cheia truncada em silencio, um item
duplicado por duas consultas contado duas vezes, e a pasta de saida a
cair dentro do repositorio. O resto e leitura de XML.
"""

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tests.apoio import RAIZ, ler

from ferramentas import gnews
from recolha.rede import ErroDeRede

CONFIG = {
    "base": "https://motor.exemplo/rss/search",
    "parametros": {"hl": "pt-PT", "gl": "PT", "ceid": "PT:pt-150"},
    "consultas": ["Pessoa Exemplo entrevista"],
    "limiar_divisao": 90,
    "pausa_s": 0,
    "pausa_resolucao_s": 0,
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


class TestTriagem(unittest.TestCase):
    class SujeitoFalso:
        def aparece_em(self, texto):
            return "pessoa exemplo" in texto.lower()

    def _linhas(self):
        return [
            # grupo sujeito: nomeia a pessoa e diz entrevista
            {"data": "2024-01-13", "titulo": "A entrevista a Pessoa Exemplo na íntegra", "fonte": "Canal Notícias",
             "canal_por_fonte": "canal-noticias", "canal_no_titulo": "", "formato_no_titulo": "entrevista", "url_google": "u1"},
            # grupo programa: canal titula pelo programa, a pessoa fica na sinopse que o indice nao traz
            {"data": "2024-03-20", "titulo": "Grande Entrevista Episódio 12 - de 20 mar 2024", "fonte": "Canal Exemplo",
             "canal_por_fonte": "canal-generalista", "canal_no_titulo": "", "formato_no_titulo": "entrevista", "url_google": "u2"},
            # ruido: cita a pessoa, nada indica entrevista
            {"data": "2024-01-14", "titulo": "Pessoa Exemplo foi à convenção", "fonte": "Jornal",
             "canal_por_fonte": "", "canal_no_titulo": "", "formato_no_titulo": "", "url_google": "u3"},
            # ruido: diz entrevista, mas nem pessoa nem canal
            {"data": "2024-01-15", "titulo": "Entrevista a outra pessoa qualquer", "fonte": "Jornal",
             "canal_por_fonte": "", "canal_no_titulo": "", "formato_no_titulo": "entrevista", "url_google": "u4"},
        ]

    def test_dois_grupos_e_o_ruido_fica_de_fora(self):
        retidas = gnews.agrupar(CONFIG, self._linhas(), self.SujeitoFalso())
        self.assertEqual([(l["url_google"], l["grupo"]) for l in retidas], [("u1", "sujeito"), ("u2", "programa")])

    def test_episodio_de_programa_sem_o_nome_da_pessoa_e_retido(self):
        """O canal titula os episodios com o nome do programa e a data. Se
        a triagem exigisse o nome no titulo, perdiam-se todas as emissoes
        desse canal, que sao as que tem duracao declarada."""
        retidas = gnews.agrupar(CONFIG, self._linhas(), self.SujeitoFalso())
        self.assertIn("u2", [l["url_google"] for l in retidas])

    def test_ficheiros_de_triagem_escritos_com_as_colunas_de_decisao_primeiro(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            retidas = gnews.agrupar(CONFIG, self._linhas(), self.SujeitoFalso())
            gnews.gravar_triagem(pasta, retidas)
            cabecalho = (pasta / "triagem.csv").read_text(encoding="utf-8-sig").splitlines()[0]
            self.assertEqual(cabecalho.split(",")[:3], ["decisao", "prova_url", "duracao"])
            self.assertIn("<a href=", (pasta / "triagem.html").read_text(encoding="utf-8"))

    def test_resolver_so_toca_nos_triados(self):
        """Resolver a colheita inteira sao milhares de pedidos e horas de
        espera para linhas que ninguem vai abrir."""
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            gnews.gravar_csv(pasta, {l["url_google"]: {**l, "url_final": ""} for l in self._linhas()})
            gnews.gravar_triagem(pasta, gnews.agrupar(CONFIG, self._linhas(), self.SujeitoFalso()))
            pedidos = []

            def seguir(url):
                pedidos.append(url)
                return "https://canal.exemplo/peca", ""

            resumo = gnews.resolver(CONFIG, pasta, seguir_fn=seguir, dormir=lambda s: None)
            self.assertEqual(sorted(pedidos), ["u1", "u2"])
            self.assertEqual(resumo["resolvidas"], 2)



class TestDuracaoNoTexto(unittest.TestCase):
    CONFIG_D = {
        "padroes_duracao": [
            {"padrao": r"dura[çc][ãa]o(?:\s+total)?\s*:?\s*(\d{1,2})\s*h(?:oras?)?\s*(\d{1,2})\s*min", "unidades": ["h", "min"]},
            {"padrao": r"dura[çc][ãa]o(?:\s+total)?\s*:?\s*(\d{1,3})\s*min", "unidades": ["min"]},
            {"padrao": r"\b(\d{1,2}):([0-5]\d):([0-5]\d)\b", "unidades": ["h", "min", "s"]},
        ]
    }

    def test_horas_e_minutos_nao_sao_lidos_como_minutos_e_segundos(self):
        """A primeira versao dobrava tudo por sessenta a partir da direita
        e lia uma hora e doze minutos como 72 segundos. O numero sai
        plausivel, por isso o erro passaria despercebido no site."""
        self.assertEqual(gnews.duracao_no_texto(self.CONFIG_D, "duração total 1h 12min"), 4320)

    def test_minutos_sozinhos(self):
        self.assertEqual(gnews.duracao_no_texto(self.CONFIG_D, "Ep. 19 Duração: 51min Género: Informação"), 3060)

    def test_relogio(self):
        self.assertEqual(gnews.duracao_no_texto(self.CONFIG_D, "vídeo 00:47:42 fim"), 2862)

    def test_zero_nunca_e_duracao(self):
        self.assertIsNone(gnews.duracao_no_texto(self.CONFIG_D, "Duração: 0min"))

    def test_sem_padrao_fica_por_apurar(self):
        self.assertIsNone(gnews.duracao_no_texto(self.CONFIG_D, "uma pagina sem duracao nenhuma"))


class TestVerificacao(unittest.TestCase):
    class SujeitoFalso:
        def aparece_em(self, texto):
            return "pessoa exemplo" in texto.lower()

    CONFIG_V = {**TestDuracaoNoTexto.CONFIG_D, "separadores_programa": [" - ", " | ", ": "], "pausa_resolucao_s": 0}

    PAGINA_COM = (
        '<html><head><meta property="og:title" content="Grande Entrevista - Pessoa Exemplo - ep. 41">'
        '<meta name="description" content="A conversa com Pessoa Exemplo."></head>'
        "<body>Ep. 41 Duração: 51min</body></html>"
    )
    PAGINA_SEM = (
        '<html><head><meta property="og:title" content="Grande Entrevista - Outra Gente - ep. 12">'
        '<meta name="description" content="Outro convidado qualquer."></head>'
        "<body>Duração: 44min</body></html>"
    )

    def test_pagina_do_canal_diz_quem_foi_o_convidado(self):
        """O indice titula o episodio pelo nome do programa. Sem ler a
        pagina, 55 candidatos entravam na lista com o convidado errado."""
        r = gnews.verificar_pagina(self.CONFIG_V, self.PAGINA_COM, "https://canal.exemplo/e1", self.SujeitoFalso())
        self.assertEqual(r["sujeito_na_pagina"], "sim")
        self.assertEqual(r["duracao_na_pagina"], "3060")
        self.assertEqual(r["programa_na_pagina"], "Grande Entrevista")

    def test_episodio_de_outro_convidado_e_reprovado(self):
        r = gnews.verificar_pagina(self.CONFIG_V, self.PAGINA_SEM, "https://canal.exemplo/e2", self.SujeitoFalso())
        self.assertEqual(r["sujeito_na_pagina"], "nao")

    def _pasta_com_triagem(self, tmp):
        pasta = Path(tmp)
        linhas = [
            {"data": "2026-06-24", "titulo": "Grande Entrevista Episódio 19", "fonte": "Canal Exemplo",
             "canal_por_fonte": "canal-generalista", "canal_no_titulo": "", "formato_no_titulo": "entrevista",
             "url_google": "u1", "url_final": "https://canal.exemplo/e1"},
            {"data": "2026-04-08", "titulo": "Grande Entrevista Episódio 12", "fonte": "Canal Exemplo",
             "canal_por_fonte": "canal-generalista", "canal_no_titulo": "", "formato_no_titulo": "entrevista",
             "url_google": "u2", "url_final": "https://canal.exemplo/e2"},
        ]
        gnews.gravar_csv(pasta, {l["url_google"]: l for l in linhas})
        gnews.gravar_triagem(pasta, gnews.agrupar(self.CONFIG_V, linhas, self.SujeitoFalso()))
        return pasta

    def test_reprovacao_automatica_com_o_motivo_escrito(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = self._pasta_com_triagem(tmp)
            paginas = {"https://canal.exemplo/e1": self.PAGINA_COM, "https://canal.exemplo/e2": self.PAGINA_SEM}
            resumo = gnews.verificar(self.CONFIG_V, pasta, sujeito=self.SujeitoFalso(), obter=lambda u: paginas[u], dormir=lambda s: None)
            self.assertEqual((resumo["com_sujeito"], resumo["sem_sujeito"]), (1, 1))
            linhas = {l["url_google"]: l for l in csv.DictReader((pasta / "triagem.csv").open(encoding="utf-8-sig"))}
            self.assertEqual(linhas["u2"]["decisao"], "nao")
            self.assertIn("nao nomeia o sujeito", linhas["u2"]["nota"])
            self.assertEqual(linhas["u1"]["decisao"], "")
            self.assertEqual(linhas["u1"]["prova_url"], "https://canal.exemplo/e1")

    def test_decisao_ja_escrita_nunca_e_substituida(self):
        """A verificacao e um auxilio, nao um juiz. Apagar uma decisao de
        uma pessoa perderia trabalho que nao se repete."""
        with tempfile.TemporaryDirectory() as tmp:
            pasta = self._pasta_com_triagem(tmp)
            linhas = list(csv.DictReader((pasta / "triagem.csv").open(encoding="utf-8-sig")))
            for l in linhas:
                l["decisao"] = "sim"
            gnews.gravar_triagem(pasta, linhas)
            paginas = {"https://canal.exemplo/e1": self.PAGINA_COM, "https://canal.exemplo/e2": self.PAGINA_SEM}
            gnews.verificar(self.CONFIG_V, pasta, sujeito=self.SujeitoFalso(), obter=lambda u: paginas[u], dormir=lambda s: None)
            depois = {l["url_google"]: l for l in csv.DictReader((pasta / "triagem.csv").open(encoding="utf-8-sig"))}
            self.assertEqual(depois["u2"]["decisao"], "sim")

    def test_pagina_que_nao_responde_fica_anotada_e_nao_reprovada(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = self._pasta_com_triagem(tmp)

            def parte(url):
                raise ErroDeRede("403")

            resumo = gnews.verificar(self.CONFIG_V, pasta, sujeito=self.SujeitoFalso(), obter=parte, dormir=lambda s: None)
            self.assertEqual(resumo["sem_pagina"], 2)
            linhas = list(csv.DictReader((pasta / "triagem.csv").open(encoding="utf-8-sig")))
            self.assertEqual([l["decisao"] for l in linhas], ["", ""])
            self.assertIn("nao respondeu", linhas[0]["nota"])



if __name__ == "__main__":
    unittest.main(verbosity=2)
