"""O criterio de inclusao, motivo a motivo."""

import unittest

from tests.apoio import config_teste, fonte, item

from recolha import criterio


class TestCorteDeData(unittest.TestCase):
    def setUp(self):
        self.config = config_teste()
        self.fonte = fonte(self.config, "podcast-exemplo")

    def test_anterior_ao_inicio_vai_para_quarentena(self):
        q = []
        r = criterio.avaliar(item(publicado_em="2019-05-15"), self.fonte, self.config, q)
        self.assertIsNone(r)
        self.assertEqual(q[0]["motivo"], "anterior_ao_inicio")

    def test_no_proprio_dia_de_inicio_entra(self):
        r = criterio.avaliar(item(publicado_em="2019-05-16"), self.fonte, self.config, [])
        self.assertIsNotNone(r)

    def test_o_corte_usa_a_data_de_emissao_e_nao_a_de_publicacao(self):
        q = []
        r = criterio.avaliar(
            item(publicado_em="2019-05-20", descricao="Entrevista emitida a 10 de maio."),
            self.fonte, self.config, q,
        )
        self.assertIsNone(r)
        self.assertEqual(q[0]["motivo"], "anterior_ao_inicio")


class TestSujeito(unittest.TestCase):
    def setUp(self):
        self.config = config_teste()

    def test_feed_sem_o_nome_e_rejeitado(self):
        q = []
        r = criterio.avaliar(item(titulo="Conversa com Beltrano"), fonte(self.config, "podcast-exemplo"), self.config, q)
        self.assertIsNone(r)
        self.assertEqual(q[0]["motivo"], "sem_sujeito")

    def test_nome_e_por_palavra_inteira(self):
        q = []
        r = criterio.avaliar(item(titulo="Aventuras na Venturaland"), fonte(self.config, "podcast-exemplo"), self.config, q)
        self.assertIsNone(r)

    def test_registo_curado_nao_precisa_do_nome_no_titulo(self):
        f = fonte(self.config, "registo-curado")
        r = criterio.avaliar(item(titulo="Jornal da Noite", canal="sic", programa="JN", data_declarada="2025-09-04"), f, self.config, [])
        self.assertIsNotNone(r)


class TestFormato(unittest.TestCase):
    def setUp(self):
        self.config = config_teste()
        self.fonte = fonte(self.config, "podcast-exemplo")

    def test_segmento_com_formato_debate_exclui(self):
        q = []
        r = criterio.avaliar(item(titulo="Debate: André Ventura frente a Fulano"), self.fonte, self.config, q)
        self.assertIsNone(r)
        self.assertEqual(q[0]["motivo"], "formato_nao_elegivel (debate)")

    def test_termo_de_exclusao_no_titulo(self):
        q = []
        r = criterio.avaliar(item(titulo="André Ventura reage ao relatório"), self.fonte, self.config, q)
        self.assertIsNone(r)
        self.assertEqual(q[0]["motivo"], "formato_nao_elegivel (declaracao)")

    def test_termo_de_exclusao_na_descricao_nao_exclui(self):
        r = criterio.avaliar(item(descricao="Falou-se do debate de ontem."), self.fonte, self.config, [])
        self.assertIsNotNone(r)

    def test_catch_all_da_o_programa_e_o_formato(self):
        r = criterio.avaliar(item(), self.fonte, self.config, [])
        self.assertEqual(r.programa, "Grande Conversa")
        self.assertEqual(r.canal, "sic-noticias")


class TestDuracaoECanal(unittest.TestCase):
    def setUp(self):
        self.config = config_teste()
        self.fonte = fonte(self.config, "podcast-exemplo")

    def test_fonte_automatica_sem_duracao_fica_por_confirmar(self):
        """Numa fonte automatica, sem duracao quer dizer nao verificado."""
        q = []
        r = criterio.avaliar(item(duracao_s=None), fonte(self.config, "yt-exemplo"), self.config, q)
        self.assertIsNone(r)
        self.assertEqual(q[0]["motivo"], "por_confirmar")
        self.assertTrue(q[0]["url"])

    def test_fonte_verificada_sem_duracao_entra_com_duracao_por_apurar(self):
        r = criterio.avaliar(
            item(duracao_s=None, canal="sic", programa="JN", data_declarada="2025-09-04"),
            fonte(self.config, "registo-curado"), self.config, [],
        )
        self.assertIsNotNone(r)
        self.assertIsNone(r.duracao_s)

    def test_nao_ha_duracao_minima(self):
        """Uma entrevista curta e uma entrevista curta. Ver METODOLOGIA 2."""
        for segundos in (60, 300, 599, 600):
            with self.subTest(segundos=segundos):
                self.assertIsNotNone(criterio.avaliar(item(duracao_s=segundos), self.fonte, self.config, []))

    def test_origem_vem_da_fonte(self):
        do_canal = criterio.avaliar(item(canal="sic", programa="JN", data_declarada="2025-09-04"), fonte(self.config, "registo-curado"), self.config, [])
        da_imprensa = criterio.avaliar(item(canal="sic", programa="JN", data_declarada="2025-09-04"), fonte(self.config, "clipping-imprensa"), self.config, [])
        self.assertEqual(do_canal.origem, "canal")
        self.assertEqual(da_imprensa.origem, "imprensa")

    def test_canal_desconhecido(self):
        q = []
        f = fonte(self.config, "registo-curado")
        r = criterio.avaliar(item(canal="sic-hd", programa="JN", data_declarada="2025-09-04"), f, self.config, q)
        self.assertIsNone(r)
        self.assertEqual(q[0]["motivo"], "canal_desconhecido")


class TestDatas(unittest.TestCase):
    def setUp(self):
        self.config = config_teste()
        self.fonte = fonte(self.config, "podcast-exemplo")

    def test_data_declarada_na_descricao(self):
        r = criterio.avaliar(item(publicado_em="2025-09-05", descricao="Entrevista emitida a 4 de setembro."), self.fonte, self.config, [])
        self.assertEqual((r.data, r.data_origem, r.publicado_em), ("2025-09-04", "declarada", "2025-09-05"))

    def test_sem_declaracao_usa_publicacao(self):
        r = criterio.avaliar(item(publicado_em="2025-09-05"), self.fonte, self.config, [])
        self.assertEqual((r.data, r.data_origem), ("2025-09-05", "publicacao"))

    def test_data_implausivel_e_ignorada(self):
        r = criterio.avaliar(item(publicado_em="2025-09-05", descricao="emitida a 4 de janeiro de 2020"), self.fonte, self.config, [])
        self.assertEqual(r.data_origem, "publicacao")

    def test_data_iso_no_texto(self):
        r = criterio.avaliar(item(publicado_em="2025-09-05", descricao="Gravado em 2025-09-03."), self.fonte, self.config, [])
        self.assertEqual((r.data, r.data_origem), ("2025-09-03", "declarada"))

    def test_registo_curado_declara_a_data(self):
        f = fonte(self.config, "registo-curado")
        r = criterio.avaliar(item(canal="sic", programa="JN", data_declarada="2025-09-04", publicado_em="2025-09-06"), f, self.config, [])
        self.assertEqual((r.data, r.data_origem), ("2025-09-04", "declarada"))


class TestIdentidadeEBlocos(unittest.TestCase):
    def setUp(self):
        self.config = config_teste()
        self.fonte = fonte(self.config, "podcast-exemplo")

    def test_id_e_determinista(self):
        a = criterio.avaliar(item(), self.fonte, self.config, [])
        b = criterio.avaliar(item(), self.fonte, self.config, [])
        self.assertEqual(a.id, b.id)
        self.assertEqual(a.bloco, b.bloco)

    def test_mesmo_bloco_fica_com_o_mais_longo(self):
        q = []
        curto = criterio.avaliar(item(id_nativo="a", duracao_s=720, publicado_em="2025-09-05"), self.fonte, self.config, [])
        longo = criterio.avaliar(item(id_nativo="b", duracao_s=2900, publicado_em="2025-09-05"), self.fonte, self.config, [])
        ficam = criterio.resolver_blocos([curto, longo], q)
        self.assertEqual([e.id for e in ficam], [longo.id])
        self.assertTrue(q[0]["motivo"].startswith("fragmento_ou_repetido"))
        self.assertEqual(q[0]["id_nativo"], curto.id)

    def test_com_duracao_ganha_a_sem_duracao(self):
        """A mesma emissao provada duas vezes fica com a prova melhor,
        seja qual for a ordem por que aparece."""
        f = fonte(self.config, "registo-curado")
        com = criterio.avaliar(item(id_nativo="a", duracao_s=1800, canal="sic", programa="JN", data_declarada="2025-09-04"), f, self.config, [])
        sem = criterio.avaliar(item(id_nativo="b", duracao_s=None, canal="sic", programa="JN", data_declarada="2025-09-04"), f, self.config, [])
        self.assertEqual([e.id for e in criterio.resolver_blocos([sem, com], [])], [com.id])
        self.assertEqual([e.id for e in criterio.resolver_blocos([com, sem], [])], [com.id])

    def test_duas_sem_duracao_fica_a_primeira(self):
        f = fonte(self.config, "registo-curado")
        a = criterio.avaliar(item(id_nativo="a", duracao_s=None, canal="sic", programa="JN", data_declarada="2025-09-04"), f, self.config, [])
        b = criterio.avaliar(item(id_nativo="b", duracao_s=None, canal="sic", programa="JN", data_declarada="2025-09-04"), f, self.config, [])
        self.assertEqual([e.id for e in criterio.resolver_blocos([a, b], [])], [a.id])

    def test_empate_fica_com_o_primeiro(self):
        a = criterio.avaliar(item(id_nativo="a", duracao_s=1800), self.fonte, self.config, [])
        b = criterio.avaliar(item(id_nativo="b", duracao_s=1800), self.fonte, self.config, [])
        self.assertEqual([e.id for e in criterio.resolver_blocos([a, b], [])], [a.id])

    def test_canais_diferentes_no_mesmo_dia_sao_blocos_diferentes(self):
        f = fonte(self.config, "registo-curado")
        a = criterio.avaliar(item(id_nativo="a", canal="sic", programa="JN", data_declarada="2025-09-04"), f, self.config, [])
        b = criterio.avaliar(item(id_nativo="b", canal="sic-noticias", programa="JN", data_declarada="2025-09-04"), f, self.config, [])
        self.assertEqual(len(criterio.resolver_blocos([a, b], [])), 2)

    def test_mesma_entrevista_agrupa(self):
        f = fonte(self.config, "registo-curado")
        a = criterio.avaliar(item(id_nativo="a", canal="sic", programa="JN", data_declarada="2025-09-04", mesma_entrevista="k"), f, self.config, [])
        b = criterio.avaliar(item(id_nativo="b", canal="sic-noticias", programa="JN", data_declarada="2025-09-04", mesma_entrevista="k"), f, self.config, [])
        self.assertEqual(a.entrevista, b.entrevista)
        self.assertNotEqual(a.bloco, b.bloco)

    def test_parcial_vem_do_item_ou_da_fonte(self):
        self.assertTrue(criterio.avaliar(item(parcial=True), self.fonte, self.config, []).parcial)
        self.assertFalse(criterio.avaliar(item(), self.fonte, self.config, []).parcial)


if __name__ == "__main__":
    unittest.main(verbosity=2)
