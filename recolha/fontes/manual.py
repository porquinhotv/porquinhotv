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
a imprensa cobrem a mesma entrevista, fica a linha do canal.

Formato de cada linha:

    - data: 2026-09-04          # dia em que passou, obrigatoria
      canal: id-do-canal        # id de config/porquinho.yml, obrigatorio
      prova: https://...        # onde se ve ou le, obrigatorio
      programa: Jornal da Noite # opcional desde 2026-09-10; ver abaixo
      origem: imprensa          # opcional; "canal" por omissao da fonte
      titulo: ...               # opcional
      publicado_em: 2026-09-05  # opcional; por omissao igual a data

O `mesma_entrevista` saiu da linha a 2026-09-11, quando a unidade do
projeto passou a ser a entrevista: agrupar duas transmissoes e agora uma
entrada da tabela `mesma_entrevista` de config/curadoria.yml, com o canal
a que a entrevista fica atribuida e o motivo escrito. Uma linha que ainda
o traga e recusada, e nao ignorada, porque um campo que ficasse no
ficheiro a fingir que agrupa deixaria duas entrevistas a contar onde ha
uma. Ver recolha/entrevistas.py.

O `programa` passou a ser opcional a 2026-09-10, quando se acrescentou a
curadoria a mao: para acrescentar uma transmissao basta saber o dia, o
canal e a prova, e obrigar a escrever o nome do programa punha uma pessoa
a adivinha-lo ou a inventa-lo. Sem ele, a transmissao nao abre bloco
proprio num dia em que o canal ja tem outra com programa apurado, o que e
o comportamento certo: nao se sabe se foi a mesma, logo nao se afirma que
foram duas. Ver recolha/criterio.py, _absorver_sem_programa.

A `origem` por linha existe pela mesma razao: quem acrescenta a mao tanto
pode ter a pagina do canal como a noticia que a relata, e o site diz qual
das duas e. Sem ela, a linha herda a origem da fonte.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import yaml

from ..modelos import FICHEIRO_ENTREVISTAS, RAIZ, ItemBruto, id_estavel
from .base import PluginDeFonte, registar

OBRIGATORIOS = ("data", "canal", "prova")
# Retirados a 2026-09-10 com a duracao. Ver recolha/criterio.py.
CAMPOS_RETIRADOS = ("duracao_s", "parcial")
# Retirado a 2026-09-11 com o conceito de emissao: o agrupamento passou
# para a tabela `mesma_entrevista` de config/curadoria.yml, para ter uma
# so grafia e para funcionar tambem entre fontes diferentes.
CAMPO_MUDOU_DE_SITIO = {
    "mesma_entrevista": "passou a 2026-09-11 para a tabela 'mesma_entrevista' de config/curadoria.yml",
}


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
    for campo, para_onde in CAMPO_MUDOU_DE_SITIO.items():
        if campo in linha:
            raise ValueError(f"linha {posicao}: '{campo}' {para_onde}")


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
                id_nativo=id_estavel(data, str(linha["canal"]), str(linha.get("programa") or ""), prova),
                publicado_em=str(linha.get("publicado_em") or data),
                titulo=str(linha.get("titulo") or ""),
                url=prova,
                descricao="",
                canal=str(linha["canal"]),
                programa=str(linha.get("programa") or ""),
                data_declarada=data,
                prova_url=prova,
                origem=str(linha.get("origem") or ""),
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
            # A origem escrita na linha ganha a da fonte: uma linha da
            # curadoria pode ter prova de canal ou prova de imprensa.
            item.origem = item.origem or self.fonte.origem
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

    O que se perde e sabido: as entrevistas que o canal titula com a
    citacao em vez da palavra ficam de fora, em `formato_nao_apurado`.
    """

    tipo = "registo_automatico"
