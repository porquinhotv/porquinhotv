"""Contrato das fontes.

Uma fonte devolve itens brutos: identificador, data de publicacao, titulo,
URL e, quando os conhece, duracao e descricao. Nao decide nada. Toda a
decisao esta em recolha/criterio.py, num sitio so.
"""

from __future__ import annotations

from typing import Iterable

from ..modelos import Fonte, ItemBruto

_REGISTO: dict[str, type["PluginDeFonte"]] = {}


class PluginDeFonte:
    tipo: str = ""

    def __init__(self, fonte: Fonte):
        self.fonte = fonte

    def obter(self) -> Iterable[ItemBruto]:
        raise NotImplementedError


def registar(cls: type[PluginDeFonte]) -> type[PluginDeFonte]:
    _REGISTO[cls.tipo] = cls
    return cls


def plugin_para(fonte: Fonte) -> PluginDeFonte | None:
    cls = _REGISTO.get(fonte.tipo)
    return cls(fonte) if cls else None


def tipos_conhecidos() -> list[str]:
    return sorted(_REGISTO)
