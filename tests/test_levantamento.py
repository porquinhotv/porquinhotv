"""Levantamento das fontes: tudo offline, com paginas e respostas fixas.

- a analise de HTML diz onde os termos aparecem e se ha video com duracao;
- o id de YouTube vem do canonical, nao do primeiro UC... que apareca;
- a resposta do arquivo.pt e contada por ano;
- a corrida completa nao faz um unico pedido real e escreve um relatorio
  com uma linha por canal, sem travessoes e em LF.
"""

import json
import tempfile
import unittest
from pathlib import Path

from tests.apoio import RAIZ, ler

from ferramentas import levantamento
from recolha.rede import ErroDeRede

TERMOS = ["Pessoa Exemplo", "entrevista", "exclusivo", "grande entrevista"]


class TestAnaliseDeHtml(unittest.TestCase):
    def test_onde_os_termos_aparecem(self):
        r = levantamento.analisar_html(ler("pagina_canal_exemplo.html"), TERMOS)
        self.assertEqual(r["termos_no_titulo"], ["Pessoa Exemplo", "entrevista"])
        self.assertIn("exclusivo", r["termos_nos_metadados"])
        self.assertIn("grande entrevista", r["termos_nos_metadados"])
        self.assertIn("exclusivo", r["termos_no_jsonld"])
        self.assertIn("Pessoa Exemplo", r["termos_no_corpo"])
        self.assertTrue(r["meta_keywords"])

    def test_video_com_duracao_e_feeds(self):
        r = levantamento.analisar_html(ler("pagina_canal_exemplo.html"), TERMOS)
        self.assertEqual(r["jsonld_blocos"], 3)
        self.assertEqual(r["jsonld_videos"], 1)
        self.assertEqual(r["jsonld_videos_com_duracao"], 1)
        self.assertEqual(r["feeds"], ["https://exemplo.pt/rss"])
        self.assertEqual(r["ids_youtube"], ["UCabcdefghijklmnopqrstuv"])

    def test_corpo_ignora_scripts(self):
        r = levantamento.analisar_html(ler("pagina_canal_exemplo.html"), ["carregado"])
        self.assertEqual(r["termos_no_corpo"], [])

    def test_pagina_vazia(self):
        r = levantamento.analisar_html("<html><body></body></html>", TERMOS)
        self.assertEqual(r["termos_no_corpo"], [])
        self.assertEqual(r["jsonld_blocos"], 0)
        self.assertEqual(r["bytes_texto"], 0)

    def test_duracao_iso(self):
        self.assertEqual(levantamento._duracao_iso("PT1H12M30S"), 4350)
        self.assertEqual(levantamento._duracao_iso("PT45M"), 2700)
        self.assertIsNone(levantamento._duracao_iso("1:12:30"))
        self.assertIsNone(levantamento._duracao_iso(""))


class TestYouTube(unittest.TestCase):
    def test_id_vem_do_canonical(self):
        self.assertEqual(levantamento.id_de_canal_youtube(ler("youtube_canal_exemplo.html")), "UCzyxwvutsrqponmlkjihgfe")

    def test_sem_canonical_usa_o_mais_frequente(self):
        html = "UCaaaaaaaaaaaaaaaaaaaaaa x UCbbbbbbbbbbbbbbbbbbbbbb y UCbbbbbbbbbbbbbbbbbbbbbb"
        self.assertEqual(levantamento.id_de_canal_youtube(html), "UCbbbbbbbbbbbbbbbbbbbbbb")

    def test_sem_id(self):
        self.assertIsNone(levantamento.id_de_canal_youtube("<html></html>"))


class TestArquivo(unittest.TestCase):
    def test_url(self):
        url = levantamento.url_arquivo("https://arquivo.pt/textsearch", "Pessoa Exemplo entrevista", "exemplo.pt", "2019-05-16", "2026-09-08", 200)
        self.assertIn("q=%22Pessoa+Exemplo+entrevista%22", url)
        self.assertIn("siteSearch=exemplo.pt", url)
        self.assertIn("from=20190516", url)
        self.assertIn("to=20260908", url)
        self.assertIn("maxItems=200", url)

    def test_contagem_por_ano(self):
        r = levantamento.ler_resposta_arquivo(ler("arquivo_exemplo.json"))
        self.assertEqual(r["total_estimado"], 37)
        self.assertEqual(r["itens_lidos"], 3)
        self.assertEqual(r["por_ano"], {"2020": 2, "2023": 1})
        self.assertEqual(r["exemplos"][0]["data"], "20200301")

    def test_resposta_vazia(self):
        r = levantamento.ler_resposta_arquivo('{"response_items": []}')
        self.assertEqual(r["total_estimado"], 0)
        self.assertEqual(r["por_ano"], {})


class TestCorrida(unittest.TestCase):
    """Uma corrida completa contra um `obter` falso. Nenhum pedido real."""

    def _obter(self, url):
        self.pedidos.append(url)
        if "youtube.com/@" in url:
            return ler("youtube_canal_exemplo.html")
        if "textsearch" in url:
            return ler("arquivo_exemplo.json")
        if "falha" in url:
            raise ErroDeRede("pedido falhou: " + url)
        return ler("pagina_canal_exemplo.html")

    def setUp(self):
        self.pedidos = []
        self.config = {
            "arquivo": {"api": "https://arquivo.pt/textsearch", "max_itens": 10, "termos_extra": ["entrevista"], "pausa_s": 0},
            "termos_formato": ["entrevista"],
            "canais": [
                {"id": "rtp1", "dominios": ["exemplo.pt"], "paginas": ["https://exemplo.pt/", "https://exemplo.pt/pesquisa?q={termo}"], "youtube": ["exemplo"]},
                {"id": "cmtv", "dominios": ["exemplo.pt"], "paginas": ["https://falha.pt/"], "youtube": ["exemplo"]},
            ],
        }

    def test_corrida_e_relatorio(self):
        r = levantamento.correr(self.config, obter=self._obter, dormir=lambda s: None)
        self.assertEqual([c["canal"] for c in r["canais"]], ["rtp1", "cmtv"])
        primeiro, segundo = r["canais"]
        self.assertTrue(all(p["responde"] for p in primeiro["paginas"]))
        self.assertEqual(primeiro["youtube"][0]["channel_id"], "UCzyxwvutsrqponmlkjihgfe")
        self.assertIn("exemplo.pt", primeiro["arquivo"])
        self.assertFalse(segundo["paginas"][0]["responde"])
        # Handle e consultas ao arquivo.pt repetidos entre canais nao se pedem duas vezes.
        self.assertEqual(sum(1 for u in self.pedidos if "youtube.com/@" in u), 1)
        consultas = [u for u in self.pedidos if "textsearch" in u]
        self.assertEqual(len(consultas), len(set(consultas)))

        md = levantamento.relatorio(r)
        self.assertIn("| RTP1 |", md)
        self.assertIn("| CMTV |", md)
        self.assertIn("0/1", md)
        for t in ("\u2014", "\u2013"):
            self.assertNotIn(t, md)

    def test_escrita_em_lf(self):
        r = levantamento.correr(self.config, obter=self._obter, com_arquivo=False, dormir=lambda s: None)
        with tempfile.TemporaryDirectory() as pasta:
            levantamento.escrever(r, Path(pasta))
            for nome in ("levantamento.json", "LEVANTAMENTO.md"):
                self.assertNotIn(b"\r\n", (Path(pasta) / nome).read_bytes())
            json.loads((Path(pasta) / "levantamento.json").read_text(encoding="utf-8"))

    def test_configuracao_real_e_coerente(self):
        """Cada canal do levantamento existe no tema; nada de nomes novos."""
        cfg = levantamento.carregar()
        from recolha.modelos import carregar_config
        tema = carregar_config()
        ids = [c["id"] for c in cfg["canais"]]
        self.assertEqual(sorted(ids), sorted(tema.canais))
        self.assertEqual(len(ids), len(set(ids)))
        for c in cfg["canais"]:
            self.assertTrue(c.get("dominios"), c["id"])
            self.assertTrue(c.get("paginas"), c["id"])
        self.assertTrue((RAIZ / "config" / "levantamento.yml").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
