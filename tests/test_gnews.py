"""Colheita do Google Noticias, sem rede.

O que importa travar: uma janela cheia truncada em silencio, um item
duplicado por duas consultas contado duas vezes, e a pasta de saida a
cair dentro do repositorio. O resto e leitura de XML.
"""

import contextlib
import csv
import io
import tempfile
import unittest
import unittest.mock
from types import SimpleNamespace
from datetime import date
from pathlib import Path

from tests.apoio import RAIZ, ler

import yaml

from ferramentas import gnews
from recolha.modelos import ProvaDeFormato, Sujeito, carregar_config, normalizar
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
    PAGINA_MODERNA = (
        '<html><body><c-wiz jscontroller="x"><div jsname="y" '
        'data-n-a-id="AU_yqLxyz" data-n-a-sg="ASSINATURA&amp;1" data-n-a-ts="1757000000">'
        "</div></c-wiz></body></html>"
    )
    RESPOSTA = (
        ")]}'\n\n"
        '[["wrb.fr","Fbv4je","[\\"garturlres\\",\\"https://canal.exemplo/peca\\"]",null,null,null,"generic"],["di",22]]'
    )

    def test_redirecionamento_http_e_seguido(self):
        final = gnews.resolver_url("https://news.google.com/rss/articles/X?oc=5", seguir_fn=lambda u: ("https://canal.exemplo/peca", ""))
        self.assertEqual(final, "https://canal.exemplo/peca")

    def test_formato_antigo_com_destino_no_atributo(self):
        corpo = '<html><body><c-wiz><a data-n-au="https://canal.exemplo/peca?a=1&amp;b=2">x</a></c-wiz></body></html>'
        final = gnews.resolver_url("https://news.google.com/rss/articles/X?oc=5", seguir_fn=lambda u: ("https://news.google.com/rss/articles/X", corpo))
        self.assertEqual(final, "https://canal.exemplo/peca?a=1&b=2")

    def test_formato_novo_pede_o_destino_ao_indice(self):
        """As ligacoes colhidas em 2026 trazem um identificador opaco e a
        pagina nao declara destino nenhum: a primeira versao devolveu
        vazio nas 150 e o passo seguinte nao teve nada para ler."""
        pedidos = []

        def publicar(url, dados):
            pedidos.append((url, dados.decode()))
            return self.RESPOSTA

        final = gnews.resolver_url(
            "https://news.google.com/rss/articles/AU_yqLxyz?oc=5",
            seguir_fn=lambda u: ("https://news.google.com/rss/articles/AU_yqLxyz", self.PAGINA_MODERNA),
            publicar_fn=publicar,
        )
        self.assertEqual(final, "https://canal.exemplo/peca")
        self.assertEqual(len(pedidos), 1)
        self.assertIn("AU_yqLxyz", pedidos[0][1])
        self.assertIn("1757000000", pedidos[0][1])

    def test_pedido_de_decode_e_json_valido(self):
        """Um pedido malformado devolve 400 e a coluna ficaria vazia sem
        que se percebesse se a culpa era do pedido ou do indice."""
        import json as _json

        pedido = gnews.PEDIDO_DECODE.format(id="AU_yqLxyz", ts="1757000000", sg="ASSINATURA")
        fora = _json.loads(pedido)
        dentro = _json.loads(fora[0][0][1])
        self.assertEqual(fora[0][0][0], "Fbv4je")
        self.assertEqual((dentro[0], dentro[2], dentro[3], dentro[4]), ("garturlreq", "AU_yqLxyz", 1757000000, "ASSINATURA"))

    def test_assinatura_com_entidade_html_e_desfeita(self):
        sg, ts = gnews.parametros_de_decode(self.PAGINA_MODERNA)
        self.assertEqual(sg, "ASSINATURA&1")
        self.assertEqual(ts, "1757000000")

    def test_sem_assinatura_fica_vazio_e_nao_inventa(self):
        final = gnews.resolver_url("https://news.google.com/rss/articles/X?oc=5", seguir_fn=lambda u: ("https://news.google.com/rss/articles/X", "<html></html>"))
        self.assertEqual(final, "")

    def test_resposta_sem_endereco_fica_vazia(self):
        final = gnews.resolver_url(
            "https://news.google.com/rss/articles/AU_yqLxyz?oc=5",
            seguir_fn=lambda u: ("https://news.google.com/rss/articles/AU_yqLxyz", self.PAGINA_MODERNA),
            publicar_fn=lambda u, d: ")]}'\n\n[[\"wrb.fr\",\"Fbv4je\",null,null,null,null,\"generic\"]]",
        )
        self.assertEqual(final, "")

    def test_falha_de_rede_deixa_vazio(self):
        def parte(u):
            raise OSError("sem rede")

        self.assertEqual(gnews.resolver_url("https://x", seguir_fn=parte), "")

    def test_limite_permite_sondar_sem_gastar_a_lista_toda(self):
        """A resolucao inteira sao 150 pedidos ao indice. Sondar cinco
        antes de os gastar todos e o que faltou da primeira vez."""
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            linhas = {f"u{i}": {"url_google": f"u{i}", "url_final": "", "data": "2026-01-0{}".format(i % 9 + 1), "titulo": "t"} for i in range(20)}
            gnews.gravar_csv(pasta, linhas)
            pedidos = []

            def seguir(url):
                pedidos.append(url)
                return "https://canal.exemplo/peca", ""

            gnews.resolver(CONFIG, pasta, so_triados=False, limite=5, seguir_fn=seguir, dormir=lambda s: None)
            self.assertEqual(len(pedidos), 5)



class TestVerificacao(unittest.TestCase):
    class SujeitoFalso:
        def aparece_em(self, texto):
            return "pessoa exemplo" in texto.lower()

    CONFIG_V = {"separadores_programa": [" - ", " | ", ": "], "pausa_resolucao_s": 0}

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
        self.assertEqual(r["programa_na_pagina"], "Grande Entrevista")
        # A pagina escreve "Duração: 51min" no corpo e a leitura ignora-a:
        # a duracao saiu do projeto a 2026-09-10.
        self.assertNotIn("duracao_na_pagina", r)

    def test_episodio_de_outro_convidado_e_reprovado(self):
        r = gnews.verificar_pagina(self.CONFIG_V, self.PAGINA_SEM, "https://canal.exemplo/e2", self.SujeitoFalso())
        self.assertEqual(r["sujeito_na_pagina"], "nao")

    @staticmethod
    def _ler(pasta):
        """Fechar o ficheiro. Deixa-lo aberto enche a saida dos testes de
        ResourceWarning e esconde o que interessa ler."""
        with (pasta / "triagem.csv").open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

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
            linhas = {l["url_google"]: l for l in self._ler(pasta)}
            self.assertEqual(linhas["u2"]["decisao"], "nao")
            self.assertIn("nao nomeia o sujeito", linhas["u2"]["nota"])
            self.assertEqual(linhas["u1"]["decisao"], "")
            self.assertEqual(linhas["u1"]["prova_url"], "https://canal.exemplo/e1")

    def test_decisao_ja_escrita_nunca_e_substituida(self):
        """A verificacao e um auxilio, nao um juiz. Apagar uma decisao de
        uma pessoa perderia trabalho que nao se repete."""
        with tempfile.TemporaryDirectory() as tmp:
            pasta = self._pasta_com_triagem(tmp)
            linhas = self._ler(pasta)
            for l in linhas:
                l["decisao"] = "sim"
            gnews.gravar_triagem(pasta, linhas)
            paginas = {"https://canal.exemplo/e1": self.PAGINA_COM, "https://canal.exemplo/e2": self.PAGINA_SEM}
            gnews.verificar(self.CONFIG_V, pasta, sujeito=self.SujeitoFalso(), obter=lambda u: paginas[u], dormir=lambda s: None)
            depois = {l["url_google"]: l for l in self._ler(pasta)}
            self.assertEqual(depois["u2"]["decisao"], "sim")

    def test_pagina_que_nao_responde_fica_anotada_e_nao_reprovada(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = self._pasta_com_triagem(tmp)

            def parte(url):
                raise ErroDeRede("403")

            resumo = gnews.verificar(self.CONFIG_V, pasta, sujeito=self.SujeitoFalso(), obter=parte, dormir=lambda s: None)
            self.assertEqual(resumo["sem_pagina"], 2)
            linhas = self._ler(pasta)
            self.assertEqual([l["decisao"] for l in linhas], ["", ""])
            self.assertIn("nao respondeu", linhas[0]["nota"])



class TestEmitir(unittest.TestCase):
    CANAIS = {"canal-generalista", "canal-noticias"}
    CONFIG_E = {"canais_por_dominio": {"canal-noticias": ["canalnoticias.exemplo"], "canal-generalista": ["canal.exemplo"]}}

    def _pasta(self, tmp, linhas):
        pasta = Path(tmp)
        with (pasta / "triagem.csv").open("w", encoding="utf-8-sig", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=gnews.COLUNAS_TRIAGEM, lineterminator="\n", extrasaction="ignore")
            escritor.writeheader()
            for l in linhas:
                escritor.writerow({c: l.get(c, "") for c in gnews.COLUNAS_TRIAGEM})
        return pasta

    def test_so_entram_as_decididas_com_sim(self):
        linhas = [
            {"decisao": "sim", "prova_url": "https://canal.exemplo/a", "data": "2026-06-24", "programa_na_pagina": "Programa"},
            {"decisao": "nao", "prova_url": "https://canal.exemplo/b", "data": "2026-06-25"},
            {"decisao": "", "prova_url": "https://canal.exemplo/c", "data": "2026-06-26"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            saida, avisos = gnews.emitir(self.CONFIG_E, self._pasta(tmp, linhas), self.CANAIS)
        self.assertEqual(len(saida), 1)
        self.assertEqual(saida[0]["prova"], "https://canal.exemplo/a")

    def test_prova_de_imprensa_nao_entra(self):
        """Uma peca de um jornal sobre a entrevista nao e a emissao. A
        regra de que a prova e sempre o endereco do canal existe para
        isto, e ha um teste no projeto que falha se for violada."""
        linhas = [{"decisao": "sim", "prova_url": "https://jornal.exemplo/peca", "data": "2026-06-24"}]
        with tempfile.TemporaryDirectory() as tmp:
            saida, avisos = gnews.emitir(self.CONFIG_E, self._pasta(tmp, linhas), self.CANAIS)
        self.assertEqual(saida, [])
        self.assertEqual(len(avisos), 1)
        self.assertIn("fora dos nove canais", avisos[0])

    def test_mesma_emissao_vista_por_duas_fontes_e_uma_linha(self):
        """Tres linhas da triagem para o mesmo canal e dia sao a mesma
        emissao. Sem agrupar, o site contaria tres. Fica a primeira: sem
        duracao nao ha prova melhor do que outra, e a ordem da triagem e a
        mesma em todas as corridas."""
        linhas = [
            {"decisao": "sim", "prova_url": "https://canal.exemplo/curto", "data": "2026-06-03"},
            {"decisao": "sim", "prova_url": "https://canal.exemplo/integral", "data": "2026-06-03"},
            {"decisao": "sim", "prova_url": "https://canal.exemplo/outro", "data": "2026-06-03"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            saida, _ = gnews.emitir(self.CONFIG_E, self._pasta(tmp, linhas), self.CANAIS)
        self.assertEqual(len(saida), 1)
        self.assertEqual(saida[0]["prova"], "https://canal.exemplo/curto")

    def test_simulcast_fica_agrupado_e_conta_duas_vezes(self):
        """Dois canais no mesmo dia sao duas emissoes, agrupadas por
        `mesma_entrevista`. E a decisao editorial 3."""
        linhas = [
            {"decisao": "sim", "prova_url": "https://canal.exemplo/a", "data": "2026-06-03"},
            {"decisao": "sim", "prova_url": "https://canalnoticias.exemplo/b", "data": "2026-06-03"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            saida, _ = gnews.emitir(self.CONFIG_E, self._pasta(tmp, linhas), self.CANAIS)
        self.assertEqual(len(saida), 2)
        self.assertEqual({l["mesma_entrevista"] for l in saida}, {"2026-06-03"})
        self.assertEqual({l["canal"] for l in saida}, self.CANAIS)

    def test_emissao_sozinha_no_dia_nao_leva_chave_de_grupo(self):
        linhas = [{"decisao": "sim", "prova_url": "https://canal.exemplo/a", "data": "2026-06-24"}]
        with tempfile.TemporaryDirectory() as tmp:
            saida, _ = gnews.emitir(self.CONFIG_E, self._pasta(tmp, linhas), self.CANAIS)
        self.assertNotIn("mesma_entrevista", saida[0])

    def test_uma_triagem_antiga_com_colunas_de_duracao_nao_escreve_duracao(self):
        """O triagem.csv do autor ainda tem as colunas `duracao` e
        `duracao_na_pagina` da colheita de setembro. Le-se na mesma, e o
        que se escreve no registo nao traz o campo: se trouxesse, o
        coletor recusava a fonte inteira."""
        linhas = [{"decisao": "sim", "prova_url": "https://canal.exemplo/a", "data": "2026-06-24", "duracao": "1740"}]
        with tempfile.TemporaryDirectory() as tmp:
            saida, _ = gnews.emitir(self.CONFIG_E, self._pasta(tmp, linhas), self.CANAIS)
        self.assertNotIn("duracao_s", saida[0])
        self.assertNotIn("duracao", gnews.COLUNAS_TRIAGEM)
        self.assertNotIn("duracao_na_pagina", gnews.COLUNAS_TRIAGEM)

    def test_data_reescrita_pela_folha_de_calculo_e_lida(self):
        """O Excel devolve 20/03/2024 onde estava 2024-03-20. Cortar dez
        caracteres escrevia essa forma no registo publicado."""
        linhas = [{"decisao": "sim", "prova_url": "https://canal.exemplo/a", "data": "20/03/2024", "data_na_pagina": "20/03/2024"}]
        with tempfile.TemporaryDirectory() as tmp:
            saida, avisos = gnews.emitir(self.CONFIG_E, self._pasta(tmp, linhas), self.CANAIS)
        self.assertEqual(saida[0]["data"], "2024-03-20")
        self.assertEqual(avisos, [])

    def test_data_de_emissao_escrita_a_mao_ganha_a_da_pagina(self):
        """A pagina do canal declara a data de publicacao. Um artigo do
        canal publicado na terca sobre a entrevista de segunda deslocava a
        emissao um dia, e ninguem tinha onde corrigir."""
        linhas = [{"decisao": "sim", "prova_url": "https://canal.exemplo/a", "data": "2026-06-24", "data_na_pagina": "2026-06-24", "data_emissao": "23/06/2026"}]
        with tempfile.TemporaryDirectory() as tmp:
            saida, _ = gnews.emitir(self.CONFIG_E, self._pasta(tmp, linhas), self.CANAIS)
        self.assertEqual(saida[0]["data"], "2026-06-23")

    def test_data_ilegivel_fica_de_fora_com_aviso(self):
        linhas = [{"decisao": "sim", "prova_url": "https://canal.exemplo/a", "data": "marco de 2024"}]
        with tempfile.TemporaryDirectory() as tmp:
            saida, avisos = gnews.emitir(self.CONFIG_E, self._pasta(tmp, linhas), self.CANAIS)
        self.assertEqual(saida, [])
        self.assertIn("data ilegivel", avisos[0])

    def test_sim_com_acentos_ou_maiusculas(self):
        for escrito in ("sim", "SIM", " Sim "):
            linhas = [{"decisao": escrito, "prova_url": "https://canal.exemplo/a", "data": "2026-06-24"}]
            with tempfile.TemporaryDirectory() as tmp:
                saida, _ = gnews.emitir(self.CONFIG_E, self._pasta(tmp, linhas), self.CANAIS)
            self.assertEqual(len(saida), 1, escrito)

    def test_recusa_escrita_de_qualquer_maneira_fica_de_fora(self):
        """So entra o que diz sim. As formas de dizer nao sao muitas e
        nao se preveem todas; erro por defeito e a regra do projeto."""
        for escrito in ("nao", "não", "n", "NÃO", "talvez", ""):
            linhas = [{"decisao": escrito, "prova_url": "https://canal.exemplo/a", "data": "2026-06-24"}]
            with tempfile.TemporaryDirectory() as tmp:
                saida, _ = gnews.emitir(self.CONFIG_E, self._pasta(tmp, linhas), self.CANAIS)
            self.assertEqual(saida, [], escrito)

    def test_titulo_com_entidades_html_e_desfeito(self):
        linhas = [{"decisao": "sim", "prova_url": "https://canal.exemplo/a", "data": "2026-06-24", "titulo_na_pagina": "Andr&#233; e a entrevista"}]
        with tempfile.TemporaryDirectory() as tmp:
            saida, _ = gnews.emitir(self.CONFIG_E, self._pasta(tmp, linhas), self.CANAIS)
        self.assertEqual(saida[0]["titulo"], "André e a entrevista")

    def test_saida_ordenada_por_data(self):
        linhas = [
            {"decisao": "sim", "prova_url": "https://canal.exemplo/b", "data": "2026-08-01"},
            {"decisao": "sim", "prova_url": "https://canalnoticias.exemplo/a", "data": "2026-02-01"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            saida, _ = gnews.emitir(self.CONFIG_E, self._pasta(tmp, linhas), self.CANAIS)
        self.assertEqual([l["data"] for l in saida], ["2026-02-01", "2026-08-01"])

    def test_leitor_do_grupo_e_prova_valida(self):
        """O mesmo video e servido no site do canal e no seu leitor. Sem
        declarar o dominio do leitor, uma prova legitima era recusada
        como se fosse imprensa."""
        config = {"canais_por_dominio": {"canal-generalista": ["canal.exemplo", "leitor.exemplo"]}}
        linhas = [{"decisao": "sim", "prova_url": "https://leitor.exemplo/programa/x/video/1", "data": "2026-06-03"}]
        with tempfile.TemporaryDirectory() as tmp:
            saida, avisos = gnews.emitir(config, self._pasta(tmp, linhas), self.CANAIS)
        self.assertEqual(avisos, [])
        self.assertEqual(saida[0]["canal"], "canal-generalista")

    def test_canal_escrito_a_mao_ganha_ao_dominio(self):
        """Um dominio serve mais do que um canal do mesmo grupo. Quando a
        pessoa escreve o canal, e essa a decisao."""
        linhas = [{"decisao": "sim", "canal": "canal-noticias", "prova_url": "https://canal.exemplo/a", "data": "2026-06-24"}]
        with tempfile.TemporaryDirectory() as tmp:
            saida, _ = gnews.emitir(self.CONFIG_E, self._pasta(tmp, linhas), self.CANAIS)
        self.assertEqual(saida[0]["canal"], "canal-noticias")

    def test_registo_escrito_mantem_o_cabecalho(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "entrevistas.yml"
            caminho.write_text("---\n# comentario que documenta os campos\n\nentrevistas: []\n", encoding="utf-8")
            gnews.escrever_registo([{"data": "2026-06-24", "canal": "canal-generalista", "programa": "P", "prova": "https://canal.exemplo/a"}], caminho)
            texto = caminho.read_text(encoding="utf-8")
        self.assertIn("# comentario que documenta os campos", texto)
        self.assertIn("canal-generalista", texto)
        self.assertNotIn("\r", texto)



class TestPaginasDeCanal(unittest.TestCase):
    """As 150 provas em dominio de canal que estavam paradas a espera de um
    `sim` escrito a mao, padrao que o projeto abandonou a 2026-09-09."""

    # Configuracao editorial de exemplo, com as mesmas classes reais: o
    # passo de emissao le os termos daqui, como o criterio do coletor.
    EDITORIAL = SimpleNamespace(
        canais={"canal-noticias": None, "outro-canal": None},
        sujeito=Sujeito(id="p", nome="Pessoa Exemplo", detetar=("Pessoa Exemplo",)),
        exclusoes={"debate": ("debate", "frente a frente")},
        prova_de_formato=ProvaDeFormato(termos=("entrevista",), programas=("Grande Entrevista",)),
    )

    def _linha(self, **campos):
        base = {
            "prova_url": "https://canal.exemplo/entrevista",
            "sujeito_na_pagina": "sim",
            "data_na_pagina": "2026-06-23",
            "titulo_na_pagina": "Grande Entrevista - Pessoa Exemplo",
            "programa_na_pagina": "Grande Entrevista",
            "canal": "canal-noticias",
            "decisao": "",
        }
        return {**base, **campos}

    def _emitir(self, linhas, ja=None):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            gnews.gravar_triagem(pasta, linhas)
            return gnews.emitir_paginas_de_canal(CONFIG, pasta, self.EDITORIAL, ja or set())

    def test_um_resumo_de_debate_nao_se_escreve_como_entrevista(self):
        """Entrada real, primeira corrida: das cinco linhas escritas, tres
        eram resumos de debates ("o debate entre X e Y em tres minutos") e
        entraram porque a prova de formato so era aplicada no coletor. Um
        ficheiro do repositorio nao pode contar com o passo seguinte para
        limpar o que este escreveu."""
        entrevistas, avisos = self._emitir([self._linha(
            titulo_na_pagina="Caça, touradas e a coelha. O debate entre Pessoa Exemplo e Outra Gente em três minutos",
            programa_na_pagina="",
        )])
        self.assertEqual(entrevistas, [])
        self.assertTrue(any("formato nao elegivel" in a for a in avisos), avisos)

    def test_entrevista_a_outra_pessoa_no_mesmo_programa_nao_conta(self):
        """Entrada real: "Grande Entrevista - Outra Gente - ep. 11" prova o
        formato e nomeia um programa de entrevistas, e a pagina nomeia o
        sujeito nas etiquetas. A entrevista nao e a ele. Das 108 linhas
        vetadas a 2026-09-09, 74 eram deste tipo."""
        entrevistas, avisos = self._emitir([self._linha(
            titulo_na_pagina="Grande Entrevista - Outra Gente - ep. 11",
            programa_na_pagina="Grande Entrevista",
        )])
        self.assertEqual(entrevistas, [])
        self.assertIn("1 paginas: o titulo nao nomeia o sujeito", avisos)

    def test_um_recorte_sem_a_palavra_no_titulo_nao_conta(self):
        """Entrada real: um recorte de 91 segundos entrou como entrevista
        exclusiva. E o mesmo erro que a correcao d767742 travou nas fontes
        automaticas, repetido aqui por o passo nao aplicar a mesma regra."""
        entrevistas, avisos = self._emitir([self._linha(
            titulo_na_pagina="Pessoa Exemplo: «Não sou machista»",
            programa_na_pagina="Dois às 10",
        )])
        self.assertEqual(entrevistas, [])
        self.assertIn("1 paginas: o canal nao lhe chama entrevista", avisos)

    def test_entra_sem_ninguem_escrever_sim(self):
        """Eram 150 linhas paradas so porque o registo do canal exige uma
        aprovacao escrita por linha. Com a triagem em 851 linhas, exigir
        isso e nao publicar nada."""
        entrevistas, _ = self._emitir([self._linha()])
        self.assertEqual(len(entrevistas), 1)
        self.assertNotIn("duracao_s", entrevistas[0])

    def test_uma_recusa_escrita_trava_a_linha(self):
        """A avaliacao decide, a pessoa veta. E a unica intervencao humana
        que o processo pede."""
        entrevistas, avisos = self._emitir([self._linha(decisao="nao")])
        self.assertEqual(entrevistas, [])
        self.assertIn("1 paginas: vetada a mao", avisos)

    def test_uma_pagina_por_ler_nao_entra(self):
        """Nao sei nao e sim: uma pagina que nao respondeu nao prova nada,
        e o titulo do indice nao substitui a leitura."""
        entrevistas, avisos = self._emitir([self._linha(sujeito_na_pagina="", titulo_na_pagina="")])
        self.assertEqual(entrevistas, [])
        self.assertIn("1 paginas: por ler: a pagina nao respondeu", avisos)

    def test_o_registo_verificado_a_mao_ganha(self):
        """Quando uma pessoa ja leu a pagina daquela emissao, a linha dela
        e melhor prova e esta nao se repete."""
        entrevistas, avisos = self._emitir([self._linha()], ja={("canal-noticias", "2026-06-23")})
        self.assertEqual(entrevistas, [])
        self.assertIn("1 paginas: ja no registo verificado a mao", avisos)

    def test_prova_de_imprensa_e_ignorada_em_silencio(self):
        """Uma peca de jornal pertence ao --emitir --imprensa. Sao centenas
        e contá-las aqui enchia o ecra com o que nao e erro."""
        entrevistas, avisos = self._emitir([self._linha(prova_url="https://jornal.exemplo/peca", canal="")])
        self.assertEqual(entrevistas, [])
        self.assertEqual([a for a in avisos if "jornal" in a], [])

    def test_duas_linhas_do_mesmo_dia_e_canal_sao_uma_emissao(self):
        """Os canais publicam o video integral e os recortes em paginas
        diferentes. Fica a primeira, como no `emitir`: sem duracao nao ha
        forma de dizer qual e o integral, e as duas provam a emissao."""
        entrevistas, _ = self._emitir([
            self._linha(prova_url="https://canal.exemplo/recorte"),
            self._linha(prova_url="https://canal.exemplo/integral"),
        ])
        self.assertEqual(len(entrevistas), 1)
        self.assertEqual(entrevistas[0]["prova"], "https://canal.exemplo/recorte")


class TestMapasDeSitio(unittest.TestCase):
    """A via que chega ao arquivo do jornal pela porta da frente."""

    CONFIG_M = {
        **CONFIG,
        "pausa_por_dominio": {"jornal.exemplo": 300},
        "mapas": [{"nome": "Jornal Exemplo", "indice": "https://jornal.exemplo/sitemap_index.xml",
                   "prefixos": ["fact_check-sitemap"]}],
    }

    class SujeitoFalso:
        detetar = ("Pessoa Exemplo",)

        def aparece_em(self, texto):
            from recolha.modelos import ProvaDeFormato, Sujeito, carregar_config, normalizar, contem_palavra
            return contem_palavra(texto, self.detetar) is not None

    def _obter(self, url):
        if url.endswith("sitemap_index.xml"):
            return ler("mapa_indice_exemplo.xml")
        return ler("mapa_pecas_exemplo.xml")

    def test_do_indice_so_se_usam_os_mapas_das_pecas(self):
        """O indice real declara 37 mapas, de artigos a notificacoes push.
        O de artigos foi medido a 2026-09-09 e deu zero em 21: sao debates
        e pecas sobre redes sociais, nenhuma prova uma emissao."""
        alvos = gnews.mapas_a_usar(ler("mapa_indice_exemplo.xml"), ["fact_check-sitemap"])
        self.assertEqual(alvos, ["https://jornal.exemplo/fact_check-sitemap.xml",
                                 "https://jornal.exemplo/fact_check-sitemap2.xml"])

    def test_um_mapa_nao_tem_href_e_por_isso_le_se_por_loc(self):
        """Na primeira sondagem o mapa apareceu com zero ligacoes e isso
        leu-se como falha. Nao era: um mapa escreve <loc> e a funcao que
        colhe ligacoes procura href."""
        self.assertEqual(len(gnews.enderecos_do_mapa(ler("mapa_pecas_exemplo.xml"))), 4)

    def test_nome_dentro_de_outra_palavra_nao_conta(self):
        """Entrada real: um endereco do mapa de artigos era sobre outra
        pessoa cujo apelido contem o do sujeito. A deteccao e por palavra
        inteira e nao o apanha, mas o caso fica travado."""
        with tempfile.TemporaryDirectory() as tmp:
            resumo = gnews.colher_mapas(self.CONFIG_M, Path(tmp), sujeito=self.SujeitoFalso(),
                                        obter=self._obter, dormir=lambda s: None)
        self.assertEqual(resumo["com_o_nome"], 4)
        self.assertEqual(resumo["novas"], 2)

    def test_linhas_do_mapa_entram_com_a_prova_resolvida_e_sem_titulo(self):
        """Um mapa da um endereco e mais nada. As colunas do titulo e da
        data ficam vazias de proposito: quem as preenche e o --verificar,
        com o mesmo extrator de qualquer outra peca."""
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            gnews.colher_mapas(self.CONFIG_M, pasta, sujeito=self.SujeitoFalso(),
                               obter=self._obter, dormir=lambda s: None)
            with (pasta / "triagem.csv").open(encoding="utf-8-sig", newline="") as f:
                linhas = list(csv.DictReader(f))
        self.assertEqual([l["grupo"] for l in linhas], ["imprensa", "imprensa"])
        self.assertTrue(all(l["prova_url"] == l["url_google"] for l in linhas))
        self.assertTrue(all(l["titulo"] == "" and l["data"] == "" for l in linhas))

    def test_uma_linha_ja_na_triagem_nao_se_repete_nem_se_reescreve(self):
        """O ficheiro de trabalho funde, nunca grava por cima: a decisao
        que uma pessoa escreveu nao se perde porque a colheita passou
        outra vez pelo mesmo endereco."""
        url = "https://jornal.exemplo/fact-check/entrevista-a-pessoa-exemplo-no-canal/"
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            gnews.gravar_triagem(pasta, [{"url_google": url, "prova_url": url, "decisao": "nao",
                                          "grupo": "imprensa", "nota": "vetada a mao"}])
            resumo = gnews.colher_mapas(self.CONFIG_M, pasta, sujeito=self.SujeitoFalso(),
                                        obter=self._obter, dormir=lambda s: None)
            with (pasta / "triagem.csv").open(encoding="utf-8-sig", newline="") as f:
                linhas = list(csv.DictReader(f))
        self.assertEqual(resumo["novas"], 1)
        antiga = [l for l in linhas if l["url_google"] == url]
        self.assertEqual(len(antiga), 1)
        self.assertEqual(antiga[0]["decisao"], "nao")

    def test_limite_para_a_corrida_para_se_medir_antes_de_gastar(self):
        """A corrida completa sobre o dominio real leva cerca de 18 horas.
        Uma amostra do primeiro mapa custa menos de uma hora e diz se as
        18 se pagam."""
        with tempfile.TemporaryDirectory() as tmp:
            resumo = gnews.colher_mapas(self.CONFIG_M, Path(tmp), sujeito=self.SujeitoFalso(),
                                        limite=1, obter=self._obter, dormir=lambda s: None)
        self.assertEqual(resumo["novas"], 1)

    def test_pausa_e_a_que_o_dominio_pede_e_nao_arrasta_os_outros(self):
        """O robots.txt de um dos dominios pede 300 segundos. Uma pausa so
        para todos os dominios ou desrespeita esse, ou faz os outros
        esperar por nada."""
        self.assertEqual(gnews.pausa_do_dominio(self.CONFIG_M, "https://jornal.exemplo/peca", 2), 300)
        self.assertEqual(gnews.pausa_do_dominio(self.CONFIG_M, "https://www.jornal.exemplo/peca", 2), 300)
        self.assertEqual(gnews.pausa_do_dominio(self.CONFIG_M, "https://outro.exemplo/peca", 2), 2)


class TestProvaDeImprensa(unittest.TestCase):
    """O clipping deixou de ser ultimo recurso a 2026-09-08 e os anuncios
    contam desde 2026-09-09. O que estes testes travam: a data da peca a
    passar por data da emissao, um anuncio lido para tras e um relato
    lido para a frente, o canal do grupo trocado quando o lead nomeia
    dois, e a mesma entrevista a contar duas vezes por ter duas pecas."""

    CANAIS = {"canal-generalista", "canal-noticias"}
    CONFIG_I = {
        **CONFIG,
        "imprensa": {
            "relato": ["esteve", "disse", "garantiu", "justifica"],
            "anuncio": ["vai estar", "não perca", "será às", "dá hoje"],
            "ontem": ["ontem"],
            "amanha": ["amanhã"],
            "hoje": ["hoje", "esta noite"],
            "dias_da_semana": {"segunda-feira": 0, "terça-feira": 1, "quarta-feira": 2, "quinta-feira": 3, "sexta-feira": 4, "sábado": 5, "domingo": 6},
        },
    }
    PECA = "https://jornal.exemplo/politica/peca"

    class SujeitoFalso:
        def aparece_em(self, texto):
            return "pessoa exemplo" in texto.lower()

    def _pasta(self, tmp, linhas):
        pasta = Path(tmp)
        with (pasta / "triagem.csv").open("w", encoding="utf-8-sig", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=gnews.COLUNAS_TRIAGEM, lineterminator="\n", extrasaction="ignore")
            escritor.writeheader()
            for l in linhas:
                escritor.writerow({c: l.get(c, "") for c in gnews.COLUNAS_TRIAGEM})
        return pasta

    def _emitir(self, linhas, ja_no_canal=None):
        with tempfile.TemporaryDirectory() as tmp:
            return gnews.emitir_imprensa(self.CONFIG_I, self._pasta(tmp, linhas), self.CANAIS, ja_no_canal)

    def _linha(self, **campos):
        base = {
            "decisao": "sim",
            "prova_url": self.PECA,
            # A pagina foi lida: e o que distingue uma peca avaliavel de
            # uma que so tem o titulo do indice. Sem isto, todas as linhas
            # destes testes eram "por ler", que e o estado real das 112
            # que nao responderam.
            "sujeito_na_pagina": "sim",
            "data_na_pagina": "2026-06-23",
            "titulo_na_pagina": "\"A idade da reforma tinha de descer\": Pessoa Exemplo justifica voto contra",
            "descricao_na_pagina": "Pessoa Exemplo esteve esta segunda-feira no Grande Programa do Canal Notícias numa entrevista exclusiva.",
        }
        return {**base, **campos}

    def test_a_pagina_da_peca_guarda_o_lead(self):
        """O titulo de uma peca de jornal e a citacao; "numa entrevista
        exclusiva" esta na primeira frase. Sem guardar o lead, sete das
        doze entrevistas da CMTV encontradas a 2026-09-08 nao tinham a
        palavra em lado nenhum da triagem."""
        pagina = ler("peca_imprensa_exemplo.html")
        config = {**TestVerificacao.CONFIG_V}
        r = gnews.verificar_pagina(config, pagina, self.PECA, self.SujeitoFalso())
        self.assertEqual(r["sujeito_na_pagina"], "sim")
        self.assertIn("numa entrevista exclusiva", r["descricao_na_pagina"])
        self.assertEqual(r["data_na_pagina"], "2026-06-23")

    def test_peca_que_relata_entra_no_dia_da_emissao_e_nao_no_da_peca(self):
        """A peca saiu na terca sobre a entrevista de segunda. Escrever a
        data da peca deslocava a emissao um dia; foi um dos erros vistos no
        registo a 2026-09-08."""
        saida, avisos = self._emitir([self._linha()])
        self.assertEqual(avisos, [])
        self.assertEqual(len(saida), 1)
        self.assertEqual(saida[0]["data"], "2026-06-22")
        self.assertEqual(saida[0]["publicado_em"], "2026-06-23")
        self.assertEqual(saida[0]["canal"], "canal-noticias")
        self.assertNotIn("duracao_s", saida[0])
        self.assertNotIn("mesma_entrevista", saida[0])

    def test_dia_da_semana_igual_ao_da_peca_e_o_proprio_dia(self):
        linha = self._linha(data_na_pagina="2026-06-22")
        saida, _ = self._emitir([linha])
        self.assertEqual(saida[0]["data"], "2026-06-22")
        self.assertNotIn("publicado_em", saida[0])

    def test_ontem_recua_um_dia(self):
        linha = self._linha(descricao_na_pagina="Pessoa Exemplo esteve ontem no Canal Notícias em entrevista.")
        saida, _ = self._emitir([linha])
        self.assertEqual(saida[0]["data"], "2026-06-22")

    def test_sem_dia_fixado_a_linha_espera(self):
        """"Em entrevista ao canal, disse que..." nao diz quando. A data da
        peca nao serve de substituto: seria inventar um dia."""
        linha = self._linha(descricao_na_pagina="Em entrevista ao Canal Notícias, Pessoa Exemplo disse que nao teme eleicoes.")
        saida, avisos = self._emitir([linha])
        self.assertEqual(saida, [])
        self.assertIn("nao fixa o dia", avisos[0])

    def test_data_escrita_a_mao_ganha_a_leitura(self):
        linha = self._linha(descricao_na_pagina="Em entrevista ao Canal Notícias, Pessoa Exemplo disse que nao teme eleicoes.", data_emissao="20/06/2026")
        saida, avisos = self._emitir([linha])
        self.assertEqual(avisos, [])
        self.assertEqual(saida[0]["data"], "2026-06-20")

    def test_anuncio_conta_no_dia_que_anuncia(self):
        """"Da hoje entrevista, sera as 19h" e um anuncio. Ate 2026-09-09
        ficava de fora; conta desde entao por decisao do autor, no dia que
        a peca fixa, e nao no dia em que se leu."""
        linha = self._linha(
            titulo_na_pagina="Pessoa Exemplo: primeira entrevista hoje no Canal Notícias",
            descricao_na_pagina="Pessoa Exemplo dá hoje a primeira entrevista. Será às 19 horas no Grande Programa do Canal Notícias.",
        )
        saida, avisos = self._emitir([linha])
        self.assertEqual(avisos, [])
        self.assertEqual(saida[0]["data"], "2026-06-23")
        self.assertNotIn("publicado_em", saida[0])
        self.assertNotIn("como", saida[0])

    def test_amanha_avanca_um_dia(self):
        """Uma peca de segunda que diz "amanha" fala da entrevista de
        terca. Ler a data da peca punha a emissao um dia antes de existir."""
        linha = self._linha(descricao_na_pagina="Pessoa Exemplo dá amanhã uma entrevista ao Canal Notícias.")
        saida, _ = self._emitir([linha])
        self.assertEqual(saida[0]["data"], "2026-06-24")
        self.assertEqual(saida[0]["publicado_em"], "2026-06-23")

    def test_dia_da_semana_num_anuncio_le_se_para_a_frente(self):
        """"Nao perca, esta segunda-feira" numa peca de terca e a segunda
        seguinte, nao a vespera. Lida para tras, a emissao ficava uma
        semana antes de acontecer."""
        linha = self._linha(descricao_na_pagina="Não perca: Pessoa Exemplo em entrevista ao Canal Notícias esta segunda-feira.")
        saida, avisos = self._emitir([linha])
        self.assertEqual(avisos, [])
        self.assertEqual(saida[0]["data"], "2026-06-29")

    def test_relato_ganha_a_anuncio_sobre_a_mesma_emissao(self):
        """Duas pecas para a mesma (canal, data), uma de vespera a anunciar
        e outra do dia seguinte a relatar, ambas a um dia de distancia.
        Fica o relato: prova que aconteceu, o anuncio so que ia acontecer."""
        anuncio = self._linha(data_na_pagina="2026-06-21", prova_url="https://jornal.exemplo/antes",
                              descricao_na_pagina="Pessoa Exemplo dá amanhã uma entrevista ao Canal Notícias.")
        relato = self._linha(data_na_pagina="2026-06-23", prova_url="https://jornal.exemplo/depois",
                             descricao_na_pagina="Pessoa Exemplo esteve ontem no Canal Notícias em entrevista.")
        saida, avisos = self._emitir([anuncio, relato])
        self.assertEqual(len(saida), 1)
        self.assertEqual(saida[0]["prova"], "https://jornal.exemplo/depois")
        self.assertEqual(avisos, [])

    def test_duas_datas_a_um_dia_no_mesmo_canal_saem_como_aviso(self):
        """Um jornal diz "ontem" e outro "esta noite" depois da meia-noite,
        e a mesma entrevista fica com duas datas. Fundir era adivinhar
        qual esta certa; ficar calado era contar uma como duas."""
        a = self._linha(prova_url="https://jornal.exemplo/a", descricao_na_pagina="Pessoa Exemplo esteve ontem no Canal Notícias em entrevista.")
        b = self._linha(prova_url="https://jornal.exemplo/b", data_na_pagina="2026-06-24", descricao_na_pagina="Pessoa Exemplo esteve ontem no Canal Notícias em entrevista.")
        saida, avisos = self._emitir([a, b])
        self.assertEqual(len(saida), 2)
        self.assertEqual(len(avisos), 1)
        self.assertIn("possivel duplicado", avisos[0])
        self.assertIn("2026-06-22 e 2026-06-23", avisos[0])

    def test_sugestao_escrita_para_todas_as_linhas_e_nao_so_para_as_visitadas(self):
        """A 2026-09-09 o `--verificar` so escrevia a sugestao das paginas
        que visitou nessa corrida: as 150 ja verificadas antes e as 124 que
        nao responderam ficaram sem coluna, e o `--emitir --imprensa`
        devolveu zero sem ninguem perceber porque."""
        antiga = self._linha(sujeito_na_pagina="sim", url_google="u1")
        falhada = {"decisao": "", "prova_url": self.PECA, "titulo": "Pessoa Exemplo em entrevista", "url_google": "u2"}
        do_canal = self._linha(sujeito_na_pagina="sim", prova_url="https://canalnoticias.exemplo/v", url_google="u3")
        with tempfile.TemporaryDirectory() as tmp:
            pasta = self._pasta(tmp, [antiga, falhada, do_canal])
            resumo = gnews.sugerir_todas(self.CONFIG_I, pasta, self.CANAIS)
            with (pasta / "triagem.csv").open(encoding="utf-8-sig", newline="") as f:
                linhas = {l["url_google"]: l["sugestao"] for l in csv.DictReader(f)}
        self.assertTrue(linhas["u1"].startswith("sim: canal-noticias a 2026-06-22"))
        self.assertTrue(linhas["u2"].startswith("por ler"))
        self.assertTrue(linhas["u3"].startswith("prova do canal"))
        self.assertEqual((resumo["sim"], resumo["por_ler"], resumo["do_canal"]), (1, 1, 1))

    def test_pagina_que_nao_respondeu_nao_e_um_nao(self):
        """124 paginas nao responderam a 2026-09-09, umas a 403 e outras a
        recusar a maquina. Escrever "nao" nessas era afirmar que a peca
        nao prova nada quando ninguem a leu."""
        linha = {"prova_url": self.PECA, "titulo": "Pessoa Exemplo em entrevista ao Canal Notícias"}
        self.assertTrue(gnews.sugerir(self.CONFIG_I, linha, self.CANAIS).startswith("por ler"))

    def test_linha_sem_decisao_entra_pela_avaliacao(self):
        """Ate 2026-09-09 so entrava o que uma pessoa marcasse `sim`. Com a
        triagem a passar de 150 para 851 linhas ninguem escreve 851 sins, e
        o `--emitir --imprensa` devolvia zero com a suite toda a passar."""
        saida, avisos = self._emitir([self._linha(decisao="")])
        self.assertEqual(avisos, [])
        self.assertEqual(saida[0]["data"], "2026-06-22")

    def test_recusa_escrita_a_mao_trava_a_linha(self):
        """A coluna `decisao` deixou de mandar entrar e passou a mandar
        ficar de fora. Uma recusa e a unica forma de travar uma peca que a
        avaliacao aceitaria, e vale escrita como for."""
        for recusa in ("nao", "não", "n"):
            saida, avisos = self._emitir([self._linha(decisao=recusa)])
            self.assertEqual((saida, avisos), ([], []), recusa)

    def test_recusas_nao_decididas_saem_contadas_e_nao_uma_a_uma(self):
        """571 das 851 linhas sao recusadas. Escrever uma linha por cada
        no ecra escondia o desacordo, que e a peca marcada `sim` a ser
        recusada pela avaliacao."""
        muda = [self._linha(decisao="", prova_url=f"https://jornal.exemplo/{i}",
                            descricao_na_pagina="Pessoa Exemplo esteve esta segunda-feira em entrevista na televisão.")
                for i in range(3)]
        explicita = self._linha(decisao="sim", prova_url="https://jornal.exemplo/x",
                                descricao_na_pagina="Pessoa Exemplo esteve esta segunda-feira em entrevista na televisão.")
        saida, avisos = self._emitir(muda + [explicita])
        self.assertEqual(saida, [])
        self.assertEqual(len(avisos), 2)
        self.assertTrue(any(a.startswith("3 pecas: nao nomeia o canal") for a in avisos))

    def test_peca_que_data_a_entrevista_a_um_ano_de_distancia_fica_de_fora(self):
        """Peca real de 2023-03-10: "disse em entrevista ao canal em
        dezembro de 2021 (...), hoje um novo militante diz outra coisa".
        O "hoje" fala do presente, nao da entrevista, e a linha entrava com
        a data da peca. Um ano na frase da entrevista tira a leitura."""
        linha = self._linha(
            titulo_na_pagina="O partido perdeu militantes",
            descricao_na_pagina='Pessoa Exemplo disse em entrevista ao Canal Notícias em dezembro de 2021 que tinha 40.000 militantes, hoje um novo militante diz outra coisa.',
        )
        saida, avisos = self._emitir([linha])
        self.assertEqual(saida, [])
        self.assertIn("noutro periodo", avisos[0])

    def test_nome_duplamente_escapado_nao_vira_nome_de_programa(self):
        """Entrada real: uma pagina do NOW serve o nome com o & escapado
        (`Andr&amp;#233;`). Uma passagem so devolvia `Andr&#233;`, que
        chegou ao registo como nome de programa e se ve na pagina de
        Fontes. Como o nome escapado nao e igual ao do sujeito, a regra que
        recusa usar o nome do convidado como programa nao disparava."""
        pagina = ('<html><head><meta property="og:title" '
                  'content="Pessoa Exemplo: primeira entrevista hoje no Canal Not&amp;#237;cias">'
                  '</head><body></body></html>')
        dados = gnews.verificar_pagina(CONFIG, pagina, "https://jornal.exemplo/p", self.SujeitoFalso())
        self.assertNotIn("&#", dados["titulo_na_pagina"])
        self.assertNotIn("&#", dados["programa_na_pagina"])

    def test_a_mesma_nota_nao_se_repete_a_cada_corrida(self):
        """A celula de uma linha do Expresso tinha a mesma mensagem de 403
        seis vezes, uma por corrida do --verificar, e ficou ilegivel
        precisamente onde o motivo escrito e mais preciso."""
        linha = {}
        for _ in range(6):
            gnews.anotar(linha, "pagina nao respondeu: HTTP Error 403")
        self.assertEqual(linha["nota"], "pagina nao respondeu: HTTP Error 403")
        gnews.anotar(linha, "ligacao por resolver")
        self.assertEqual(linha["nota"], "pagina nao respondeu: HTTP Error 403 | ligacao por resolver")

    def test_pagina_por_ler_nao_e_avaliada_pelo_titulo_do_indice(self):
        """Entrada real: a peca do Expresso de 2026-02-05, cuja pagina
        responde 403. Sem lead, a avaliacao lia so o titulo do indice e
        recusava-a com um motivo que nao era o dela. Com um titulo do
        genero de "primeira entrevista hoje na CMTV" teria feito pior:
        publicava uma emissao a partir de uma pagina que ninguem abriu."""
        linha = self._linha(
            sujeito_na_pagina="",
            titulo_na_pagina="",
            descricao_na_pagina="",
            data_na_pagina="",
            data="2026-01-20",
            titulo="Pessoa Exemplo: primeira entrevista hoje no Canal Notícias",
        )
        novo, motivo = gnews.avaliar_peca(self.CONFIG_I, linha, self.CANAIS)
        self.assertIsNone(novo)
        self.assertEqual(motivo, gnews.MOTIVO_POR_LER)
        self.assertEqual(self._emitir([linha])[0], [])

    def test_a_sugestao_e_a_emissao_leem_a_mesma_linha_da_mesma_maneira(self):
        """A docstring do `avaliar_peca` prometia uma so leitura das
        regras. Era falso para as 112 linhas por ler: o `sugerir` parava e
        dizia "por ler", o `emitir_imprensa` avaliava e dizia outra coisa.
        Uma promessa publicada tem de ser verdadeira."""
        linha = self._linha(sujeito_na_pagina="", titulo_na_pagina="", descricao_na_pagina="")
        self.assertEqual(gnews.sugerir(self.CONFIG_I, linha, self.CANAIS), gnews.MOTIVO_POR_LER)
        self.assertEqual(gnews.avaliar_peca(self.CONFIG_I, linha, self.CANAIS)[1], gnews.MOTIVO_POR_LER)

    def test_ano_solto_e_longe_da_palavra_nao_trava_a_leitura(self):
        """Peca real de 2026-06-17: "Na entrevista a <canal>, ontem a noite
        (16 de junho), (...) subvencoes revogadas em 2005". A primeira
        versao da regra do ano cortou esta emissao, que estava certa e era
        de um canal com poucas linhas, por causa de um ano a 366
        caracteres da palavra a falar de outra coisa."""
        config = gnews.carregar()
        texto = ("Na entrevista ao canal, ontem à noite (16 de junho), o líder aproveitou o tempo de antena "
                 "para defender bandeiras do seu partido, da redução da idade mínima de acesso à reforma sem "
                 "penalizações até à eliminação das subvenções vitalícias para ex-políticos que as obtiveram "
                 "antes da revogação de tal privilégio em 2005.")
        self.assertFalse(gnews.entrevista_datada_por_extenso(config, texto))
        self.assertEqual(gnews.data_de_emissao(config, texto, "2026-06-17"), ("2026-06-16", "ontem"))

    def test_mes_com_ano_data_a_entrevista_esteja_onde_estiver(self):
        """Peca real de 2026: "Em novembro de 2020, o jornalista (...) foi
        criticado por uma entrevista que fez ao lider". O ano esta a 93
        caracteres da palavra, longe de mais para a janela, mas "novembro
        de 2020" e uma data por extenso e data a entrevista."""
        config = gnews.carregar()
        texto = ("Em novembro de 2020, o jornalista, que na altura ainda trabalhava no canal, foi duramente "
                 "criticado por uma entrevista que fez ao líder do partido.")
        self.assertTrue(gnews.entrevista_datada_por_extenso(config, texto))

    def test_ano_solto_colado_a_palavra_trava_a_leitura(self):
        config = gnews.carregar()
        self.assertTrue(gnews.entrevista_datada_por_extenso(config, "disse em entrevista ao canal em 2021 que tinha razão"))

    def test_ano_noutra_frase_nao_trava_a_leitura(self):
        """"Em entrevista, esta noite, ao canal (...). Recicla uma
        declaracao de 2019" e uma peca certa: o ano esta na frase da
        declaracao antiga, nao na da entrevista."""
        linha = self._linha(
            descricao_na_pagina="Em entrevista, esta noite, ao Canal Notícias, Pessoa Exemplo disse que os presos ganham mais. Recicla uma declaração de 2019 que já foi verificada.",
        )
        saida, avisos = self._emitir([linha])
        self.assertEqual(avisos, [])
        self.assertEqual(saida[0]["data"], "2026-06-23")

    def test_em_direto_nao_diz_em_que_dia_a_peca_foi_escrita(self):
        """"Abandonou a entrevista em direto" descreve como a emissao
        passou, nao quando a peca foi escrita. Como marcador de "hoje",
        punha a emissao no dia da peca, que era o dia seguinte."""
        config = gnews.carregar()
        texto = "Pessoa Exemplo abandonou a entrevista em direto. Os comentadores participavam na entrevista que o canal fez ao candidato."
        self.assertEqual(gnews.data_de_emissao(config, texto, "2025-11-02"), ("", ""))

    def test_a_sugestao_e_o_que_a_emissao_faria(self):
        """A pessoa decide a partir da coluna `sugestao`. Se a sugestao
        dissesse sim e a emissao recusasse, a triagem estaria a mentir."""
        linha = {**self._linha(), "sujeito_na_pagina": "sim"}
        self.assertEqual(gnews.sugerir(self.CONFIG_I, linha, self.CANAIS), "sim: canal-noticias a 2026-06-22 (segunda-feira)")
        sem_canal = {**linha, "descricao_na_pagina": "Pessoa Exemplo esteve esta segunda-feira em entrevista na televisão."}
        self.assertTrue(gnews.sugerir(self.CONFIG_I, sem_canal, self.CANAIS).startswith("nao: nao nomeia o canal"))
        sem_sujeito = {**linha, "sujeito_na_pagina": "nao"}
        self.assertTrue(gnews.sugerir(self.CONFIG_I, sem_sujeito, self.CANAIS).startswith("nao:"))
        do_canal = {**linha, "prova_url": "https://canalnoticias.exemplo/video"}
        self.assertEqual(gnews.sugerir(self.CONFIG_I, do_canal, self.CANAIS), "prova do canal: entra por --emitir")

    def test_anuncio_entra_se_uma_pessoa_escrever_a_data(self):
        linha = self._linha(
            descricao_na_pagina="Pessoa Exemplo dá hoje a primeira entrevista. Será às 19 horas no Grande Programa do Canal Notícias.",
            data_emissao="2026-06-23",
        )
        saida, avisos = self._emitir([linha])
        self.assertEqual(avisos, [])
        self.assertEqual(saida[0]["data"], "2026-06-23")

    def test_dia_da_semana_sem_verbo_a_linha_espera(self):
        """"Pessoa Exemplo em entrevista ao Canal esta segunda-feira" tanto
        pode ser a legenda de um video como a chamada para o que vem a
        seguir. Sem um verbo que diga para que lado se le, a segunda que
        passou e a que vem sao a mesma frase e errar e errar uma semana."""
        linha = self._linha(
            titulo_na_pagina="Pessoa Exemplo em entrevista ao Canal Notícias",
            descricao_na_pagina="Pessoa Exemplo em entrevista ao Canal Notícias esta segunda-feira.",
        )
        saida, avisos = self._emitir([linha])
        self.assertEqual(saida, [])
        self.assertIn("sem verbo", avisos[0])

    def test_ontem_sem_verbo_nao_e_ambiguo(self):
        """"Ontem" so tem um lado. Exigir um verbo aqui deixava de fora
        legendas como "Pessoa Exemplo ontem em entrevista ao canal"."""
        linha = self._linha(descricao_na_pagina="Pessoa Exemplo ontem em entrevista ao Canal Notícias.")
        saida, avisos = self._emitir([linha])
        self.assertEqual(avisos, [])
        self.assertEqual(saida[0]["data"], "2026-06-22")

    def test_peca_que_nao_nomeia_o_canal_fica_de_fora(self):
        linha = self._linha(descricao_na_pagina="Pessoa Exemplo esteve esta segunda-feira em entrevista na televisão.")
        saida, avisos = self._emitir([linha])
        self.assertEqual(saida, [])
        self.assertIn("nao nomeia o canal", avisos[0])

    def test_dois_canais_no_lead_e_a_pessoa_que_escolhe(self):
        """Um artigo de audiencias nomeia o canal da entrevista e os
        concorrentes. Escolher o primeiro que aparece e adivinhar."""
        linha = self._linha(descricao_na_pagina="Pessoa Exemplo esteve esta segunda-feira em entrevista no Canal Notícias, que bateu o Canal Exemplo.")
        saida, avisos = self._emitir([linha])
        self.assertEqual(saida, [])
        self.assertIn("mais de um canal", avisos[0])
        saida, avisos = self._emitir([{**linha, "canal": "canal-noticias"}])
        self.assertEqual(saida[0]["canal"], "canal-noticias")

    def test_nome_longo_nao_conta_tambem_como_o_curto(self):
        """"Canal Notícias" contem "Canal"; sem retirar o nome longo antes
        de procurar o curto, um so canal nomeado contava como dois."""
        config = {**self.CONFIG_I, "canais_por_texto": {"canal-generalista": ["Canal"], "canal-noticias": ["Canal Notícias"]}}
        self.assertEqual(gnews.canais_no_texto(config, "esteve no Canal Notícias"), ["canal-noticias"])

    def test_peca_que_nao_diz_entrevista_fica_de_fora(self):
        linha = self._linha(descricao_na_pagina="Pessoa Exemplo esteve esta segunda-feira no Canal Notícias e disse que nao teme eleicoes.")
        saida, avisos = self._emitir([linha])
        self.assertEqual(saida, [])
        self.assertIn("nao diz entrevista", avisos[0])

    def test_titulo_que_diz_debate_nao_e_entrevista(self):
        linha = self._linha(titulo_na_pagina="Debate: Pessoa Exemplo frente a rival no Canal Notícias")
        saida, avisos = self._emitir([linha])
        self.assertEqual(saida, [])
        self.assertIn("debate", avisos[0])

    def test_emissao_ja_no_registo_do_canal_nao_se_repete(self):
        saida, avisos = self._emitir([self._linha()], ja_no_canal={("canal-noticias", "2026-06-22")})
        self.assertEqual(saida, [])
        self.assertIn("ja no registo do canal", avisos[0])

    def test_pagina_do_canal_e_ignorada_neste_modo(self):
        """As provas do canal pertencem a `--emitir`. Aqui nao sao erro nem
        entram: seriam escritas no ficheiro errado."""
        linha = self._linha(prova_url="https://canalnoticias.exemplo/video")
        saida, avisos = self._emitir([linha])
        self.assertEqual((saida, avisos), ([], []))

    def test_duas_pecas_sobre_a_mesma_emissao_e_uma_linha(self):
        perto = self._linha(data_na_pagina="2026-06-22", prova_url="https://jornal.exemplo/a")
        longe = self._linha(data_na_pagina="2026-06-23", prova_url="https://outro.exemplo/b", descricao_na_pagina="Pessoa Exemplo esteve ontem no Canal Notícias em entrevista.")
        saida, _ = self._emitir([longe, perto])
        self.assertEqual(len(saida), 1)
        self.assertEqual(saida[0]["prova"], "https://jornal.exemplo/a")

    def test_simulcast_de_imprensa_fica_agrupado(self):
        a = self._linha(prova_url="https://jornal.exemplo/a")
        b = self._linha(prova_url="https://jornal.exemplo/b", descricao_na_pagina="Pessoa Exemplo esteve esta segunda-feira no Canal Exemplo em entrevista.")
        saida, _ = self._emitir([a, b])
        self.assertEqual([l["canal"] for l in saida], ["canal-generalista", "canal-noticias"])
        self.assertEqual({l["mesma_entrevista"] for l in saida}, {"2026-06-22"})

    def test_registo_do_canal_da_os_pares_ja_provados(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "entrevistas.yml"
            caminho.write_text("---\n# c\n\nentrevistas:\n- data: '2026-06-22'\n  canal: canal-noticias\n  programa: P\n  prova: https://canalnoticias.exemplo/v\n", encoding="utf-8")
            self.assertEqual(gnews.emissoes_do_registo(caminho), {("canal-noticias", "2026-06-22")})
            self.assertEqual(gnews.emissoes_do_registo(Path(tmp) / "nada.yml"), set())

    def test_configuracao_real_tem_as_regras_de_imprensa(self):
        config = gnews.carregar()
        for chave in ("relato", "anuncio", "ontem", "amanha", "hoje", "dias_da_semana"):
            self.assertIn(chave, config["imprensa"])
        self.assertEqual(len(config["imprensa"]["dias_da_semana"]), 7)


class TestTriagem(unittest.TestCase):
    """O que estes testes travam: a via da imprensa a ficar sem linhas por
    causa do titulo, e uma nova triagem a apagar decisoes ja tomadas."""

    class SujeitoFalso:
        def aparece_em(self, texto):
            return "pessoa exemplo" in texto.lower()

    def _linha(self, **campos):
        base = {"data": "2026-06-23", "titulo": "Pessoa Exemplo: \"A idade da reforma tinha de descer\"", "fonte": "Jornal Exemplo",
                "canal_por_fonte": "", "canal_no_titulo": "", "formato_no_titulo": "", "url_google": "u1",
                "consultas": "\"Pessoa Exemplo\" entrevista Canal"}
        return {**base, **campos}

    def _grupos(self, linhas):
        return {l["url_google"]: l["grupo"] for l in gnews.agrupar(CONFIG, linhas, self.SujeitoFalso())}

    def test_peca_de_jornal_titulada_com_a_citacao_entra_como_imprensa(self):
        """Sete das doze entrevistas da CMTV encontradas a 2026-09-08 nao
        tinham "entrevista" no titulo, e o clipping ficou vazio porque
        nenhuma linha chegava ao passo que le o lead. A consulta que a
        trouxe tem a palavra: e o sinal que o indice da de graca."""
        self.assertEqual(self._grupos([self._linha()]), {"u1": "imprensa"})

    def test_peca_sem_entrevista_no_titulo_nem_na_consulta_fica_de_fora(self):
        """Uma peca que cita o sujeito vinda de uma consulta sem a palavra e
        o ruido de sempre; retirar-lo era mandar milhares de linhas a uma
        pessoa."""
        self.assertEqual(self._grupos([self._linha(consultas="Goucha \"Pessoa Exemplo\"")]), {})

    def test_pagina_de_canal_nunca_e_imprensa(self):
        """Os grupos `sujeito` e `programa` nao mudam: uma pagina do canal
        com a citacao no titulo continua de fora, porque a prova do canal
        vai pelo criterio do titulo, nao pelo lead."""
        self.assertEqual(self._grupos([self._linha(canal_por_fonte="canal-generalista")]), {})
        self.assertEqual(self._grupos([self._linha(canal_por_fonte="canal-generalista", formato_no_titulo="entrevista")]), {"u1": "sujeito"})

    def test_nova_triagem_guarda_as_decisoes_anteriores(self):
        """A 2026-09-09 a triagem tinha 150 decisoes e o grupo `imprensa`
        ia acrescentar 666 linhas. O `--triar` gravava por cima e as 150
        desapareciam."""
        retidas = [self._linha(url_google="u1", grupo="sujeito"), self._linha(url_google="u2", grupo="imprensa")]
        anteriores = [{"url_google": "u1", "decisao": "sim", "prova_url": "https://canal.exemplo/e1", "sujeito_na_pagina": "sim", "grupo": "sujeito", "titulo": "antigo"}]
        fundidas = {l["url_google"]: l for l in gnews.fundir_triagem(retidas, anteriores)}
        self.assertEqual(fundidas["u1"]["decisao"], "sim")
        self.assertEqual(fundidas["u1"]["prova_url"], "https://canal.exemplo/e1")
        self.assertEqual(fundidas["u1"]["titulo"], "antigo")
        self.assertNotIn("decisao", fundidas["u2"])

    def test_linha_que_a_regra_deixou_de_reter_nao_desaparece(self):
        anteriores = [{"url_google": "u9", "decisao": "nao", "grupo": "programa", "titulo": "x"}]
        fundidas = gnews.fundir_triagem([self._linha()], anteriores)
        self.assertEqual([l["url_google"] for l in fundidas], ["u1", "u9"])

    def test_triar_funde_com_o_ficheiro_existente(self):
        with tempfile.TemporaryDirectory() as tmp, unittest.mock.patch.object(gnews, "carregar_config") as cfg:
            cfg.return_value.sujeito = self.SujeitoFalso()
            pasta = Path(tmp)
            gnews.gravar_csv(pasta, {"u1": self._linha()})
            gnews.gravar_triagem(pasta, [{**self._linha(), "grupo": "imprensa", "decisao": "sim", "prova_url": "https://jornal.exemplo/p"}])
            resumo = gnews.triar(CONFIG, pasta)
            with (pasta / "triagem.csv").open(encoding="utf-8-sig", newline="") as f:
                linhas = list(csv.DictReader(f))
        self.assertEqual(resumo["imprensa"], 1)
        self.assertEqual(linhas[0]["decisao"], "sim")
        self.assertEqual(linhas[0]["prova_url"], "https://jornal.exemplo/p")


class TestRendimento(unittest.TestCase):
    """O relatorio que decide se vale a pena colher com uma consulta nova.

    Sem ele, a escolha de consultas e feita por intuicao: foi assim que se
    propos alargar a via da imprensa com consultas apertadas nos mesmos
    termos de consultas largas que ja tinham corrido, que sao
    subconjuntos delas e trazem zero linhas novas.
    """

    class SujeitoFalso:
        def aparece_em(self, texto):
            return "pessoa exemplo" in (texto or "").lower()

    def _linha(self, url, titulo, consultas, fonte="Jornal Exemplo", canal_por_fonte="", formato=""):
        return {
            "data": "2026-06-24", "titulo": titulo, "fonte": fonte,
            "dominio_fonte": "jornal.exemplo", "canal_por_fonte": canal_por_fonte,
            "canal_no_titulo": "", "formato_no_titulo": formato,
            "url_google": url, "url_final": "", "consultas": consultas, "janelas": "2026-06",
        }

    def _pasta(self, tmp, linhas, triagem=()):
        pasta = Path(tmp)
        gnews.gravar_csv(pasta, {l["url_google"]: l for l in linhas})
        if triagem:
            gnews.gravar_triagem(pasta, list(triagem))
        return pasta

    def test_prova_publicada_e_atribuida_a_consulta_que_so_ela_trouxe(self):
        """A coluna que autoriza tirar uma consulta. Uma consulta com zero
        exclusivas nao custa uma linha; com uma, custa essa."""
        linhas = [self._linha("u1", "Pessoa Exemplo fala do pais", "consulta A")]
        triagem = [{**linhas[0], "grupo": "imprensa", "prova_url": "https://jornal.exemplo/peca"}]
        with tempfile.TemporaryDirectory() as tmp:
            pasta = self._pasta(tmp, linhas, triagem)
            resumo = gnews.rendimento(
                CONFIG, pasta, sujeito=self.SujeitoFalso(),
                provas={"jornal.exemplo/peca"},
            )
        self.assertEqual(resumo["consultas"], 1)
        self.assertEqual(resumo["provas_no_registo"], 1)

    def test_linha_trazida_por_duas_consultas_nao_e_exclusiva_de_nenhuma(self):
        """Somar a mesma linha as duas consultas como exclusiva dava um
        rendimento inventado: nenhuma das duas a traz sozinha."""
        linhas = [self._linha("u1", "Pessoa Exemplo em entrevista", "consulta A | consulta B", formato="entrevista")]
        with tempfile.TemporaryDirectory() as tmp:
            pasta = self._pasta(tmp, linhas)
            saida = io.StringIO()
            with contextlib.redirect_stdout(saida):
                gnews.rendimento(CONFIG, pasta, sujeito=self.SujeitoFalso(), provas=set())
        for linha in saida.getvalue().splitlines():
            if "consulta A" in linha or "consulta B" in linha:
                self.assertEqual(linha.split()[:2], ["1", "0"])

    def test_conta_as_linhas_que_so_o_sinal_na_consulta_deixou_de_fora(self):
        """O tecto do que consultas novas recuperam sem pedir nada a rede:
        a linha ja esta colhida e so nao entrou porque a consulta que a
        trouxe nao trazia a palavra do formato."""
        linhas = [
            self._linha("u1", "Pessoa Exemplo diz que o pais precisa de mudanca", "consulta sem a palavra"),
            self._linha("u2", "Outra gente qualquer", "consulta sem a palavra"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            pasta = self._pasta(tmp, linhas)
            with contextlib.redirect_stdout(io.StringIO()):
                resumo = gnews.rendimento(CONFIG, pasta, sujeito=self.SujeitoFalso(), provas=set())
        self.assertEqual(resumo["fora_por_sinal_da_consulta"], 1)

    def test_consulta_da_configuracao_que_nunca_trouxe_nada_e_dita(self):
        """Uma consulta muda e tempo de colheita gasto a cada corrida.
        Fica escrita, para se poder tirar."""
        linhas = [self._linha("u1", "Pessoa Exemplo em entrevista", "consulta A", formato="entrevista")]
        config = {**CONFIG, "consultas": ["consulta A", "consulta que nunca trouxe nada"]}
        with tempfile.TemporaryDirectory() as tmp:
            pasta = self._pasta(tmp, linhas)
            with contextlib.redirect_stdout(io.StringIO()):
                resumo = gnews.rendimento(config, pasta, sujeito=self.SujeitoFalso(), provas=set())
        self.assertEqual(resumo["mudas"], 1)


class TestConsultasDaConfiguracaoReal(unittest.TestCase):
    """As consultas sao a entrada do funil: um erro aqui nao da erro
    nenhum, so faz a colheita gastar horas a trazer o que ja tinha."""

    def setUp(self):
        self.consultas = gnews.carregar().get("consultas") or []

    def test_cada_consulta_nomeia_o_sujeito(self):
        """Uma linha so entra na triagem se o titulo nomear o sujeito.
        Uma consulta que nao o nomeia traz peças que o funil deita fora
        todas, e paga-se na mesma o tempo de as pedir."""
        sujeito = carregar_config().sujeito
        for consulta in self.consultas:
            with self.subTest(consulta=consulta):
                self.assertTrue(sujeito.aparece_em(consulta))

    def test_nao_ha_duas_consultas_com_o_mesmo_conjunto_de_termos(self):
        """Medido a 2026-09-09: as duas consultas que tinham os mesmos
        termos por ordens diferentes trouxeram 260 e 263 linhas e so 1 e
        4 exclusivas. Sao a mesma amostra do indice e a segunda custa
        cerca de 89 pedidos por corrida para repetir a primeira. Termos
        diferentes, sim: a que junta o nome de um canal trouxe 130 linhas
        que mais nenhuma trouxe."""
        vistos: dict[frozenset, str] = {}
        for consulta in self.consultas:
            termos = frozenset(normalizar(consulta).split())
            anterior = vistos.get(termos)
            self.assertIsNone(anterior, f"{consulta!r} repete os termos de {anterior!r}")
            vistos[termos] = consulta



class TestReferencia(unittest.TestCase):
    """A lista de referencia dirige a colheita e mede a cobertura. O que
    importa travar: uma janela que nao inclua o dia da emissao, uma
    consulta de canal a correr para o canal errado, um pedido repetido, e
    uma cobertura que diga "sem nada" com uma pista a um dia de distancia
    ou que diga "no site" com uma emissao a dois."""

    CONFIG = {
        **CONFIG,
        "dirigidas": {
            "folga_antes": 2,
            "folga_depois": 3,
            "consultas_gerais": ["Pessoa Exemplo entrevista"],
            "consultas_por_canal": {"canal-generalista": ["Pessoa Exemplo entrevista Canal"]},
        },
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name) / "saida"
        self.pasta.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _referencia(self, texto: str) -> list[dict]:
        caminho = Path(self.tmp.name) / "referencia.yml"
        caminho.write_text(texto, encoding="utf-8")
        return gnews.carregar_referencia(caminho)

    def test_le_a_data_escrita_como_data_ou_como_texto(self):
        """O YAML le `2025-03-18` como objeto de data e `'2025-03-18'`
        como texto; a ferramenta tem de ficar sempre com o ISO."""
        linhas = self._referencia("entrevistas:\n  - {data: 2025-03-18, canal: canal-generalista}\n  - {data: '2025-04-11', canal: canal-noticias, nota: x}\n")
        self.assertEqual([(l["data"], l["canal"]) for l in linhas], [("2025-03-18", "canal-generalista"), ("2025-04-11", "canal-noticias")])
        self.assertEqual(linhas[1]["nota"], "x")

    def test_recusa_linha_sem_canal_ou_com_data_torta(self):
        with self.assertRaises(ValueError):
            self._referencia("entrevistas:\n  - {data: 2025-03-18}\n")
        with self.assertRaises(ValueError):
            self._referencia("entrevistas:\n  - {data: 18/03/2025, canal: canal-generalista}\n")

    def test_janela_inclui_o_dia_a_vespera_e_os_tres_dias_seguintes(self):
        pedidos = gnews.pedidos_de_referencia(self.CONFIG, [{"data": "2025-03-18", "canal": "canal-noticias"}])
        self.assertEqual(pedidos, [("Pessoa Exemplo entrevista", (date(2025, 3, 16), date(2025, 3, 21)))])

    def test_consulta_do_canal_so_corre_para_esse_canal_e_nada_se_repete(self):
        referencia = [
            {"data": "2025-03-18", "canal": "canal-generalista"},
            {"data": "2025-03-18", "canal": "canal-generalista"},
            {"data": "2025-03-18", "canal": "canal-noticias"},
        ]
        pedidos = gnews.pedidos_de_referencia(self.CONFIG, referencia)
        consultas = [c for c, _ in pedidos]
        self.assertEqual(consultas, ["Pessoa Exemplo entrevista", "Pessoa Exemplo entrevista Canal"])

    def test_colheita_dirigida_partilha_o_estado_com_a_mensal(self):
        """Os dois modos escrevem o mesmo candidatos.csv e o mesmo estado:
        um pedido feito por um nao se repete pelo outro, e um item trazido
        pelos dois e uma linha."""
        pedidos: list[str] = []

        def obter(url):
            pedidos.append(url)
            return ler("gnews_exemplo.xml")

        referencia = [{"data": "2024-02-10", "canal": "canal-noticias"}]
        gnews.colher_dirigidas(self.CONFIG, self.pasta, referencia, obter=obter, dormir=lambda s: None)
        gnews.colher_dirigidas(self.CONFIG, self.pasta, referencia, obter=obter, dormir=lambda s: None)
        self.assertEqual(len(pedidos), 1)
        self.assertIn("after%3A2024-02-07", pedidos[0])
        self.assertIn("before%3A2024-02-14", pedidos[0])
        gnews.colher(self.CONFIG, self.pasta, date(2024, 2, 1), date(2024, 2, 29), obter=obter, dormir=lambda s: None)
        self.assertEqual(len(pedidos), 2)
        self.assertEqual(len(gnews.ler_csv(self.pasta)), 3)

    def _triagem(self, linhas):
        with (self.pasta / "triagem.csv").open("w", encoding="utf-8-sig", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=gnews.COLUNAS_TRIAGEM, lineterminator="\n")
            escritor.writeheader()
            for linha in linhas:
                escritor.writerow({c: linha.get(c, "") for c in gnews.COLUNAS_TRIAGEM})

    def test_cobertura_distingue_site_registo_pista_e_nada(self):
        """Quatro linhas, quatro estados, e a tolerancia de um dia nos dois
        sentidos: a pista a um dia conta, a emissao a dois nao."""
        self._triagem([
            {"sugestao": "sim: canal-noticias a 2025-01-25 (relato)", "prova_url": "https://jornal.exemplo/p", "sujeito_na_pagina": "sim"},
            {"sugestao": "prova do canal: entra por --emitir", "prova_url": "https://canal.exemplo/v/1", "data_na_pagina": "2025-05-29", "sujeito_na_pagina": "sim", "titulo_na_pagina": "x"},
            {"sugestao": "nao: a peca nao diz entrevista", "prova_url": "https://jornal.exemplo/q", "canal": "canal-noticias", "data_emissao": "2025-07-03", "sujeito_na_pagina": "sim"},
        ])
        referencia = [
            {"data": "2025-01-24", "canal": "canal-noticias", "nota": ""},
            {"data": "2025-03-18", "canal": "canal-generalista", "nota": ""},
            {"data": "2025-04-11", "canal": "canal-noticias", "nota": ""},
            {"data": "2025-05-27", "canal": "canal-generalista", "nota": ""},
            {"data": "2025-07-03", "canal": "canal-noticias", "nota": ""},
        ]
        emissoes = {("canal-generalista", "2025-03-19"), ("canal-noticias", "2025-04-13")}
        registos = {("canal-noticias", "2025-04-11")}
        with contextlib.redirect_stdout(io.StringIO()) as saida:
            resumo = gnews.cobertura(self.CONFIG, self.pasta, referencia, emissoes, registos, tolerancia=1)
        self.assertEqual(resumo, {"referencia": 5, "no_site": 1, "no_registo": 1, "com_pista": 1, "sem_nada": 2})
        texto = saida.getvalue()
        self.assertIn("2025-01-24  canal-noticias pistas: 1 avaliada", texto)
        self.assertIn("2025-03-18  canal-generalista site: 2025-03-19", texto)
        self.assertIn("2025-04-11  canal-noticias registo por publicar: 2025-04-11", texto)
        # A prova de canal esta a dois dias da linha de 27 de maio: fora da
        # tolerancia, e a linha fica "sem nada" em vez de ganhar uma pista
        # que nao e dela.
        self.assertIn("2025-05-27  canal-generalista sem nada", texto)
        # A recusa da avaliacao com canal escrito a mao nao e pista: o
        # motivo esta escrito e a linha nao prova nada.
        self.assertIn("2025-07-03  canal-noticias sem nada", texto)
        self.assertIn("sem nada, por ordem: 2025-05-27 canal-generalista, 2025-07-03 canal-noticias", texto)

    def test_cobertura_sem_triagem_nem_site_diz_sem_nada_e_nao_falha(self):
        with contextlib.redirect_stdout(io.StringIO()):
            resumo = gnews.cobertura(self.CONFIG, self.pasta, [{"data": "2025-01-24", "canal": "canal-noticias", "nota": ""}], set(), set())
        self.assertEqual(resumo["sem_nada"], 1)


class TestReferenciaReal(unittest.TestCase):
    """O ficheiro real: um canal com id errado ou uma data antes do inicio
    do tema pediriam janelas para nada, e uma consulta dirigida sem o
    sujeito traria peças que o funil deita fora todas."""

    def setUp(self):
        self.editorial = carregar_config()
        self.referencia = gnews.carregar_referencia()
        self.dirigidas = gnews.carregar().get("dirigidas") or {}

    def test_cada_linha_tem_um_canal_dos_nove_e_uma_data_no_tema(self):
        inicio = self.editorial.tema.desde
        for linha in self.referencia:
            with self.subTest(linha=linha):
                self.assertIn(linha["canal"], set(self.editorial.canais))
                self.assertGreaterEqual(linha["data"], inicio)

    def test_nao_ha_duas_linhas_iguais(self):
        pares = [(l["data"], l["canal"]) for l in self.referencia]
        self.assertEqual(len(pares), len(set(pares)))

    def test_cada_consulta_dirigida_nomeia_o_sujeito_e_o_canal_e_dos_nove(self):
        sujeito = self.editorial.sujeito
        for consulta in self.dirigidas.get("consultas_gerais") or []:
            with self.subTest(consulta=consulta):
                self.assertTrue(sujeito.aparece_em(consulta))
        for canal, consultas in (self.dirigidas.get("consultas_por_canal") or {}).items():
            with self.subTest(canal=canal):
                self.assertIn(canal, set(self.editorial.canais))
                for consulta in consultas:
                    self.assertTrue(sujeito.aparece_em(consulta))


if __name__ == "__main__":
    unittest.main(verbosity=2)
