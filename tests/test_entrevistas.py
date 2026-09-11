"""A dobragem de transmissoes em entrevistas.

A unidade do projeto passou a ser a entrevista exclusiva a 2026-09-11.
Cada teste aqui trava um erro concreto que esta mudanca tornou possivel,
e todos eles sao erros de contagem publicada, que e a classe que este
projeto considera a pior de todas.
"""

import unittest

from tests.apoio import RAIZ  # noqa: F401  (garante o sys.path)

from recolha import curadoria, entrevistas
from recolha.modelos import carregar_config, url_normalizado


def transmissao(id_, canal, data="2025-03-17", prova=None, programa="P", **campos):
    base = {
        "id": id_,
        "bloco": f"{canal}:{data}",
        "entrevista": f"{canal}:{data}",
        "data": data,
        "data_origem": "declarada",
        "publicado_em": data,
        "canal": canal,
        "programa": programa,
        "origem": "canal",
        "fonte": "registo-curado",
        "confianca": "alta",
        "prova_url": prova or f"https://exemplo.pt/{id_}",
        "titulo": "Entrevista",
        "primeira_vez": "2026-01-01",
        "rondas": 1,
        "fontes_distintas": 1,
    }
    base.update(campos)
    return base


class TestSemTabela(unittest.TestCase):
    def test_sem_tabela_cada_transmissao_e_uma_entrevista(self):
        """Agrupar e uma afirmacao positiva. O erro que isto previne e o
        que a KB pagou duas vezes: deduzir um grupo de um dominio ou de um
        identificador de video partilhado, sem ninguem ter lido a pagina."""
        linhas = [transmissao("a", "tvi"), transmissao("b", "cnn-portugal")]
        self.assertEqual(len(entrevistas.agrupar(linhas, {})), 2)

    def test_uma_transmissao_so_traz_um_canal_e_nenhuma_nota(self):
        e = entrevistas.agrupar([transmissao("a", "tvi")], {})[0]
        self.assertEqual(e["canais"], ["tvi"])
        self.assertFalse(e["principal_declarado"])
        self.assertEqual(len(e["transmissoes"]), 1)


class TestComTabela(unittest.TestCase):
    def setUp(self):
        self.linhas = [
            transmissao("a", "tvi", prova="https://exemplo.pt/tvi"),
            transmissao("b", "cnn-portugal", prova="https://exemplo.pt/cnn"),
        ]
        self.grupos = {
            "https://exemplo.pt/tvi": ("k", "cnn-portugal"),
            "https://exemplo.pt/cnn": ("k", "cnn-portugal"),
        }

    def test_duas_transmissoes_dao_uma_entrevista(self):
        dobradas = entrevistas.agrupar(self.linhas, self.grupos)
        self.assertEqual(len(dobradas), 1)
        self.assertEqual(len(dobradas[0]["transmissoes"]), 2)

    def test_a_entrevista_fica_no_canal_que_a_tabela_declara(self):
        """O canal nao se le do dominio nem da ordem das linhas: a KB
        mediu 8 linhas erradas em 8 quando se deduziu o canal do dominio.
        Aqui a primeira transmissao da lista e da TVI e a entrevista fica
        na CNN Portugal, porque foi isso que alguem escreveu."""
        e = entrevistas.agrupar(self.linhas, self.grupos)[0]
        self.assertEqual(e["canal"], "cnn-portugal")
        self.assertTrue(e["principal_declarado"])

    def test_o_canal_atribuido_vem_primeiro_na_lista_de_canais(self):
        """O site escreve "(também na TVI)" a partir desta lista, saltando
        o primeiro. Se a ordem nao fosse esta, a nota nomeava o canal a
        que a entrevista esta atribuida e escondia o outro."""
        e = entrevistas.agrupar(self.linhas, self.grupos)[0]
        self.assertEqual(e["canais"], ["cnn-portugal", "tvi"])

    def test_a_entrevista_herda_os_campos_do_canal_a_que_esta_atribuida(self):
        self.linhas[1]["programa"] = "Jornal da CNN"
        self.linhas[1]["titulo"] = "O da CNN"
        e = entrevistas.agrupar(self.linhas, self.grupos)[0]
        self.assertEqual(e["programa"], "Jornal da CNN")
        self.assertEqual(e["titulo"], "O da CNN")
        self.assertEqual(e["prova_url"], "https://exemplo.pt/cnn")

    def test_a_primeira_vez_e_a_mais_antiga_do_grupo(self):
        """`primeira_vez` e a data em que a entrevista apareceu no site.
        Herda-la da transmissao a que ficou atribuida fazia a entrevista
        rejuvenescer sempre que a segunda transmissao fosse a mais
        recente, e o append-only existe precisamente para que essa data
        nunca regrida."""
        self.linhas[0]["primeira_vez"] = "2025-06-01"
        self.linhas[1]["primeira_vez"] = "2026-02-01"
        e = entrevistas.agrupar(self.linhas, self.grupos)[0]
        self.assertEqual(e["primeira_vez"], "2025-06-01")

    def test_o_endereco_compara_se_normalizado(self):
        """A tabela e escrita a mao e o registo vem das fontes: um `www.`
        ou uma barra final a mais faziam o grupo nao juntar nada, e duas
        entrevistas continuavam a contar onde ha uma."""
        linhas = [
            transmissao("a", "tvi", prova="http://www.exemplo.pt/video/"),
            transmissao("b", "cnn-portugal", prova="https://exemplo.pt/cnn"),
        ]
        tabela = {
            url_normalizado("https://exemplo.pt/video"): ("k", "tvi"),
            url_normalizado("https://exemplo.pt/cnn"): ("k", "tvi"),
        }
        self.assertEqual(len(entrevistas.agrupar(linhas, tabela)), 1)

    def test_duas_transmissoes_com_a_mesma_pagina_juntam_se(self):
        """O mesmo video servido nos dois dominios do grupo tem uma pagina
        so. A tabela escreve o endereco uma vez e tem de juntar as duas
        transmissoes na mesma."""
        linhas = [
            transmissao("a", "tvi", prova="https://exemplo.pt/mesmo"),
            transmissao("b", "cnn-portugal", prova="https://exemplo.pt/mesmo"),
        ]
        tabela = {"https://exemplo.pt/mesmo": ("k", "cnn-portugal")}
        dobradas = entrevistas.agrupar(linhas, tabela)
        self.assertEqual(len(dobradas), 1)
        self.assertEqual(dobradas[0]["canais"], ["cnn-portugal", "tvi"])


class TestAvisos(unittest.TestCase):
    def test_um_grupo_que_nao_juntou_duas_transmissoes_avisa(self):
        """Foi assim que se apanhou um endereco mal copiado na primeira
        corrida do refactor: o grupo de um dos pares do servico publico
        juntou uma transmissao em vez de duas e o total ficou uma acima do
        previsto. Sem o aviso, ficava a contar a mais para sempre."""
        avisos = []
        entrevistas.agrupar(
            [transmissao("a", "tvi", prova="https://exemplo.pt/tvi")],
            {"https://exemplo.pt/tvi": ("k", "tvi"), "https://exemplo.pt/enganado": ("k", "tvi")},
            avisos,
        )
        self.assertEqual(len(avisos), 1)
        self.assertIn("juntou 1", avisos[0])

    def test_um_grupo_certo_nao_avisa(self):
        avisos = []
        entrevistas.agrupar(
            [transmissao("a", "tvi", prova="https://exemplo.pt/a"), transmissao("b", "now", prova="https://exemplo.pt/b")],
            {"https://exemplo.pt/a": ("k", "tvi"), "https://exemplo.pt/b": ("k", "tvi")},
            avisos,
        )
        self.assertEqual(avisos, [])

    def test_um_canal_declarado_que_nao_tem_transmissao_avisa_e_nao_parte(self):
        """Um id de canal mal escrito na tabela deixava a entrevista sem
        linha de onde herdar a data e a prova. Fica a primeira transmissao
        e o aviso diz qual foi: erro visivel, nunca uma corrida caida nem
        uma linha em branco no site."""
        avisos = []
        dobradas = entrevistas.agrupar(
            [transmissao("a", "tvi", prova="https://exemplo.pt/a"), transmissao("b", "now", prova="https://exemplo.pt/b")],
            {"https://exemplo.pt/a": ("k", "canal-que-nao-existe"), "https://exemplo.pt/b": ("k", "canal-que-nao-existe")},
            avisos,
        )
        self.assertEqual(len(dobradas), 1)
        self.assertIn(dobradas[0]["canal"], {"tvi", "now"})
        self.assertFalse(dobradas[0]["principal_declarado"])
        self.assertTrue(any("nao tem transmissao" in a for a in avisos))


class TestTabelaDaCuradoria(unittest.TestCase):
    """A tabela e escrita a mao e um erro nela e uma contagem errada
    publicada. Falha ao carregar, e nunca em silencio."""

    def _tabela(self, texto, tmp):
        caminho = tmp / "curadoria.yml"
        caminho.write_text(texto, encoding="utf-8", newline="\n")
        return curadoria.ler_grupos(caminho)

    def setUp(self):
        import tempfile
        from pathlib import Path

        self._dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)

    def test_le_um_grupo_valido(self):
        g = self._tabela(
            "mesma_entrevista:\n"
            "  - chave: k\n"
            "    canal: tvi\n"
            "    motivo: li as duas paginas\n"
            "    provas:\n"
            "      - https://exemplo.pt/a\n"
            "      - https://exemplo.pt/b\n",
            self.tmp,
        )
        self.assertEqual(g, {"https://exemplo.pt/a": ("k", "tvi"), "https://exemplo.pt/b": ("k", "tvi")})

    def test_sem_canal_falha(self):
        """Sem canal nao ha a quem atribuir a entrevista, e qualquer regra
        automatica para o adivinhar ja foi medida e recusada."""
        with self.assertRaises(ValueError):
            self._tabela("mesma_entrevista:\n  - chave: k\n    motivo: x\n    provas: [https://exemplo.pt/a]\n", self.tmp)

    def test_sem_motivo_falha(self):
        with self.assertRaises(ValueError):
            self._tabela("mesma_entrevista:\n  - chave: k\n    canal: tvi\n    provas: [https://exemplo.pt/a]\n", self.tmp)

    def test_chave_repetida_falha(self):
        """Duas entradas com a mesma chave sao um grupo so, com provas de
        dois sitios e possivelmente canais diferentes: a segunda ganhava
        em silencio."""
        with self.assertRaises(ValueError):
            self._tabela(
                "mesma_entrevista:\n"
                "  - chave: k\n    canal: tvi\n    motivo: x\n    provas: [https://exemplo.pt/a]\n"
                "  - chave: k\n    canal: now\n    motivo: y\n    provas: [https://exemplo.pt/b]\n",
                self.tmp,
            )

    def test_prova_que_nao_e_url_falha(self):
        with self.assertRaises(ValueError):
            self._tabela("mesma_entrevista:\n  - chave: k\n    canal: tvi\n    motivo: x\n    provas: [vi na televisao]\n", self.tmp)

    def test_ficheiro_sem_a_tabela_devolve_vazio(self):
        self.assertEqual(self._tabela("entrevistas: []\n", self.tmp), {})


class TestTabelaReal(unittest.TestCase):
    """A tabela que esta em producao tem de carregar e tem de juntar
    alguma coisa. Um endereco mal copiado nao falha a validacao, e este
    teste tambem nao o apanha: quem o apanha e o aviso da corrida. O que
    este trava e a tabela deixar de carregar de todo."""

    def test_a_tabela_do_repositorio_carrega(self):
        grupos = curadoria.ler_grupos()
        chaves = {c for c, _ in grupos.values()}
        self.assertTrue(chaves, "a tabela de config/curadoria.yml esta vazia")

    def test_todos_os_canais_da_tabela_sao_canais_medidos(self):
        """Um id de canal mal escrito na tabela deixa a entrevista sem
        transmissao de onde herdar a data e a prova. A corrida avisa, mas
        so quando correr: aqui apanha-se antes de o patch sair."""
        config = carregar_config()
        for chave, canal in sorted(set(curadoria.ler_grupos().values())):
            with self.subTest(grupo=chave):
                self.assertTrue(config.canal_valido(canal), f"{chave}: canal desconhecido {canal!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
