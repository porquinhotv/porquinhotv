"""Registos em ficheiro: config/entrevistas.yml e config/clipping.yml.

A fonte principal deste projeto. Cada linha traz o URL onde qualquer
pessoa a pode ver ou ler. Sem prova nao entra: a carga da prova esta do
lado de quem publica o numero. No registo do canal quem verificou foi uma
pessoa; no clipping, desde 2026-09-09, quem verificou foi a ferramenta,
contra condicoes que quem abrir a peca confirma.

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
      titulo: ...               # opcional
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
# Retirados a 2026-09-10 com a duracao. Ver recolha/criterio.py.
CAMPOS_RETIRADOS = ("duracao_s", "parcial")


def validar_linha(linha: dict, posicao: int) -> None:
    for campo in OBRIGATORIOS:
        if campo not in linha or linha[campo] in ("", None):
            raise ValueError(f"linha {posicao}: falta '{campo}'")
    prova = str(linha["prova"])
    if not prova.startswith(("https://", "http://")):
        raise ValueError(f"linha {posicao}: prova tem de ser um URL")
    for campo in CAMPOS_RETIRADOS:
        if campo in linha:
            # Um campo que o modelo deixou de ter nao pode ficar no ficheiro
            # a fingir que conta: quem o le acreditava que o site o usava.
            raise ValueError(f"linha {posicao}: '{campo}' deixou de existir a 2026-09-10; apagar a linha")


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
        itens.append(
            ItemBruto(
                id_nativo=id_estavel(data, str(linha["canal"]), str(linha["programa"]), prova),
                publicado_em=str(linha.get("publicado_em") or data),
                titulo=str(linha.get("titulo") or ""),
                url=prova,
                descricao="",
                canal=str(linha["canal"]),
                programa=str(linha["programa"]),
                data_declarada=data,
                mesma_entrevista=str(linha.get("mesma_entrevista") or ""),
                prova_url=prova,
            )
        )
    return itens


@registar
class FonteManual(PluginDeFonte):
    tipo = "manual"

    def obter(self, termos: list[str] | None = None, registo: list | None = None) -> Iterable[ItemBruto]:
        caminho = RAIZ / self.fonte.ficheiro if self.fonte.ficheiro else FICHEIRO_ENTREVISTAS
        if not caminho.exists():
            return []
        itens = ler_registo(caminho)
        for item in itens:
            item.origem = self.fonte.origem
        return itens


@registar
class FonteRegistoAutomatico(FonteManual):
    """O mesmo ficheiro, sem a isencao que so uma pessoa justifica.

    A fonte `manual` salta a prova positiva de formato e as rondas de
    confirmacao, e a justificacao escrita dessa isencao e uma pessoa ter
    aberto a pagina. Este tipo le exatamente o mesmo formato, mas o
    criterio trata-o como qualquer fonte automatica: o titulo tem de
    provar que e uma entrevista, e o bloco tem de ser visto nas rondas
    normais antes de ser publicado.

    Existe porque havia 150 provas em dominio de canal ja colhidas e
    verificadas, paradas so porque o registo do canal exige um `sim`
    escrito linha a linha, que e o padrao que este projeto abandonou a
    2026-09-09. Aqui a avaliacao decide e uma pessoa veta, como no
    clipping, e o que compensa a falta da leitura humana e o rigor do
    criterio, nao a confianca na fonte.

    O que se perde e sabido: as emissoes que o canal titula com a citacao
    em vez da palavra ficam de fora, em `formato_nao_apurado`.
    """

    tipo = "registo_automatico"
