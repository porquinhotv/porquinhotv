"""Politica de repeticao. Tudo offline, sem um unico pedido real.

O que importa aqui foi aprendido numa sondagem real: o motor de busca
respondeu 429 ao terceiro pedido seguido. Tratar um 429 como uma falha
de rede qualquer, repetindo dois segundos depois, so gasta a paciencia
de quem responde e volta a levar 429.
"""

import unittest
import urllib.error
from unittest import mock

from tests.apoio import RAIZ  # noqa: F401

from recolha import rede


def _http_error(codigo, cabecalhos=None):
    """HTTPError e um objecto de ficheiro: sem o fechar, o Python avisa
    com um ResourceWarning no meio da saida dos testes."""
    erro = urllib.error.HTTPError("https://exemplo.pt/x", codigo, "erro", cabecalhos or {}, None)
    erro.close()
    return erro


class TestRepeticao(unittest.TestCase):
    def setUp(self):
        self.esperas = []
        mock.patch.object(rede.time, "sleep", self.esperas.append).start()
        self.addCleanup(mock.patch.stopall)

    def _correr(self, efeitos):
        with mock.patch.object(rede.urllib.request, "urlopen", side_effect=efeitos):
            with self.assertRaises(rede.ErroDeRede):
                rede.obter_texto("https://exemplo.pt/x")

    def test_429_espera_muito_mais_do_que_um_erro_qualquer(self):
        self._correr([_http_error(429)] * 3)
        self.assertTrue(self.esperas, "nao esperou nada")
        self.assertGreaterEqual(min(self.esperas), 20.0, f"esperas curtas demais: {self.esperas}")

    def test_429_respeita_retry_after(self):
        self._correr([_http_error(429, {"Retry-After": "45"})] * 3)
        self.assertIn(45.0, self.esperas)

    def test_retry_after_absurdo_e_limitado(self):
        self._correr([_http_error(429, {"Retry-After": "99999"})] * 3)
        self.assertLessEqual(max(self.esperas), rede.ESPERA_MAXIMA)

    def test_retry_after_ilegivel_nao_rebenta(self):
        self._correr([_http_error(429, {"Retry-After": "amanha"})] * 3)
        self.assertTrue(self.esperas)

    def test_403_nao_se_repete(self):
        """Um 403 nao muda por se insistir. Repetir tres vezes cada URL
        recusado triplicava o tempo da corrida sem mudar o resultado."""
        chamadas = []

        def efeito(*args, **kwargs):
            chamadas.append(1)
            raise _http_error(403)

        with mock.patch.object(rede.urllib.request, "urlopen", side_effect=efeito):
            with self.assertRaises(rede.ErroDeRede):
                rede.obter_texto("https://exemplo.pt/x")
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(self.esperas, [])

    def test_404_nao_se_repete(self):
        chamadas = []

        def efeito(*args, **kwargs):
            chamadas.append(1)
            raise _http_error(404)

        with mock.patch.object(rede.urllib.request, "urlopen", side_effect=efeito):
            with self.assertRaises(rede.ErroDeRede):
                rede.obter_texto("https://exemplo.pt/x")
        self.assertEqual(len(chamadas), 1)

    def test_500_repete_com_espera_curta(self):
        self._correr([_http_error(500)] * 3)
        self.assertTrue(self.esperas)
        self.assertLess(max(self.esperas), 20.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
