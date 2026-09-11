"""Agregados: as somas fecham, os canais estao todos, os recordes batem.

A unidade e a entrevista exclusiva desde 2026-09-11. O que chega aqui ja
vem dobrado por recolha/entrevistas.py: uma entrevista que passou em dois
canais e uma entrada so, com os dois canais dentro. O erro que estes
testes previnem e o de a reparticao por canal somar mais do que o total,
que e exactamente o que acontecia se cada canal contasse a sua.
"""

import unittest

from tests.apoio import config_teste

from recolha import resumo


def entrevista(data, canal, tambem_em=(), origem="declarada", fonte="registo-curado", proveniencia="canal"):
    """Uma entrada como recolha/entrevistas.agrupar a produz."""
    canais = [canal] + list(tambem_em)
    return {
        "id": f"{canal}:{data}",
        "data": data,
        "data_origem": origem,
        "canal": canal,
        "programa": "P",
        "origem": proveniencia,
        "fonte": fonte,
        "canais": canais,
        "principal_declarado": len(canais) > 1,
        "transmissoes": [
            {"id": f"{fonte}:{data}:{c}", "canal": c, "fonte": fonte, "data": data}
            for c in canais
        ],
    }


class TestSomas(unittest.TestCase):
    def setUp(self):
        self.config = config_teste()
        self.entrevistas = [
            entrevista("2025-09-01", "sic", tambem_em=["sic-noticias"]),
            entrevista("2025-09-03", "rtp3", origem="publicacao"),
            entrevista("2025-09-04", "rtp3"),
            entrevista("2025-09-05", "cmtv"),
            entrevista("2025-09-20", "now"),
            entrevista("2025-09-22", "cmtv", proveniencia="imprensa", fonte="clipping-imprensa"),
        ]
        self.r = resumo.construir(self.entrevistas, self.config)

    def test_totais(self):
        self.assertEqual(self.r["totais"], {"entrevistas": 6})

    def test_um_balde_traz_um_numero_so(self):
        """Ate 2026-09-11 cada balde trazia `emissoes` e
        `entrevistas_distintas`, e o site escrevia os dois. O autor
        retirou o conceito de emissao: um campo que sobrevivesse aqui
        seria lido por um site novo como um numero a mais e por um site
        antigo como se nada tivesse mudado."""
        baldes = [self.r["totais"], self.r["ambito"]["fora_do_ambito"]]
        baldes += self.r["por_dia"] + self.r["por_semana"] + self.r["por_mes"] + self.r["por_ano"]
        baldes += self.r["por_canal"] + list(self.r["por_origem"].values())
        baldes += [c for d in self.r["canal_por_dia"] for c in d["canais"].values()]
        for balde in baldes:
            for campo in ("emissoes", "entrevistas_distintas", "chaves"):
                self.assertNotIn(campo, balde)
            self.assertIn("entrevistas", balde)

    def test_nenhum_balde_tem_campos_de_tempo(self):
        """`tempo_s`, `sem_duracao` e `parciais` sairam a 2026-09-10. Um
        resumo que os trouxesse a zero seria lido por um site antigo como
        uma medicao de zero minutos."""
        baldes = [self.r["totais"]] + self.r["por_dia"] + self.r["por_canal"] + list(self.r["por_origem"].values())
        baldes += [c for d in self.r["canal_por_dia"] for c in d["canais"].values()]
        for balde in baldes:
            for campo in ("tempo_s", "sem_duracao", "parciais"):
                self.assertNotIn(campo, balde)
        self.assertEqual(self.r["esquema"], 3)

    def test_entrevista_de_imprensa_conta_como_qualquer_outra(self):
        dia = next(d for d in self.r["por_dia"] if d["data"] == "2025-09-22")
        self.assertEqual(dia["entrevistas"], 1)
        canal = next(c for c in self.r["por_canal"] if c["canal"] == "cmtv")
        self.assertEqual(canal["entrevistas"], 2)

    def test_reparticao_por_origem(self):
        self.assertEqual(self.r["por_origem"]["imprensa"]["entrevistas"], 1)
        self.assertEqual(self.r["por_origem"]["canal"]["entrevistas"], 5)

    def test_uma_entrevista_em_dois_canais_conta_num_canal_so(self):
        """O erro que isto previne e uma reparticao por canal cuja soma e
        maior do que o total publicado. A entrevista de 2025-09-01 passou
        em dois canais e esta atribuida ao primeiro: conta la, e nao no
        outro. Quem quiser ver os dois canais abre a pagina de Fontes,
        onde estao as duas provas."""
        por_canal = {c["canal"]: c["entrevistas"] for c in self.r["por_canal"]}
        self.assertEqual(por_canal["sic"], 1)
        self.assertEqual(por_canal["sic-noticias"], 0)
        dia = next(d for d in self.r["canal_por_dia"] if d["data"] == "2025-09-01")
        self.assertEqual(list(dia["canais"]), ["sic"])

    def test_soma_por_canal_fecha_no_total(self):
        self.assertEqual(sum(c["entrevistas"] for c in self.r["por_canal"]), self.r["totais"]["entrevistas"])

    def test_todos_os_canais_aparecem_pela_ordem_da_configuracao(self):
        self.assertEqual([c["canal"] for c in self.r["por_canal"]], list(self.config.canais))
        zero = next(c for c in self.r["por_canal"] if c["canal"] == "tvi")
        self.assertEqual(zero["entrevistas"], 0)

    def test_soma_por_periodo_fecha_no_total(self):
        for chave in ("por_dia", "por_semana", "por_mes", "por_ano"):
            with self.subTest(chave=chave):
                self.assertEqual(sum(d["entrevistas"] for d in self.r[chave]), 6)

    def test_canal_por_dia_marca_declaradas(self):
        dia = next(d for d in self.r["canal_por_dia"] if d["data"] == "2025-09-03")
        self.assertEqual(dia["canais"]["rtp3"]["declaradas"], 0)
        dia1 = next(d for d in self.r["canal_por_dia"] if d["data"] == "2025-09-01")
        self.assertEqual(dia1["canais"]["sic"]["declaradas"], 1)

    def test_recordes(self):
        rec = self.r["recordes"]
        self.assertEqual(rec["ultima_data"], "2025-09-22")
        self.assertEqual(rec["maior_jejum"], {"dias": 14, "de": "2025-09-05", "ate": "2025-09-20"})
        self.assertEqual(rec["maior_maratona"], {"dias": 3, "de": "2025-09-03", "ate": "2025-09-05"})

    def test_o_tema_e_os_canais_vao_no_resumo(self):
        self.assertEqual(self.r["tema"]["desde"], "2019-05-16")
        self.assertEqual(self.r["sujeito"]["id"], "ventura")
        self.assertEqual(self.r["fontes"], ["clipping-imprensa", "registo-curado"])

    def test_a_lista_de_fontes_conta_as_das_transmissoes(self):
        """Uma fonte que so tenha provado a segunda transmissao de uma
        entrevista provou alguma coisa. Contar so as fontes da transmissao
        a que a entrevista esta atribuida apagava-a da lista publicada, e
        com ela a unica pista de que aquela via rende."""
        e = entrevista("2025-10-01", "sic", tambem_em=["tvi"])
        e["transmissoes"][1]["fonte"] = "busca-tvi"
        r = resumo.construir([e], config_teste())
        self.assertEqual(r["fontes"], ["busca-tvi", "registo-curado"])


class TestSemanaIso(unittest.TestCase):
    def test_virada_de_ano(self):
        self.assertEqual(resumo.semana_iso("2024-12-30"), "2025-W01")
        self.assertEqual(resumo.semana_iso("2021-01-03"), "2020-W53")
        self.assertEqual(resumo.semana_iso("2026-09-07"), "2026-W37")


class TestVazio(unittest.TestCase):
    def test_sem_entrevistas(self):
        r = resumo.construir([], config_teste())
        self.assertEqual(r["totais"]["entrevistas"], 0)
        self.assertIsNone(r["recordes"]["ultima_data"])
        self.assertEqual(len(r["por_canal"]), 9)


class TestAmbitoVisivel(unittest.TestCase):
    """O site mostra e conta a partir de tema.visivel_desde (decisao do
    autor, 2026-09-11). O erro que isto previne: somar anos de cobertura
    residual (2019 a 2023, com uma ou duas entrevistas apuradas por ano)
    como se fossem medicao. Nada se apaga: o que fica antes do corte sai
    de todos os agregados e e contado em ambito.fora_do_ambito, para a
    pagina de Fontes o dizer."""

    def _config_com_corte(self):
        from dataclasses import replace

        config = config_teste()
        tema = replace(
            config.tema,
            visivel_desde="2024-01-01",
            visivel_rotulo="desde o inicio de 2024",
            visivel_tab="Desde 2024",
        )
        return replace(config, tema=tema)

    def test_entrevista_anterior_ao_corte_fica_fora_de_todos_os_agregados(self):
        """2023-12-31 fica fora e 2024-01-01 entra: o corte compara datas
        ISO e inclui o proprio dia. A entrevista de fora nao aparece em
        nenhum balde nem na lista de fontes, e fica contada no ambito."""
        entrevistas = [
            entrevista("2023-12-31", "sic", fonte="clipping-imprensa", proveniencia="imprensa"),
            entrevista("2024-01-01", "cmtv"),
        ]
        r = resumo.construir(entrevistas, self._config_com_corte())
        self.assertEqual(r["totais"], {"entrevistas": 1})
        self.assertEqual([b["ano"] for b in r["por_ano"]], ["2024"])
        self.assertEqual([d["data"] for d in r["por_dia"]], ["2024-01-01"])
        self.assertEqual(r["primeiro_registo"], "2024-01-01")
        self.assertEqual(r["fontes"], ["registo-curado"])
        self.assertEqual(sum(c["entrevistas"] for c in r["por_canal"]), r["totais"]["entrevistas"])
        self.assertEqual(r["ambito"]["fora_do_ambito"], {"entrevistas": 1})

    def test_o_ambito_vai_no_resumo_por_extenso(self):
        """O site nao pode adivinhar o corte: o resumo di-lo, com o rotulo
        e a tab que a configuracao editorial escreveu."""
        r = resumo.construir([entrevista("2024-05-01", "sic")], self._config_com_corte())
        self.assertEqual(r["ambito"]["visivel_desde"], "2024-01-01")
        self.assertEqual(r["ambito"]["rotulo"], "desde o inicio de 2024")
        self.assertEqual(r["ambito"]["tab"], "Desde 2024")
        self.assertEqual(r["ambito"]["recolha_desde"], self._config_com_corte().tema.desde)

    def test_sem_corte_definido_o_resumo_conta_tudo_como_dantes(self):
        """Uma configuracao sem visivel_desde comporta-se como antes da
        mudanca: o corte cai em tema.desde e nada do dataset sai. E o que
        protege as configuracoes e fixtures antigas."""
        config = config_teste()
        r = resumo.construir([entrevista("2025-09-01", "sic")], config)
        self.assertEqual(r["totais"]["entrevistas"], 1)
        self.assertEqual(r["ambito"]["visivel_desde"], config.tema.desde)
        self.assertEqual(r["ambito"]["fora_do_ambito"], {"entrevistas": 0})


if __name__ == "__main__":
    unittest.main(verbosity=2)
