"""O que o publico le tem de ser o que o projeto faz.

- a Metodologia HTML corresponde ao Markdown;
- os textos satiricos no site correspondem ao YAML;
- sem travessoes nos textos versionados;
- o site nao pede nada a terceiros;
- nenhum nome de canal ou pessoa no codigo Python;
- sem metadados de editor nos SVG.
"""

import re
import unittest

from tests.apoio import RAIZ

from ferramentas import gerar_metodologia, gerar_textos

TRAVESSOES = ("\u2014", "\u2013")
TEXTO_VERSIONADO = [RAIZ / "METODOLOGIA.md", RAIZ / "README.md"]
TEXTO_VERSIONADO += sorted((RAIZ / "config").glob("*.yml"))
TEXTO_VERSIONADO += sorted((RAIZ / "docs").glob("*.html")) + sorted((RAIZ / "docs").glob("*.js")) + sorted((RAIZ / "docs").glob("*.css"))
# Unico esquema externo permitido: o namespace do SVG, que nao e um pedido.
URL_PERMITIDO = re.compile(r"https?://(www\.)?w3\.org/")
NOMES_PROIBIDOS_NO_CODIGO = re.compile(r"\b(ventura|chega|rtp\d?|sic|tvi|cnn|cmtv|milhazes|rogeiro)\b", re.IGNORECASE)


class TestArtefactosGerados(unittest.TestCase):
    def test_metodologia_html_em_dia(self):
        self.assertEqual(gerar_metodologia.ALVO.read_text(encoding="utf-8"), gerar_metodologia.construir(),
                         "correr: python -m ferramentas.gerar_metodologia")

    def test_textos_json_em_dia(self):
        self.assertEqual(gerar_textos.ALVO.read_text(encoding="utf-8"), gerar_textos.construir(),
                         "correr: python -m ferramentas.gerar_textos")

    def test_validacao_dos_textos_apanha_erros(self):
        mau = {"humores": [{"id": "a", "ate_dias": 3, "frases": ["{x}"]}, {"id": "b", "ate_dias": None, "frases": []}]}
        with self.assertRaises(ValueError):
            gerar_textos.validar(mau, {"comparacoes": []})
        desordem = {"humores": [{"id": "a", "ate_dias": 3, "frases": []}, {"id": "b", "ate_dias": 2, "frases": []}, {"id": "c", "ate_dias": None, "frases": []}]}
        with self.assertRaises(ValueError):
            gerar_textos.validar(desordem, {"comparacoes": []})


class TestConvencoes(unittest.TestCase):
    def test_sem_travessoes(self):
        for caminho in TEXTO_VERSIONADO:
            with self.subTest(ficheiro=caminho.name):
                for n, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1):
                    for t in TRAVESSOES:
                        self.assertNotIn(t, linha, f"{caminho.name}:{n}")

    def test_o_site_nao_pede_nada_a_terceiros(self):
        for caminho in sorted((RAIZ / "docs").glob("*.html")) + sorted((RAIZ / "docs").glob("*.js")) + sorted((RAIZ / "docs").glob("*.css")):
            with self.subTest(ficheiro=caminho.name):
                for url in re.findall(r"https?://[^\s\"'<>)]+", caminho.read_text(encoding="utf-8")):
                    self.assertRegex(url, URL_PERMITIDO, f"pedido externo em {caminho.name}: {url}")

    def test_sem_google_no_site(self):
        for caminho in sorted((RAIZ / "docs").glob("*.html")) + sorted((RAIZ / "docs").glob("*.css")):
            self.assertNotIn("google", caminho.read_text(encoding="utf-8").lower(), caminho.name)

    def test_nenhum_nome_no_codigo_python(self):
        for caminho in sorted((RAIZ / "recolha").rglob("*.py")) + sorted((RAIZ / "ferramentas").glob("*.py")):
            with self.subTest(ficheiro=caminho.name):
                texto = caminho.read_text(encoding="utf-8")
                self.assertIsNone(NOMES_PROIBIDOS_NO_CODIGO.search(texto), f"nome editorial em {caminho}")

    def test_svg_sem_metadados_de_editor(self):
        for caminho in sorted((RAIZ / "docs").glob("*.svg")):
            texto = caminho.read_text(encoding="utf-8").lower()
            for marca in ("inkscape", "sodipodi", "illustrator", "adobe", "sketch", "figma"):
                self.assertNotIn(marca, texto, f"{caminho.name} tem metadados de {marca}")

    def test_nenhum_documento_afirma_uma_duracao_minima(self):
        """A duracao minima foi removida. Uma suposicao que cai tem de cair
        em todas as suas copias, senao o documento publico continua a
        afirmar uma regra que o codigo ja nao aplica."""
        for caminho in TEXTO_VERSIONADO + sorted((RAIZ / "recolha").rglob("*.py")):
            texto = caminho.read_text(encoding="utf-8")
            with self.subTest(ficheiro=caminho.name):
                self.assertNotIn("duracao_minima", texto, caminho.name)
                self.assertNotIn("duração mínima de", texto, caminho.name)

    def test_ficheiros_em_lf(self):
        """Inclui os ficheiros de dados: gerados em CRLF, o diff do git
        mostraria o ficheiro inteiro alterado a cada corrida e a trilha de
        auditoria deixaria de servir para o que existe."""
        alvos = TEXTO_VERSIONADO + sorted((RAIZ / "recolha").rglob("*.py"))
        alvos += sorted((RAIZ / "docs" / "dados").glob("*.json"))
        alvos += [RAIZ / "docs" / "textos.json"]
        for caminho in alvos:
            if not caminho.exists():
                continue
            with self.subTest(ficheiro=caminho.name):
                self.assertNotIn(b"\r\n", caminho.read_bytes(), f"CRLF em {caminho.name}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
