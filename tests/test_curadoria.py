"""A curadoria a mao: acrescentar uma emissao e vetar uma prova.

Existe desde 2026-09-10, a pedido do autor: dar a ligacao da prova e a
data, e nada mais. Estes testes travam os dois erros que uma via destas
comete com facilidade, e que sao os dois piores do projeto: publicar uma
linha que nao devia (o veto que nao apanha o que ja esta publicado) e
fazer desaparecer uma linha sem dizer porque (o veto que nao escreve na
quarentena).
"""

import unittest

from tests.apoio import FIXTURES, RAIZ, config_teste, fonte

from recolha import criterio, curadoria, principal
from recolha.fontes import manual


class TestLerRemocoes(unittest.TestCase):
    def test_le_prova_e_motivo(self):
        r = curadoria.ler_remocoes(FIXTURES / "curadoria_exemplo.yml")
        self.assertEqual(r, {"https://exemplo.pt/x1": "e um debate, nao uma entrevista"})

    def test_ficheiro_que_nao_existe_nao_e_erro(self):
        """A corrida nao pode partir por o ficheiro ainda nao ter sido
        criado: sem curadoria, ha zero remocoes."""
        self.assertEqual(curadoria.ler_remocoes(FIXTURES / "nao-existe.yml"), {})

    def test_remocao_sem_motivo_e_recusada(self):
        """Uma remocao sem motivo e indistinguivel de um engano daqui a seis
        meses. O ficheiro nao carrega em vez de a aceitar em silencio."""
        import tempfile
        from pathlib import Path

        for conteudo in ("remover:\n  - prova: https://x\n", "remover:\n  - motivo: qualquer\n"):
            with self.subTest(conteudo=conteudo), tempfile.TemporaryDirectory() as tmp:
                caminho = Path(tmp) / "c.yml"
                caminho.write_text(conteudo, encoding="utf-8")
                with self.assertRaises(ValueError):
                    curadoria.ler_remocoes(caminho)

    def test_o_ficheiro_real_carrega(self):
        curadoria.ler_remocoes(RAIZ / "config" / "curadoria.yml")


class TestAcrescentarAMao(unittest.TestCase):
    def setUp(self):
        self.itens = manual.ler_registo(FIXTURES / "curadoria_exemplo.yml")
        self.config = config_teste()

    def test_basta_data_canal_e_prova(self):
        """O pedido do autor era esse: a ligacao da prova e a data. Exigir o
        nome do programa punha uma pessoa a adivinha-lo."""
        self.assertEqual(len(self.itens), 2)
        primeiro = self.itens[0]
        self.assertEqual((primeiro.data_declarada, primeiro.canal, primeiro.programa), ("2021-03-15", "cmtv", ""))

    def test_a_origem_da_linha_ganha_a_da_fonte(self):
        """Quem acrescenta a mao tanto pode ter a pagina do canal como a
        noticia que a relata, e o site tem de dizer qual das duas e."""
        self.assertEqual(self.itens[0].origem, "imprensa")
        self.assertEqual(self.itens[1].origem, "")

    def test_entra_sem_prova_de_formato_no_titulo(self):
        """A isencao e a mesma do registo curado e tem a mesma
        justificacao: uma pessoa abriu a pagina. A primeira linha nao tem
        titulo nenhum e entra na mesma."""
        f = fonte(self.config, "registo-curado")
        emissao = criterio.avaliar(self.itens[0], f, self.config, [])
        self.assertIsNotNone(emissao)
        self.assertEqual(emissao.data, "2021-03-15")


class TestVetoDoQueJaEstaPublicado(unittest.TestCase):
    def test_retira_e_escreve_o_motivo_na_quarentena(self):
        """O erro que este teste trava: um veto que so apanhasse o que as
        fontes devolvem hoje deixaria a linha publicada no armazem, e
        remover passaria a exigir uma corrida com repor."""
        fundidas = {
            "a": {"id": "a", "fonte": "x", "prova_url": "https://www.exemplo.pt/peca/", "titulo": "T", "publicado_em": "2021-03-15"},
            "b": {"id": "b", "fonte": "x", "prova_url": "https://exemplo.pt/outra", "titulo": "U", "publicado_em": "2021-03-16"},
        }
        q = []
        # O endereco escrito na curadoria nao tem de bater letra a letra
        # com o publicado: e comparado normalizado, como em todo o projeto.
        ficam, vetadas = principal._aplicar_vetos(fundidas, {"https://exemplo.pt/peca": "e um debate"}, q)
        self.assertEqual(list(ficam), ["b"])
        self.assertEqual(vetadas, 1)
        self.assertEqual(q[0]["motivo"], "vetada_a_mao (e um debate)")
        self.assertEqual(q[0]["id_nativo"], "a")

    def test_sem_remocoes_nao_mexe_em_nada(self):
        fundidas = {"a": {"id": "a", "prova_url": "https://exemplo.pt/a"}}
        q = []
        ficam, vetadas = principal._aplicar_vetos(fundidas, {}, q)
        self.assertEqual((ficam, vetadas, q), (fundidas, 0, []))


if __name__ == "__main__":
    unittest.main()
