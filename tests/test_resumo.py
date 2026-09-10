"""Agregados: as somas fecham, os canais estao todos, os recordes batem."""

import unittest

from tests.apoio import config_teste

from recolha import resumo


def linha(data, canal, entrevista=None, origem="declarada", fonte="registo-curado", proveniencia="canal"):
    return {
        "id": f"{fonte}:{data}:{canal}",
        "bloco": f"{canal}:{data}",
        "entrevista": entrevista or f"{canal}:{data}",
        "data": data,
        "data_origem": origem,
        "canal": canal,
        "programa": "P",
        "origem": proveniencia,
        "fonte": fonte,
    }


class TestSomas(unittest.TestCase):
    def setUp(self):
        self.config = config_teste()
        self.linhas = [
            linha("2025-09-01", "sic", entrevista="k1"),
            linha("2025-09-01", "sic-noticias", entrevista="k1"),
            linha("2025-09-03", "rtp3", origem="publicacao"),
            linha("2025-09-04", "rtp3"),
            linha("2025-09-05", "cmtv"),
            linha("2025-09-20", "now"),
            linha("2025-09-22", "cmtv", proveniencia="imprensa", fonte="clipping-imprensa"),
        ]
        self.r = resumo.construir(self.linhas, self.config)

    def test_totais(self):
        self.assertEqual(self.r["totais"], {"emissoes": 7, "entrevistas_distintas": 6})

    def test_nenhum_balde_tem_campos_de_tempo(self):
        """`tempo_s`, `sem_duracao` e `parciais` sairam a 2026-09-10. Um
        resumo que os trouxesse a zero seria lido por um site antigo como
        uma medicao de zero minutos."""
        baldes = [self.r["totais"]] + self.r["por_dia"] + self.r["por_canal"] + list(self.r["por_origem"].values())
        baldes += [c for d in self.r["canal_por_dia"] for c in d["canais"].values()]
        for balde in baldes:
            for campo in ("tempo_s", "sem_duracao", "parciais"):
                self.assertNotIn(campo, balde)
        self.assertEqual(self.r["esquema"], 2)

    def test_emissao_de_imprensa_conta_como_qualquer_outra(self):
        dia = next(d for d in self.r["por_dia"] if d["data"] == "2025-09-22")
        self.assertEqual(dia["emissoes"], 1)
        canal = next(c for c in self.r["por_canal"] if c["canal"] == "cmtv")
        self.assertEqual(canal["emissoes"], 2)

    def test_reparticao_por_origem(self):
        self.assertEqual(self.r["por_origem"]["imprensa"]["emissoes"], 1)
        self.assertEqual(self.r["por_origem"]["canal"]["emissoes"], 6)

    def test_soma_por_canal_fecha_no_total(self):
        self.assertEqual(sum(c["emissoes"] for c in self.r["por_canal"]), self.r["totais"]["emissoes"])

    def test_todos_os_canais_aparecem_pela_ordem_da_configuracao(self):
        self.assertEqual([c["canal"] for c in self.r["por_canal"]], list(self.config.canais))
        zero = next(c for c in self.r["por_canal"] if c["canal"] == "tvi")
        self.assertEqual(zero["emissoes"], 0)

    def test_soma_por_periodo_fecha_no_total(self):
        for chave in ("por_dia", "por_semana", "por_mes", "por_ano"):
            with self.subTest(chave=chave):
                self.assertEqual(sum(d["emissoes"] for d in self.r[chave]), 7)

    def test_por_dia_leva_as_chaves_de_entrevista(self):
        dia = next(d for d in self.r["por_dia"] if d["data"] == "2025-09-01")
        self.assertEqual(dia["chaves"], ["k1"])
        self.assertEqual(dia["emissoes"], 2)

    def test_canal_por_dia_marca_declaradas(self):
        dia = next(d for d in self.r["canal_por_dia"] if d["data"] == "2025-09-03")
        self.assertEqual(dia["canais"]["rtp3"]["declaradas"], 0)
        dia1 = next(d for d in self.r["canal_por_dia"] if d["data"] == "2025-09-01")
        self.assertEqual(set(dia1["canais"]), {"sic", "sic-noticias"})

    def test_recordes(self):
        rec = self.r["recordes"]
        self.assertEqual(rec["ultima_data"], "2025-09-22")
        self.assertEqual(rec["maior_jejum"], {"dias": 14, "de": "2025-09-05", "ate": "2025-09-20"})
        self.assertEqual(rec["maior_maratona"], {"dias": 3, "de": "2025-09-03", "ate": "2025-09-05"})

    def test_o_tema_e_os_canais_vao_no_resumo(self):
        self.assertEqual(self.r["tema"]["desde"], "2019-05-16")
        self.assertEqual(self.r["sujeito"]["id"], "ventura")
        self.assertEqual(self.r["fontes"], ["clipping-imprensa", "registo-curado"])


class TestSemanaIso(unittest.TestCase):
    def test_virada_de_ano(self):
        self.assertEqual(resumo.semana_iso("2024-12-30"), "2025-W01")
        self.assertEqual(resumo.semana_iso("2021-01-03"), "2020-W53")
        self.assertEqual(resumo.semana_iso("2026-09-07"), "2026-W37")


class TestVazio(unittest.TestCase):
    def test_sem_linhas(self):
        r = resumo.construir([], config_teste())
        self.assertEqual(r["totais"]["emissoes"], 0)
        self.assertIsNone(r["recordes"]["ultima_data"])
        self.assertEqual(len(r["por_canal"]), 9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
