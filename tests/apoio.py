"""Apoio comum aos testes. Tudo offline."""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
FIXTURES = RAIZ / "tests" / "fixtures"

from recolha.modelos import Fonte, ItemBruto, carregar_config  # noqa: E402


def config_teste():
    return carregar_config(FIXTURES / "porquinho_teste.yml", FIXTURES / "fontes_teste.yml")


def fonte(config, fonte_id: str) -> Fonte:
    return next(f for f in config.fontes if f.id == fonte_id)


def item(**campos) -> ItemBruto:
    base = dict(
        id_nativo="x1",
        publicado_em="2025-09-05",
        titulo="Entrevista a André Ventura",
        url="https://exemplo.pt/x1",
        duracao_s=1800,
        descricao="",
        prova_url="https://exemplo.pt/x1",
    )
    base.update(campos)
    return ItemBruto(**base)


def ler(nome: str) -> str:
    return (FIXTURES / nome).read_text(encoding="utf-8")
