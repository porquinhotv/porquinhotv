"""Levantamento das fontes: tudo offline, com paginas e respostas fixas.

- a analise de HTML diz onde os termos aparecem e se ha video;
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

    def test_video_e_feeds(self):
        r = levantamento.analisar_html(ler("pagina_canal_exemplo.html"), TERMOS)
        self.assertEqual(r["jsonld_blocos"], 3)
        self.assertEqual(r["jsonld_videos"], 1)
        self.assertNotIn("jsonld_videos_com_duracao", r)
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


class TestYouTube(unittest.TestCase):
    def test_id_vem_do_canonical(self):
        self.assertEqual(levantamento.id_de_canal_youtube(ler("youtube_canal_exemplo.html")), "UCzyxwvutsrqponmlkjihgfe")

    def test_sem_canonical_usa_o_mais_frequente(self):
        html = "UCaaaaaaaaaaaaaaaaaaaaaa x UCbbbbbbbbbbbbbbbbbbbbbb y UCbbbbbbbbbbbbbbbbbbbbbb"
        self.assertEqual(levantamento.id_de_canal_youtube(html), "UCbbbbbbbbbbbbbbbbbbbbbb")

    def test_sem_id(self):
        self.assertIsNone(levantamento.id_de_canal_youtube("<html></html>"))


class TestMesclaComCorridasAnteriores(unittest.TestCase):
    """Uma corrida com --canal nao pode apagar o que outra ja verificou."""

    def test_carregar_sem_ficheiro(self):
        with tempfile.TemporaryDirectory() as pasta:
            self.assertEqual(levantamento.carregar_anterior(Path(pasta)), {})

    def test_carregar_ficheiro_ilegivel(self):
        with tempfile.TemporaryDirectory() as pasta:
            (Path(pasta) / "levantamento.json").write_text("nao e json", encoding="utf-8")
            self.assertEqual(levantamento.carregar_anterior(Path(pasta)), {})

    def test_canal_novo_substitui_so_o_seu(self):
        anteriores = {"rtp1": {"canal": "rtp1", "nome": "RTP1"}, "cmtv": {"canal": "cmtv", "nome": "CMTV"}}
        novo = {"canais": [{"canal": "cmtv", "nome": "CMTV novo"}]}
        combinado = levantamento.mesclar(novo, anteriores, ["rtp1", "cmtv", "sic"])
        self.assertEqual([c["canal"] for c in combinado["canais"]], ["rtp1", "cmtv"])
        self.assertEqual(combinado["canais"][1]["nome"], "CMTV novo")

    def test_ordem_segue_a_configuracao(self):
        anteriores = {"cmtv": {"canal": "cmtv"}, "rtp1": {"canal": "rtp1"}}
        combinado = levantamento.mesclar({"canais": []}, anteriores, ["rtp1", "cmtv"])
        self.assertEqual([c["canal"] for c in combinado["canais"]], ["rtp1", "cmtv"])

    def _minimo(self, canais):
        return {"verificado_em": "2026-09-08T00:00:00+00:00", "desde": "2019-05-16", "termos": [], "canais": canais}

    def test_round_trip_por_ficheiro(self):
        with tempfile.TemporaryDirectory() as pasta:
            p = Path(pasta)
            levantamento.escrever(self._minimo([{"canal": "rtp1", "nome": "RTP1", "paginas": [], "youtube": []}]), p)
            anteriores = levantamento.carregar_anterior(p)
            self.assertEqual(set(anteriores), {"rtp1"})
            combinado = levantamento.mesclar(self._minimo([{"canal": "cmtv", "nome": "CMTV", "paginas": [], "youtube": []}]), anteriores, ["rtp1", "cmtv"])
            levantamento.escrever(combinado, p)
            outra_vez = levantamento.carregar_anterior(p)
            self.assertEqual(set(outra_vez), {"rtp1", "cmtv"})


class TestForcaIPv4(unittest.TestCase):
    """Contorna o erro 'Network is unreachable' visto no runner do GitHub."""

    def test_getaddrinfo_forca_af_inet(self):
        import socket

        from recolha import rede

        vistos = []

        def falso(host, port, family=0, type=0, proto=0, flags=0):
            vistos.append(family)
            return []

        original = rede._getaddrinfo_original
        rede._getaddrinfo_original = falso
        try:
            socket.getaddrinfo("exemplo.pt", 443, socket.AF_UNSPEC)
        finally:
            rede._getaddrinfo_original = original
        self.assertEqual(vistos, [socket.AF_INET])


class TestCorrida(unittest.TestCase):
    """Uma corrida completa contra um `obter` falso. Nenhum pedido real."""

    def _obter(self, url):
        self.pedidos.append(url)
        if "youtube.com/@" in url:
            return ler("youtube_canal_exemplo.html")
        if "falha" in url:
            raise ErroDeRede("pedido falhou: " + url)
        return ler("pagina_canal_exemplo.html")

    def setUp(self):
        self.pedidos = []
        self.config = {
            "pausa_s": 0,
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
        self.assertFalse(segundo["paginas"][0]["responde"])
        # Um handle repetido entre canais nao se pede duas vezes.
        self.assertEqual(sum(1 for u in self.pedidos if "youtube.com/@" in u), 1)

        md = levantamento.relatorio(r)
        self.assertIn("| RTP1 |", md)
        self.assertIn("| CMTV |", md)
        self.assertIn("0/1", md)
        for t in ("\u2014", "\u2013"):
            self.assertNotIn(t, md)

    def test_escreve_a_cada_canal(self):
        """Se a corrida for interrompida a meio, o que ja foi apurado nao
        se perde: cada canal terminado dispara uma escrita parcial."""
        chamadas = []
        levantamento.correr(self.config, obter=self._obter, dormir=lambda s: None, escrever_a_cada_canal=lambda parcial: chamadas.append(len(parcial["canais"])))
        self.assertEqual(chamadas, [1, 2])

    def test_escrita_em_lf(self):
        r = levantamento.correr(self.config, obter=self._obter, dormir=lambda s: None)
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
