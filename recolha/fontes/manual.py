"""Registos verificados a mao: config/entrevistas.yml e config/clipping.yml.

A fonte principal deste projeto. Cada linha e uma emissao verificada por
uma pessoa, com o URL onde qualquer outra pessoa a pode ver ou ler. Sem
prova nao entra: a carga da prova esta do lado de quem publica o numero.

Os dois ficheiros usam o mesmo formato e o mesmo plugin. O que muda e a
`origem`, declarada na fonte em config/fontes.yml:

    origem: canal      o proprio canal publicou a entrevista
    origem: imprensa   uma peca de imprensa escrita noticia que a
                       entrevista aconteceu naquele dia, naquele canal

O clipping e o ultimo recurso, e por isso corre depois: quando o canal e
a imprensa cobrem a mesma emissao, fica a linha do canal.

Formato de cada linha:

    - data: 2026-09-04          # data de emissao, obrigatoria
      canal: id-do-canal        # id de config/porquinho.yml, obrigatorio
      programa: Jornal da Noite # obrigatorio
      prova: https://...        # onde se ve ou le, obrigatorio
      duracao_s: 2880           # segundos declarados; omitir se nao foi
                                # possivel apurar. Procurar sempre primeiro.
      titulo: ...               # opcional
      parcial: false            # true se so existem recortes online
      publicado_em: 2026-09-05  # opcional; por omissao igual a data
      mesma_entrevista: chave   # opcional; agrupa simulcast e repeticoes
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import yaml

from ..modelos import FICHEIRO_ENTREVISTAS, RAIZ, ItemBruto, id_estavel
from .base import PluginDeFonte, registar

OBRIGATORIOS = ("data", "canal", "programa", "prova")


def validar_linha(linha: dict, posicao: int) -> None:
    for campo in OBRIGATORIOS:
        if campo not in linha or linha[campo] in ("", None):
            raise ValueError(f"linha {posicao}: falta '{campo}'")
    prova = str(linha["prova"])
    if not prova.startswith(("https://", "http://")):
        raise ValueError(f"linha {posicao}: prova tem de ser um URL")
    duracao = linha.get("duracao_s")
    if duracao is not None and int(duracao) <= 0:
        # Zero nao e "sem duracao": sem duracao escreve-se omitindo o campo,
        # para que a diferenca entre "nao apurada" e "apurada" seja explicita.
        raise ValueError(f"linha {posicao}: duracao_s tem de ser positiva ou omitida")


def ler_registo(caminho: Path) -> list[ItemBruto]:
    bruto = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    itens: list[ItemBruto] = []
    for posicao, linha in enumerate(bruto.get("entrevistas") or [], start=1):
        try:
            validar_linha(linha, posicao)
        except ValueError as exc:
            raise ValueError(f"{caminho.name}: {exc}") from None
        data = str(linha["data"])
        prova = str(linha["prova"])
        duracao = linha.get("duracao_s")
        itens.append(
            ItemBruto(
                id_nativo=id_estavel(data, str(linha["canal"]), str(linha["programa"]), prova),
                publicado_em=str(linha.get("publicado_em") or data),
                titulo=str(linha.get("titulo") or ""),
                url=prova,
                duracao_s=None if duracao is None else int(duracao),
                descricao="",
                canal=str(linha["canal"]),
                programa=str(linha["programa"]),
                data_declarada=data,
                parcial=bool(linha.get("parcial", False)),
                mesma_entrevista=str(linha.get("mesma_entrevista") or ""),
                prova_url=prova,
            )
        )
    return itens


@registar
class FonteManual(PluginDeFonte):
    tipo = "manual"

    def obter(self) -> Iterable[ItemBruto]:
        caminho = RAIZ / self.fonte.ficheiro if self.fonte.ficheiro else FICHEIRO_ENTREVISTAS
        if not caminho.exists():
            return []
        itens = ler_registo(caminho)
        for item in itens:
            item.origem = self.fonte.origem
        return itens
