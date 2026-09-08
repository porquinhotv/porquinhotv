"""Os plugins de fonte leem o que devem, e o registo curado e validado."""

import unittest
from pathlib import Path
from unittest.mock import patch

from tests.apoio import FIXTURES, RAIZ, config_teste, fonte, ler

from recolha import criterio
from recolha.fontes import manual, podcast_rss, youtube_feed
from recolha.modelos import carregar_config


class TestPodcast(unittest.TestCase):
    def test_le_itens_com_data_e_duracao(self):
        itens, seguinte = podcast_rss.ler_feed(ler("podcast_exemplo.xml"))
        self.assertEqual(len(itens), 6)  # o item sem duracao nem e candidato
        self.assertIsNone(seguinte)
        primeiro = next(i for i in itens if i.id_nativo == "ep-100")
        self.assertEqual((primeiro.duracao_s, primeiro.publicado_em), (2900, "2025-09-05"))
        self.assertNotIn("<p>", primeiro.descricao)

    def test_formatos_de_duracao(self):
        self.assertEqual(podcast_rss.duracao_em_segundos("01:02:03"), 3723)
        self.assertEqual(podcast_rss.duracao_em_segundos("45:00"), 2700)
        self.assertEqual(podcast_rss.duracao_em_segundos("2700"), 2700)
        self.assertEqual(podcast_rss.duracao_em_segundos("lixo"), 0)

    def test_corrida_completa_sobre_o_fixture(self):
        config = config_teste()
        f = fonte(config, "podcast-exemplo")
        with patch("recolha.fontes.podcast_rss.obter_texto", return_value=ler("podcast_exemplo.xml")):
            itens = list(podcast_rss.FontePodcastRss(f).obter())
        q = []
        aceites = [e for e in (criterio.avaliar(i, f, config, q) for i in itens) if e]
        aceites = criterio.resolver_blocos(aceites, q)
        self.assertEqual([e.id_nativo for e in itens].count("ep-100"), 1)
        self.assertEqual(len(aceites), 1)
        self.assertEqual(aceites[0].data, "2025-09-04")
        motivos = sorted(e["motivo"].split(" (")[0] for e in q)
        self.assertEqual(
            motivos,
            ["anterior_ao_inicio", "formato_nao_elegivel", "formato_nao_elegivel", "fragmento_ou_repetido", "sem_sujeito"],
        )


class TestYouTubeFeed(unittest.TestCase):
    def test_le_entradas_sem_duracao(self):
        itens = youtube_feed.ler_feed(ler("youtube_exemplo.xml"))
        self.assertEqual(len(itens), 2)
        self.assertIsNone(itens[0].duracao_s)
        self.assertEqual(itens[0].url, "https://www.youtube.com/watch?v=abc123DEF45")
        self.assertEqual(itens[0].publicado_em, "2025-09-06")

    def test_vai_para_por_confirmar_quando_tem_o_nome(self):
        config = config_teste()
        f = fonte(config, "yt-exemplo")
        with patch("recolha.fontes.youtube_feed.obter_texto", return_value=ler("youtube_exemplo.xml")):
            itens = list(youtube_feed.FonteYouTubeFeed(f).obter())
        q = []
        for i in itens:
            self.assertIsNone(criterio.avaliar(i, f, config, q))
        self.assertEqual(sorted(e["motivo"] for e in q), ["por_confirmar", "sem_sujeito"])

    def test_sem_channel_id_devolve_nada(self):
        config = config_teste()
        f = fonte(config, "yt-exemplo")
        vazia = type(f)(**{**f.__dict__, "channel_id": ""})
        self.assertEqual(list(youtube_feed.FonteYouTubeFeed(vazia).obter()), [])


class TestRegistoCurado(unittest.TestCase):
    def test_le_o_fixture(self):
        itens = manual.ler_registo(FIXTURES / "entrevistas_exemplo.yml")
        self.assertEqual(len(itens), 4)
        self.assertEqual(itens[0].data_declarada, "2025-09-04")
        self.assertTrue(itens[2].parcial)
        self.assertEqual(itens[0].mesma_entrevista, itens[1].mesma_entrevista)

    def test_linha_sem_duracao_e_valida_e_fica_sem_duracao(self):
        itens = manual.ler_registo(FIXTURES / "entrevistas_exemplo.yml")
        self.assertIsNone(itens[3].duracao_s)

    def test_le_o_clipping(self):
        itens = manual.ler_registo(FIXTURES / "clipping_exemplo.yml")
        self.assertEqual(len(itens), 2)
        self.assertIsNone(itens[0].duracao_s)

    def test_sem_prova_falha(self):
        with self.assertRaises(ValueError):
            manual.validar_linha({"data": "2025-01-01", "canal": "sic", "programa": "x", "duracao_s": 900}, 1)

    def test_prova_tem_de_ser_url(self):
        with self.assertRaises(ValueError):
            manual.validar_linha({"data": "2025-01-01", "canal": "sic", "programa": "x", "duracao_s": 900, "prova": "vi na televisao"}, 1)

    def test_duracao_zero_e_erro_e_nao_ausencia(self):
        """Sem duracao escreve-se omitindo o campo. Zero seria uma medicao."""
        with self.assertRaises(ValueError):
            manual.validar_linha({"data": "2025-01-01", "canal": "sic", "programa": "x", "duracao_s": 0, "prova": "https://x"}, 1)

    def test_os_registos_reais_sao_validos_e_usam_canais_conhecidos(self):
        """Falha em CI antes de publicar se alguem escrever um canal a mais."""
        config = carregar_config()
        for nome in ("entrevistas.yml", "clipping.yml"):
            for item in manual.ler_registo(RAIZ / "config" / nome):
                self.assertIn(item.canal, config.canais, f"{nome}: canal desconhecido {item.canal}")
                self.assertGreaterEqual(item.data_declarada, config.tema.desde, nome)


class TestConfig(unittest.TestCase):
    def test_canal_desconhecido_numa_fonte_e_erro_de_configuracao(self):
        import tempfile
        with tempfile.TemporaryDirectory() as pasta:
            fontes = Path(pasta) / "fontes.yml"
            fontes.write_text("fontes:\n  - id: x\n    tipo: podcast_rss\n    canal: canal-inventado\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                carregar_config(FIXTURES / "porquinho_teste.yml", fontes)

    def test_a_configuracao_real_carrega(self):
        config = carregar_config()
        self.assertEqual(len(config.canais), 9)
        self.assertEqual(config.tema.desde, "2019-05-16")
        self.assertEqual(config.fontes[0].id, "registo-curado", "o registo do canal tem de ser a primeira fonte")
        clipping = next(f for f in config.fontes if f.id == "clipping-imprensa")
        self.assertEqual(clipping.origem, "imprensa")
        self.assertGreater(
            [f.id for f in config.fontes].index("clipping-imprensa"),
            [f.id for f in config.fontes].index("registo-curado"),
            "o clipping e o ultimo recurso e tem de correr depois do registo do canal",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
