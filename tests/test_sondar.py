"""Sonda de hipoteses, sem rede.

O ponto que importa: uma hipotese que responde 200 mas nao traz ligacoes
tem de aparecer no relatorio como inutil, e nao como sucesso. Foi por ler
so o codigo de resposta que o arquivo.pt passou por fonte durante uma
corrida inteira.
"""

import tempfile
import unittest
from pathlib import Path

from tests.apoio import ler

from ferramentas import sondar
from recolha.rede import ErroDeRede


class TestAnalisar(unittest.TestCase):
    def test_conta_ligacoes_do_dominio(self):
        r = sondar.analisar(ler("pesquisa_resultados.html"), "https://exemplo.pt/p", ["Pessoa Exemplo"], "exemplo.pt")
        self.assertEqual(r["ligacoes"], 2)

    def test_pagina_de_aviso_responde_mas_nao_serve(self):
        html = "<html><body><h1>Verifique que nao e um robot</h1></body></html>"
        r = sondar.analisar(html, "https://motor.exemplo/q", ["ventura entrevista"], "")
        self.assertEqual(r["ligacoes"], 0)
        self.assertEqual(r["termos_presentes"], [])

    def test_termos_encontrados_no_texto(self):
        html = "<html><body>ventura entrevista exclusiva</body></html>"
        r = sondar.analisar(html, "https://x/y", ["ventura entrevista"], "")
        self.assertEqual(r["termos_presentes"], ["ventura entrevista"])


class TestCorrida(unittest.TestCase):
    def setUp(self):
        self.config = {
            "termo": "ventura entrevista",
            "grupos": [
                {"nome": "G1", "dominio_alvo": "exemplo.pt", "hipoteses": [
                    "https://exemplo.pt/pesquisa?q={termo}",
                    "https://falha.pt/?q={termo}",
                ]},
            ],
        }

    def _obter(self, url):
        if "falha" in url:
            raise ErroDeRede("HTTP Error 403")
        return ler("pesquisa_resultados.html")

    def test_corrida_e_relatorio(self):
        r = sondar.correr(self.config, obter=self._obter, dormir=lambda s: None)
        h = r["grupos"][0]["hipoteses"]
        self.assertTrue(h[0]["responde"])
        self.assertEqual(h[0]["ligacoes"], 2)
        self.assertFalse(h[1]["responde"])
        md = sondar.relatorio(r)
        self.assertIn("| G1", md) if "| G1" in md else self.assertIn("## G1", md)
        for t in ("\u2014", "\u2013"):
            self.assertNotIn(t, md)

    def test_termo_codificado_no_url(self):
        r = sondar.correr(self.config, obter=self._obter, dormir=lambda s: None)
        self.assertIn("ventura+entrevista", r["grupos"][0]["hipoteses"][0]["url"])

    def test_escrita_em_lf(self):
        r = sondar.correr(self.config, obter=self._obter, dormir=lambda s: None)
        with tempfile.TemporaryDirectory() as pasta:
            sondar.escrever(r, Path(pasta))
            for nome in ("sondagem.json", "SONDAGEM.md"):
                self.assertNotIn(b"\r\n", (Path(pasta) / nome).read_bytes())

    def test_configuracao_real_carrega(self):
        cfg = sondar.carregar()
        self.assertTrue(cfg["grupos"])
        self.assertTrue(cfg["dominios_de_interesse"], "sem dominios, um motor de busca nunca conta ligacoes")
        for g in cfg["grupos"]:
            self.assertTrue(g["hipoteses"], g["nome"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
