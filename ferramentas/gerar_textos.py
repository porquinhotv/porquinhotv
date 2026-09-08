"""Gera docs/textos.json a partir de config/humor.yml e config/comparacoes.yml.

    python -m ferramentas.gerar_textos            escreve
    python -m ferramentas.gerar_textos --check    so verifica

A camada satirica do site le este JSON e nunca os dados. Ha um teste que
corre o --check, por isso um YAML alterado sem regenerar o JSON parte a
suite antes de chegar ao site. Tambem valida o que o site vai assumir: um
so placeholder por frase, limites de humor crescentes, referencias
positivas.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
HUMOR = RAIZ / "config" / "humor.yml"
COMPARACOES = RAIZ / "config" / "comparacoes.yml"
ALVO = RAIZ / "docs" / "textos.json"

PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def validar(humor: dict, comparacoes: dict) -> None:
    anterior = -1
    humores = humor["humores"]
    for i, h in enumerate(humores):
        limite = h.get("ate_dias")
        if i < len(humores) - 1:
            if limite is None or limite <= anterior:
                raise ValueError(f"humor {h['id']}: ate_dias tem de ser crescente")
            anterior = limite
        elif limite is not None:
            raise ValueError("o ultimo humor tem de ter ate_dias: null")
        for frase in h["frases"]:
            extras = set(PLACEHOLDER.findall(frase)) - {"dias"}
            if extras:
                raise ValueError(f"humor {h['id']}: placeholder desconhecido {extras}")
    for c in comparacoes["comparacoes"]:
        if int(c["unidade_s"]) <= 0:
            raise ValueError(f"comparacao {c['id']}: unidade_s tem de ser positiva")
        for campo in ("artigo", "um", "varios", "nota"):
            if not c.get(campo):
                raise ValueError(f"comparacao {c['id']}: falta '{campo}'")


def construir() -> str:
    humor = yaml.safe_load(HUMOR.read_text(encoding="utf-8"))
    comparacoes = yaml.safe_load(COMPARACOES.read_text(encoding="utf-8"))
    validar(humor, comparacoes)
    conteudo = {
        "cabecalho": humor["cabecalho"],
        "estado": humor["estado"],
        "humores": humor["humores"],
        "frases": comparacoes["frases"],
        "comparacoes": comparacoes["comparacoes"],
    }
    return json.dumps(conteudo, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    gerado = construir()
    if "--check" in argv:
        atual = ALVO.read_text(encoding="utf-8") if ALVO.exists() else ""
        if atual != gerado:
            print("docs/textos.json desatualizado. Correr: python -m ferramentas.gerar_textos", file=sys.stderr)
            return 1
        print("docs/textos.json em dia")
        return 0
    ALVO.write_text(gerado, encoding="utf-8", newline="\n")  # ver gerar_metodologia
    print(f"escrito {ALVO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
