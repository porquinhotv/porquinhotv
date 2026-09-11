"""Os plugins de fonte leem o que devem, e o registo curado e validado."""

import unittest
from pathlib import Path
from unittest.mock import patch

from tests.apoio import FIXTURES, RAIZ, config_teste, fonte, ler

from recolha import criterio
from recolha.fontes import manual, podcast_rss, youtube_feed
from recolha.modelos import carregar_config


class TestPodcast(unittest.TestCase):
    def test_le_itens_com_data(self):
        """Ate 2026-09-10 o item sem `itunes:duration` nem chegava a
        candidato. Sem duracao no projeto, um item com data e candidato
        como os outros: sao 7, nao 6."""
        itens, seguinte = podcast_rss.ler_feed(ler("podcast_exemplo.xml"))
        self.assertEqual(len(itens), 7)
        self.assertIsNone(seguinte)
        primeiro = next(i for i in itens if i.id_nativo == "ep-100")
        self.assertEqual(primeiro.publicado_em, "2025-09-05")
        self.assertNotIn("<p>", primeiro.descricao)
        self.assertIn("ep-sem-duracao", [i.id_nativo for i in itens])

    def test_corrida_completa_sobre_o_fixture(self):
        config = config_teste()
        f = fonte(config, "podcast-exemplo")
        with patch("recolha.fontes.podcast_rss.obter_texto", return_value=ler("podcast_exemplo.xml")):
            itens = list(podcast_rss.FontePodcastRss(f).obter())
        q = []
        aceites = [e for e in (criterio.avaliar(i, f, config, q) for i in itens) if e]
        aceites = criterio.resolver_blocos(aceites, q)
        self.assertEqual([e.id_nativo for e in itens].count("ep-100"), 1)
        # Duas entrevistas: a de ep-100 (declarada a 2025-09-04) e a do item
        # que so nao entrava por nao ter duracao, publicado a 2025-09-10.
        self.assertEqual(sorted(e.data for e in aceites), ["2025-09-04", "2025-09-10"])
        motivos = sorted(e["motivo"].split(" (")[0] for e in q)
        self.assertEqual(
            motivos,
            ["anterior_ao_inicio", "formato_nao_elegivel", "formato_nao_elegivel", "fragmento_ou_repetido", "sem_sujeito"],
        )


class TestYouTubeFeed(unittest.TestCase):
    def test_le_entradas(self):
        itens = youtube_feed.ler_feed(ler("youtube_exemplo.xml"))
        self.assertEqual(len(itens), 2)
        self.assertEqual(itens[0].url, "https://www.youtube.com/watch?v=abc123DEF45")
        self.assertEqual(itens[0].publicado_em, "2025-09-06")

    def test_o_video_titulado_como_entrevista_e_candidato(self):
        """Ate 2026-09-10 o feed de YouTube era so um detetor: tudo morria
        em `por_confirmar` por nao trazer duracao. Sem duracao, o video que
        o canal titula como entrevista passa o criterio (as rondas vem
        depois, em recolha/confirmacao.py) e o outro continua sem sujeito."""
        config = config_teste()
        f = fonte(config, "yt-exemplo")
        with patch("recolha.fontes.youtube_feed.obter_texto", return_value=ler("youtube_exemplo.xml")):
            itens = list(youtube_feed.FonteYouTubeFeed(f).obter())
        q = []
        aceites = [e for e in (criterio.avaliar(i, f, config, q) for i in itens) if e]
        self.assertEqual([e.titulo for e in aceites], ["Entrevista a André Ventura na íntegra"])
        self.assertEqual([e["motivo"] for e in q], ["sem_sujeito"])

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

    def test_le_o_clipping(self):
        itens = manual.ler_registo(FIXTURES / "clipping_exemplo.yml")
        self.assertEqual(len(itens), 2)

    def test_sem_prova_falha(self):
        with self.assertRaises(ValueError):
            manual.validar_linha({"data": "2025-01-01", "canal": "sic", "programa": "x"}, 1)

    def test_prova_tem_de_ser_url(self):
        with self.assertRaises(ValueError):
            manual.validar_linha({"data": "2025-01-01", "canal": "sic", "programa": "x", "prova": "vi na televisao"}, 1)

    def test_a_chave_de_agrupamento_na_linha_e_recusada(self):
        """`mesma_entrevista` saiu da linha a 2026-09-11 e passou para a
        tabela de config/curadoria.yml, porque tinha de funcionar tambem
        entre fontes diferentes. Ler a linha e deitar o campo fora em
        silencio deixava duas entrevistas a contar onde ha uma, que e o
        erro que este projeto considera o pior de todos."""
        linha = {"data": "2025-01-01", "canal": "sic", "prova": "https://exemplo.pt/a", "mesma_entrevista": "k"}
        with self.assertRaises(ValueError) as erro:
            manual.validar_linha(linha, 1)
        self.assertIn("curadoria.yml", str(erro.exception))

    def test_um_campo_retirado_e_recusado_e_nao_ignorado(self):
        """`duracao_s` e `parcial` sairam a 2026-09-10. Ler a linha e deitar
        o campo fora em silencio deixava no ficheiro um numero que quem o
        abre acreditava que o site usava; a recusa obriga a apaga-lo."""
        for campo, valor in (("duracao_s", 900), ("parcial", True)):
            with self.subTest(campo=campo), self.assertRaises(ValueError):
                manual.validar_linha({"data": "2025-01-01", "canal": "sic", "programa": "x", "prova": "https://x", campo: valor}, 1)

    def test_os_registos_reais_nao_trazem_campos_retirados(self):
        """Os 26 `duracao_s` do registo curado foram apagados nesse dia; se
        alguem os voltar a escrever, o coletor recusa a fonte inteira."""
        for nome in ("entrevistas.yml", "clipping.yml", "paginas_de_canal.yml"):
            with self.subTest(ficheiro=nome):
                manual.ler_registo(RAIZ / "config" / nome)

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
        self.assertEqual(config.fontes[0].id, "curadoria", "a decisao a mao corre a frente de tudo")
        self.assertLess(
            [f.id for f in config.fontes].index("registo-curado"),
            min(i for i, f in enumerate(config.fontes) if f.tipo != "manual"),
            "o registo do canal tem de correr antes de qualquer fonte automatica",
        )
        clipping = next(f for f in config.fontes if f.id == "clipping-imprensa")
        self.assertEqual(clipping.origem, "imprensa")
        self.assertGreater(
            [f.id for f in config.fontes].index("clipping-imprensa"),
            [f.id for f in config.fontes].index("registo-curado"),
            "a prova do canal e melhor do que a da imprensa e tem de correr primeiro",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
