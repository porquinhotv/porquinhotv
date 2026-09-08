"""Append-only: primeira_vez nunca regride, ficheiros deterministas."""

import json
import tempfile
import unittest
from pathlib import Path

from tests.apoio import config_teste, fonte, item

from recolha import armazem, criterio


class TestFundir(unittest.TestCase):
    def setUp(self):
        self.config = config_teste()
        self.fonte = fonte(self.config, "podcast-exemplo")

    def test_preserva_primeira_vez(self):
        e = criterio.avaliar(item(), self.fonte, self.config, [])
        existentes = {e.id: {**e.como_dict(), "primeira_vez": "2020-01-01"}}
        fundidas, adicionadas, atualizadas = armazem.fundir(existentes, [e])
        self.assertEqual(fundidas[e.id]["primeira_vez"], "2020-01-01")
        self.assertEqual((adicionadas, atualizadas), (0, 0))

    def test_linha_nova_conta_como_adicionada(self):
        e = criterio.avaliar(item(), self.fonte, self.config, [])
        _, adicionadas, _ = armazem.fundir({}, [e])
        self.assertEqual(adicionadas, 1)

    def test_escrita_e_leitura_sao_estaveis(self):
        e = criterio.avaliar(item(), self.fonte, self.config, [])
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "emissoes.json"
            armazem.guardar({e.id: e.como_dict()}, caminho)
            primeira = caminho.read_text(encoding="utf-8")
            armazem.guardar(armazem.carregar(caminho), caminho)
            self.assertEqual(primeira, caminho.read_text(encoding="utf-8"))
            conteudo = json.loads(primeira)
            self.assertEqual(conteudo["total"], 1)
            self.assertIn("prova_url", conteudo["emissoes"][0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
