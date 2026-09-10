"""Curadoria a mao: config/curadoria.yml.

Duas listas, e as duas sao decisoes de uma pessoa que abriu a pagina:

    entrevistas:   emissoes acrescentadas a mao, com data, canal e prova
    remover:       provas que nao contam, com o motivo escrito

O `entrevistas` e lido pelo plugin `manual`, como o registo curado e o
clipping: mesmo formato, mesmo codigo, e uma fonte propria em
config/fontes.yml que corre a frente de tudo.

O `remover` vive aqui porque nao e uma fonte: e um veto que se aplica ao
que **qualquer** fonte devolver, e tambem ao que ja esta publicado.

**Isto fura a regra do append-only, e de proposito.** O dataset e
append-only para que uma linha nao desapareca quando a fonte que a
produzia deixa de a devolver. Uma remocao a mao e o contrario disso: e
alguem a afirmar que a linha esta errada. Para que nada se perca em
silencio, a linha removida vai para a quarentena com o motivo escrito
por quem a removeu, e continua visivel na pagina que publica a
quarentena. A Metodologia diz isto por palavras, na seccao das
correcoes.

Porque o motivo e obrigatorio: uma remocao sem motivo e indistinguivel
de um engano, e daqui a seis meses ninguem sabe se aquela linha foi
retirada por estar errada ou por descuido.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .modelos import RAIZ

FICHEIRO = RAIZ / "config" / "curadoria.yml"


def ler_remocoes(caminho: Path | None = None) -> dict[str, str]:
    """{prova: motivo} do ficheiro de curadoria. Vazio se nao existir.

    Nao normaliza os enderecos: quem chama e que sabe como os compara com
    os das emissoes, e ha uma so funcao no projeto a faze-lo.
    """
    caminho = caminho or FICHEIRO
    if not caminho.exists():
        return {}
    bruto = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    remocoes: dict[str, str] = {}
    for posicao, linha in enumerate(bruto.get("remover") or [], start=1):
        if not isinstance(linha, dict):
            raise ValueError(f"{caminho.name}: remover, linha {posicao}: tem de ter 'prova' e 'motivo'")
        prova = str(linha.get("prova") or "").strip()
        motivo = str(linha.get("motivo") or "").strip()
        if not prova.startswith(("https://", "http://")):
            raise ValueError(f"{caminho.name}: remover, linha {posicao}: prova tem de ser um URL")
        if not motivo:
            raise ValueError(f"{caminho.name}: remover, linha {posicao}: falta 'motivo'")
        remocoes[prova] = motivo
    return remocoes
