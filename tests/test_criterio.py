"""O criterio de inclusao, motivo a motivo."""

import unittest

from tests.apoio import config_teste, fonte, item, ler

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

    def test_o_corte_usa_o_dia_da_entrevista_e_nao_o_de_publicacao(self):
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


class TestCanal(unittest.TestCase):
    def setUp(self):
        self.config = config_teste()
        self.fonte = fonte(self.config, "podcast-exemplo")

    def test_fonte_automatica_sem_duracao_entra(self):
        """Ate 2026-09-10 um item de fonte automatica sem duracao ia para a
        quarentena como `por_confirmar`. A duracao saiu do projeto: um
        video que o canal titula como entrevista e prova da transmissao e
        entra pelo criterio normal (rondas a parte)."""
        q = []
        r = criterio.avaliar(item(), fonte(self.config, "yt-exemplo"), self.config, q)
        self.assertIsNotNone(r)
        self.assertEqual(q, [])

    def test_a_transmissao_nao_transporta_duracao_nem_parcial(self):
        """O ficheiro publicado nao pode ter um campo de tempo a fingir que
        conta: quem o le acreditava que o site o usava."""
        r = criterio.avaliar(item(), self.fonte, self.config, [])
        self.assertNotIn("duracao_s", r.como_dict())
        self.assertNotIn("parcial", r.como_dict())

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

    def test_mesmo_bloco_fica_com_o_primeiro_e_o_outro_vai_para_a_quarentena(self):
        """Sem duracao nao ha "melhor prova" dentro de um bloco: a ordem das
        fontes decide, e o segundo item fica visivel na quarentena com o
        motivo escrito, nunca descartado em silencio."""
        q = []
        a = criterio.avaliar(item(id_nativo="a", publicado_em="2025-09-05"), self.fonte, self.config, [])
        b = criterio.avaliar(item(id_nativo="b", publicado_em="2025-09-05"), self.fonte, self.config, [])
        ficam = criterio.resolver_blocos([a, b], q)
        self.assertEqual([e.id for e in ficam], [a.id])
        self.assertTrue(q[0]["motivo"].startswith("fragmento_ou_repetido"))
        self.assertEqual(q[0]["id_nativo"], b.id)

    def test_sem_programa_apurado_nao_abre_bloco_no_dia_que_ja_tem_um(self):
        """Erro real medido no dataset de 2026-09-10: a mesma transmissao entrou
        duas vezes no mesmo canal e dia, uma com o programa deduzido do
        titulo e outra sem, porque o titulo dela nao tem separador. Tres
        ocorrencias em doze linhas de uma so fonte."""
        q = []
        f = fonte(self.config, "yt-exemplo")
        com = criterio.avaliar(item(id_nativo="a", titulo="Entrevista Exemplo - André Ventura - ep. 41"), f, self.config, [])
        sem = criterio.avaliar(item(id_nativo="b", titulo="Entrevista Exemplo", descricao="com André Ventura"), f, self.config, [])
        self.assertTrue(com.programa)
        self.assertFalse(sem.programa)
        self.assertNotEqual(com.bloco, sem.bloco)
        ficam = criterio.resolver_blocos([com, sem], q)
        self.assertEqual([e.id for e in ficam], [com.id])
        self.assertIn("sem programa apurado", q[0]["motivo"])
        self.assertEqual(q[0]["id_nativo"], sem.id)

    def test_sem_programa_apurado_conta_quando_e_a_unica_do_dia(self):
        """A absorcao nao pode comer a transmissao: sem outra no mesmo canal e
        dia, uma transmissao sem programa apurado e uma transmissao e conta."""
        sem = criterio.avaliar(item(id_nativo="b", titulo="Entrevista Exemplo", descricao="com André Ventura"), fonte(self.config, "yt-exemplo"), self.config, [])
        q = []
        self.assertEqual([e.id for e in criterio.resolver_blocos([sem], q)], [sem.id])
        self.assertEqual(q, [])

    def test_dois_programas_apurados_diferentes_no_mesmo_dia_contam_os_dois(self):
        """A manha num programa de entretenimento e a noite num noticiario
        sao duas entrevistas. A absorcao so apanha o que nao esta apurado."""
        f = fonte(self.config, "yt-exemplo")
        a = criterio.avaliar(item(id_nativo="a", titulo="Entrevista Um - André Ventura"), f, self.config, [])
        b = criterio.avaliar(item(id_nativo="b", titulo="Entrevista Dois - André Ventura"), f, self.config, [])
        self.assertEqual(len(criterio.resolver_blocos([a, b], [])), 2)

    def test_a_ordem_das_fontes_decide_o_bloco(self):
        """O registo curado corre antes do clipping em config/fontes.yml, e
        e por isso, e so por isso, que a prova do canal fica quando as duas
        provam a mesma transmissao. Trocar a ordem troca o vencedor."""
        curado = fonte(self.config, "registo-curado")
        clipping = fonte(self.config, "clipping-imprensa")
        a = criterio.avaliar(item(id_nativo="a", canal="sic", programa="JN", data_declarada="2025-09-04"), curado, self.config, [])
        b = criterio.avaliar(item(id_nativo="b", canal="sic", programa="JN", data_declarada="2025-09-04"), clipping, self.config, [])
        self.assertEqual([e.id for e in criterio.resolver_blocos([a, b], [])], [a.id])
        self.assertEqual([e.id for e in criterio.resolver_blocos([b, a], [])], [b.id])

    def test_canais_diferentes_no_mesmo_dia_sao_blocos_diferentes(self):
        f = fonte(self.config, "registo-curado")
        a = criterio.avaliar(item(id_nativo="a", canal="sic", programa="JN", data_declarada="2025-09-04"), f, self.config, [])
        b = criterio.avaliar(item(id_nativo="b", canal="sic-noticias", programa="JN", data_declarada="2025-09-04"), f, self.config, [])
        self.assertEqual(len(criterio.resolver_blocos([a, b], [])), 2)

    def test_cada_transmissao_e_uma_entrevista_por_omissao(self):
        """O criterio nao agrupa nada. Ate 2026-09-11 lia uma chave escrita
        na linha do registo; agora o agrupamento e uma afirmacao positiva
        da tabela de config/curadoria.yml, aplicada a publicacao. Um
        criterio que voltasse a deduzir grupos juntaria transmissoes sem
        que ninguem tivesse lido as paginas."""
        f = fonte(self.config, "registo-curado")
        a = criterio.avaliar(item(id_nativo="a", canal="sic", programa="JN", data_declarada="2025-09-04"), f, self.config, [])
        b = criterio.avaliar(item(id_nativo="b", canal="sic-noticias", programa="JN", data_declarada="2025-09-04"), f, self.config, [])
        self.assertEqual(a.entrevista, a.bloco)
        self.assertNotEqual(a.entrevista, b.entrevista)


class TestRecusasContadas(unittest.TestCase):
    """As recusas saem contadas por motivo, nunca uma linha por registo.

    A 2026-09-10 uma fonte nova trouxe 194 paginas, leu as 194, apurou a
    duracao das 194 e publicou zero. A corrida terminou a dizer "194
    itens em quarentena" e mais nada, e como era --dry-run a quarentena
    nem sequer foi escrita em disco: o motivo existia em cada linha e nao
    havia forma de o ver.
    """

    def _capturar(self, quarentena):
        import io
        from contextlib import redirect_stdout

        from recolha import principal

        saida = io.StringIO()
        with redirect_stdout(saida):
            principal._contar_recusas(quarentena)
        return saida.getvalue()

    def test_uma_linha_por_motivo_e_nao_por_registo(self):
        quarentena = [
            {"fonte": "f", "motivo": "sem_sujeito", "titulo": f"Episodio {i}"} for i in range(190)
        ] + [
            {"fonte": "f", "motivo": "sem_data", "titulo": "Sem data"},
        ]
        linhas = [l for l in self._capturar(quarentena).splitlines() if l.strip()]
        self.assertEqual(len(linhas), 2, "uma linha por motivo, nao 191 linhas")
        self.assertIn("190", linhas[0])
        self.assertIn("sem_sujeito", linhas[0])

    def test_o_pormenor_do_motivo_nao_se_perde(self):
        quarentena = [
            {"fonte": "f", "motivo": "formato_nao_elegivel (debate)", "titulo": "x"},
            {"fonte": "f", "motivo": "formato_nao_elegivel (direto)", "titulo": "y"},
        ]
        texto = self._capturar(quarentena)
        self.assertIn("(debate)", texto)
        self.assertIn("(direto)", texto)

    def test_a_fonte_aparece_para_se_saber_de_quem_e_a_recusa(self):
        quarentena = [
            {"fonte": "uma", "motivo": "sem_data", "titulo": "x"},
            {"fonte": "outra", "motivo": "sem_data", "titulo": "y"},
        ]
        texto = self._capturar(quarentena)
        self.assertIn("uma", texto)
        self.assertIn("outra", texto)

    def test_quarentena_vazia_nao_escreve_nada(self):
        self.assertEqual(self._capturar([]), "")


class TestEpisodioDeProgramaDeEntrevista(unittest.TestCase):
    """Um episodio de um programa de entrevistas com o sujeito conta.

    O caso real de 2026-09-10, ponta a ponta: a pagina do episodio nao
    diz o nome do sujeito no titulo (o titulo e o nome do programa), diz
    o dia so nas etiquetas, e nomeia o convidado na sinopse. As tres
    coisas juntas fizeram com que 194 paginas nao dessem uma transmissao.
    """

    def setUp(self):
        self.config = config_teste()
        self.fonte = fonte(self.config, "podcast-exemplo")

    def _item(self, **campos):
        from recolha import extracao

        dados = extracao.extrair(ler("pagina_episodio_audio.html"), "https://exemplo.pt/play/p1/e2/x")
        base = dict(
            id_nativo="https://exemplo.pt/play/p1/e2/x",
            publicado_em=dados["publicado_em"],
            titulo=dados["titulo"],
            # A sinopse nomeia o convidado e o titulo nao, que e o ponto:
            # sem a sinopse, um episodio destes nao se distingue de outro.
            descricao=dados["descricao"].replace("Pessoa Exemplo", "André Ventura"),
            url="https://exemplo.pt/play/p1/e2/x",
            prova_url="https://exemplo.pt/play/p1/e2/x",
        )
        base.update(campos)
        return item(**base)

    def test_conta_quando_a_fonte_declara_o_programa(self):
        from dataclasses import replace

        fonte_com_programa = replace(self.fonte, programa="Programa de Entrevista")
        quarentena = []
        transmissao = criterio.avaliar(self._item(programa="Programa de Entrevista"), fonte_com_programa, self.config, quarentena)
        self.assertIsNotNone(transmissao, f"recusado: {quarentena}")
        self.assertEqual(transmissao.data, "2026-06-24")

    def test_sem_o_sujeito_na_sinopse_nao_conta(self):
        """Os outros convidados do mesmo programa saem, e e o que deve ser."""
        quarentena = []
        outro = self._item(descricao="Outra Pessoa - o convidado de hoje", programa="Programa de Entrevista")
        self.assertIsNone(criterio.avaliar(outro, self.fonte, self.config, quarentena))
        self.assertEqual(quarentena[0]["motivo"], "sem_sujeito")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestLicoesDaPrimeiraCorridaDeHistorico(unittest.TestCase):
    """Tres defeitos reais da primeira reconstrucao do historico.

    Ficam travados por teste porque cada um deles fazia o site publicar,
    ou a quarentena afirmar, uma coisa que nao era verdade.
    """

    def setUp(self):
        self.config = config_teste()
        self.fonte = fonte(self.config, "registo-curado")

    def test_sem_data_nao_e_anterior_ao_inicio(self):
        """59 de 64 rejeicoes diziam "antes de 2019" a paginas que
        simplesmente nao declaravam data nenhuma."""
        q = []
        self.assertIsNone(criterio.avaliar(item(publicado_em="", titulo="Grande Entrevista", canal="rtp1"), self.fonte, self.config, q))
        self.assertEqual(q[0]["motivo"], "sem_data")

    def test_data_anterior_continua_a_ser_anterior(self):
        q = []
        self.assertIsNone(criterio.avaliar(item(publicado_em="2013-12-05", canal="rtp1"), self.fonte, self.config, q))
        self.assertEqual(q[0]["motivo"], "anterior_ao_inicio")

    def test_programa_deduzido_do_titulo(self):
        self.assertEqual(criterio.programa_do_titulo("Grande Entrevista - Alguem - ep. 41", self.config), "Grande Entrevista")
        self.assertEqual(criterio.programa_do_titulo("Programa | Alguem", self.config), "Programa")

    def test_programa_nao_e_o_nome_do_sujeito(self):
        titulo = f"{self.config.sujeito.nome} - entrevista"
        self.assertEqual(criterio.programa_do_titulo(titulo, self.config), "")

    def test_titulo_sem_separador_nao_inventa_programa(self):
        self.assertEqual(criterio.programa_do_titulo("Grande Entrevista", self.config), "")

    def test_duas_entrevistas_do_mesmo_dia_e_canal_nao_colidem(self):
        """Com o programa sempre vazio, o bloco (canal, programa, dia) era
        o mesmo para programas diferentes e uma das entrevistas era
        descartada como repetida."""
        a = criterio.avaliar(item(titulo="Programa A - Alguem", canal="rtp1", url="https://exemplo.pt/1", prova_url="https://exemplo.pt/1"), self.fonte, self.config)
        b = criterio.avaliar(item(titulo="Programa B - Alguem", canal="rtp1", url="https://exemplo.pt/2", prova_url="https://exemplo.pt/2"), self.fonte, self.config)
        self.assertNotEqual(a.bloco, b.bloco)
        self.assertEqual(len(criterio.resolver_blocos([a, b], [])), 2)


class TestSujeitoNasEtiquetas(unittest.TestCase):
    """O canal identifica o convidado nas tags de pecas cujo titulo nao o
    nomeia. Procurar so no titulo perdia essas entrevistas."""

    def setUp(self):
        self.config = config_teste()
        self.fonte = fonte(self.config, "yt-teste") if any(f.id == "yt-teste" for f in self.config.fontes) else fonte(self.config, "registo-curado")

    def test_sujeito_so_nas_etiquetas_conta(self):
        automatica = next(f for f in self.config.fontes if f.tipo != "manual")
        alvo = item(titulo="Grande Entrevista - ep. 41", canal="rtp1", descricao="", etiquetas="André Ventura, política")
        q = []
        resultado = criterio.avaliar(alvo, automatica, self.config, q)
        self.assertIsNotNone(resultado, f"rejeitado: {q}")

    def test_sem_sujeito_em_lado_nenhum_continua_fora(self):
        automatica = next(f for f in self.config.fontes if f.tipo != "manual")
        alvo = item(titulo="Grande Entrevista - ep. 41", canal="rtp1", descricao="", etiquetas="outra pessoa")
        q = []
        self.assertIsNone(criterio.avaliar(alvo, automatica, self.config, q))
        self.assertEqual(q[0]["motivo"], "sem_sujeito")


class TestVariasEntrevistasNoMesmoDia(unittest.TestCase):
    """Uma entrevista de manha num programa de entretenimento e outra a
    noite num noticiario, no mesmo canal, sao duas entrevistas."""

    def setUp(self):
        self.config = config_teste()
        self.fonte = fonte(self.config, "registo-curado")

    def _transmissao(self, titulo, n):
        return criterio.avaliar(
            item(titulo=titulo, canal="rtp1",
                 url=f"https://exemplo.pt/{n}", prova_url=f"https://exemplo.pt/{n}"),
            self.fonte, self.config,
        )

    def test_manha_e_noite_contam_as_duas(self):
        manha = self._transmissao("Programa da Manha - Alguem", 1)
        noite = self._transmissao("Jornal da Noite - Alguem", 2)
        self.assertNotEqual(manha.bloco, noite.bloco)
        self.assertEqual(len(criterio.resolver_blocos([manha, noite], [])), 2)

    def test_recorte_do_mesmo_programa_nao_conta_duas_vezes(self):
        """O que a chave existe para juntar: o video integral e o recorte."""
        integral = self._transmissao("Jornal da Noite - Alguem", 1)
        recorte = self._transmissao("Jornal da Noite - Alguem", 2)
        q = []
        ficam = criterio.resolver_blocos([integral, recorte], q)
        self.assertEqual(len(ficam), 1)
        self.assertEqual(ficam[0].id, integral.id)
        self.assertIn("fragmento_ou_repetido", q[0]["motivo"])

    def test_programa_nao_apurado_fica_dito_na_quarentena(self):
        """O erro e por defeito, nunca por excesso, mas tem de se ver."""
        a = self._transmissao("Alguem em entrevista", 1)
        b = self._transmissao("Alguem outra vez", 2)
        self.assertEqual(a.programa, "")
        q = []
        self.assertEqual(len(criterio.resolver_blocos([a, b], q)), 1)
        self.assertIn("programa nao apurado", q[0]["motivo"])


class TestProvaDeFormato(unittest.TestCase):
    """Numa fonte automatica ninguem leu a pagina. Ate 8 de setembro de
    2026 o formato era `entrevista` por omissao e bastava nao haver termo
    de exclusao no titulo: sete pecas noticiosas curtas, uma de 55
    segundos, ficaram publicadas como entrevistas exclusivas. Estes
    testes travam esse erro com os titulos reais que o causaram."""

    def setUp(self):
        self.config = config_teste()
        # Fonte automatica sem `formato` declarado: a que estava a
        # publicar as pecas indevidas era desta especie.
        self.automatica = fonte(self.config, "yt-exemplo")
        self.assertFalse(self.automatica.formato_declarado)

    def _avaliar(self, **campos):
        q = []
        r = criterio.avaliar(item(**campos), self.automatica, self.config, q)
        return r, q

    def test_peca_noticiosa_com_o_nome_nao_e_entrevista(self):
        """A peca de 55 segundos que estava publicada como entrevista."""
        r, q = self._avaliar(titulo="André Ventura centra-se na formação de governo sombra")
        self.assertIsNone(r)
        self.assertEqual(q[0]["motivo"], "formato_nao_apurado")

    def test_sujeito_so_nas_etiquetas_nao_prova_o_formato(self):
        """As etiquetas encontram o sujeito, mas nao dizem que a peca e
        uma entrevista. Titulo real da RTP3, 2 minutos e 41 segundos."""
        r, q = self._avaliar(
            titulo="Presidenciais. Líder do partido não concorda com extinção do SEF",
            etiquetas="André Ventura, presidenciais",
        )
        self.assertIsNone(r)
        self.assertEqual(q[0]["motivo"], "formato_nao_apurado")

    def test_concorrente_de_reality_show_nao_entra(self):
        """Ha um concorrente de reality show com o mesmo apelido. O nome
        passa a deteccao do sujeito; o formato e que o tem de travar."""
        r, q = self._avaliar(titulo="Big Brother Ventura fica fora de si e grita com Tatiana")
        self.assertIsNone(r)
        self.assertEqual(q[0]["motivo"], "formato_nao_apurado")

    def test_a_palavra_na_sinopse_nao_prova(self):
        """A sinopse fala de tudo: uma peca que fala de uma entrevista nao
        e uma entrevista."""
        r, q = self._avaliar(titulo="André Ventura fala do país", descricao="Em entrevista, disse que...")
        self.assertIsNone(r)
        self.assertEqual(q[0]["motivo"], "formato_nao_apurado")

    def test_titulo_que_diz_entrevista_prova(self):
        """Titulo real da RTP de uma peca de 145 segundos: o canal chama-lhe
        entrevista, e isso conta. Nao ha duracao minima, e desde 2026-09-10
        nem sequer ha duracao."""
        r, q = self._avaliar(titulo="Entrevista à RTP. Ventura assume que eleger menos de 50 deputados seria mau")
        self.assertIsNotNone(r, q)

    def test_programa_de_entrevista_prova_sem_a_palavra(self):
        """Um canal titula o episodio pelo programa e deixa o convidado a
        seguir ao separador. Se o programa e de entrevista, e prova."""
        r, q = self._avaliar(titulo="Programa de Entrevista - André Ventura - ep. 12")
        self.assertIsNotNone(r, q)
        self.assertEqual(r.programa, "Programa de Entrevista")

    def test_programa_fora_da_lista_nao_prova(self):
        r, q = self._avaliar(titulo="Programa da Manhã - André Ventura")
        self.assertIsNone(r)
        self.assertEqual(q[0]["motivo"], "formato_nao_apurado")

    def test_exclusao_ganha_a_falta_de_prova(self):
        """"Debate com o sujeito" e um debate. Dizer que o formato nao se
        apurou seria menos verdade, e a quarentena tem de dizer a verdade."""
        r, q = self._avaliar(titulo="Debate com André Ventura")
        self.assertIsNone(r)
        self.assertEqual(q[0]["motivo"], "formato_nao_elegivel (debate)")

    def test_fonte_com_formato_declarado_dispensa_a_prova(self):
        """Um feed de um programa de entrevistas declara o formato na
        configuracao; essa linha e a decisao editorial, e chega."""
        declarada = fonte(self.config, "podcast-exemplo")
        self.assertTrue(any(s.formato for s in declarada.segmentos))
        r = criterio.avaliar(item(titulo="André Ventura fala do país"), declarada, self.config, [])
        self.assertIsNotNone(r)

    def test_registo_curado_dispensa_a_prova(self):
        """Uma pessoa leu a pagina. O titulo do canal pode dizer o que quiser."""
        curado = fonte(self.config, "registo-curado")
        r = criterio.avaliar(
            item(titulo="Jornal da Noite", canal="sic", programa="Jornal da Noite", data_declarada="2025-09-04"),
            curado, self.config, [],
        )
        self.assertIsNotNone(r)

    def test_sem_prova_de_formato_nao_entra_mesmo_sem_a_barreira_da_duracao(self):
        """Ate 2026-09-10 uma peca sem duracao morria em `por_confirmar`
        por sorte, antes de a prova de formato a olhar. Sem essa barreira,
        e a prova de formato que a trava, e tem de travar."""
        r, q = self._avaliar(titulo="André Ventura centra-se na formação de governo sombra")
        self.assertIsNone(r)
        self.assertEqual(q[0]["motivo"], "formato_nao_apurado")
