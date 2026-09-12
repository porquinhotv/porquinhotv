"""Gera docs/textos.json a partir de config/humor.yml.

    python -m ferramentas.gerar_textos            escreve
    python -m ferramentas.gerar_textos --check    so verifica

A camada satirica do site le este JSON e nunca os dados: as frases do
porquinho e as das metricas. Ha um teste que corre o --check, por isso um
YAML alterado sem regenerar o JSON parte a suite antes de chegar ao site.
Tambem valida o que o site vai assumir: so os placeholders que ele sabe
preencher, e escadas com limites crescentes e ultimo degrau aberto.

As comparacoes de tempo (config/comparacoes.yml) sairam a 2026-09-10 com
a duracao: sem tempo medido nao ha nada para dividir.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
HUMOR = RAIZ / "config" / "humor.yml"
ALVO = RAIZ / "docs" / "textos.json"

PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def validar_texto(texto: str, permitidos: set, onde: str) -> None:
    extras = set(PLACEHOLDER.findall(texto)) - permitidos
    if extras:
        raise ValueError(f"{onde}: placeholder desconhecido {extras}")


def validar_escada(degraus: list, campo: str, permitidos: set, onde: str) -> None:
    """Limites crescentes e ultimo degrau aberto, senao um valor cai entre
    dois degraus e o site fica sem frase. Serve o humor (por dias) e as
    metricas (por numero de entrevistas)."""
    anterior = -1
    for i, degrau in enumerate(degraus):
        limite = degrau.get(campo)
        if i < len(degraus) - 1:
            if limite is None or limite <= anterior:
                raise ValueError(f"{onde}: {campo} tem de ser crescente")
            anterior = limite
        elif limite is not None:
            raise ValueError(f"{onde}: o ultimo degrau tem de ter {campo}: null")
        for frase in degrau["frases"]:
            validar_texto(frase, permitidos, onde)


def validar_temporada(metricas: dict) -> None:
    """O numero de temporadas nao se escreve a mao: sai da contagem do
    periodo, dividida pelos episodios configurados. Esta validacao existe
    porque a alternativa a um ordinal em falta e o site escrever um numero
    que ninguem mediu, e porque uma frase com {temporada} sem o bloco
    configurado nunca chegaria a aparecer."""
    bloco = metricas.get("temporada")
    usa = any("{temporada}" in frase
              for degrau in metricas.get("total") or []
              for frase in degrau["frases"])
    if bloco is None:
        if usa:
            raise ValueError("metricas.temporada: falta o bloco e ha frases que o pedem")
        return
    episodios = bloco.get("episodios")
    if not isinstance(episodios, int) or episodios < 1:
        raise ValueError("metricas.temporada: `episodios` tem de ser um inteiro positivo")
    ordinais = bloco.get("ordinais") or {}
    if not ordinais:
        raise ValueError("metricas.temporada: `ordinais` nao pode ficar vazio")
    for chave, valor in ordinais.items():
        if not isinstance(chave, int) or chave < 1:
            raise ValueError(f"metricas.temporada: chave {chave!r} nao e um numero de temporada")
        if not isinstance(valor, str) or not valor.strip():
            raise ValueError(f"metricas.temporada: o ordinal de {chave} tem de ser texto")


def normalizar_temporada(metricas: dict) -> dict:
    """As chaves dos ordinais sao numeros no YAML e texto no JSON. A
    conversao fica aqui, e nao no site, para que o browser leia sempre a
    mesma forma independentemente do que o YAML permitir."""
    bloco = metricas.get("temporada")
    if not bloco:
        return metricas
    copia = dict(metricas)
    copia["temporada"] = dict(bloco, ordinais={str(k): v for k, v in bloco["ordinais"].items()})
    return copia


def validar(humor: dict) -> None:
    validar_escada(humor["humores"], "ate_dias", {"dias"}, "humores")
    metricas = humor.get("metricas") or {}
    if "total" in metricas:
        validar_escada(metricas["total"], "ate", {"n", "temporada"}, "metricas.total")
    validar_temporada(metricas)
    if "lider" in metricas:
        validar_texto(metricas["lider"], {"canal", "n"}, "metricas.lider")
    for chave, texto in (metricas.get("legendas") or {}).items():
        validar_texto(texto, set(), f"metricas.legendas.{chave}")


def construir() -> str:
    humor = yaml.safe_load(HUMOR.read_text(encoding="utf-8"))
    validar(humor)
    conteudo = {
        "cabecalho": humor["cabecalho"],
        "estado": humor["estado"],
        "humores": humor["humores"],
        "metricas": normalizar_temporada(humor.get("metricas") or {}),
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
