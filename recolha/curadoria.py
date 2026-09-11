"""Curadoria a mao: config/curadoria.yml.

Tres listas, e as tres sao decisoes de uma pessoa que abriu a pagina:

    entrevistas:       transmissoes acrescentadas a mao, com data, canal e prova
    remover:           provas que nao contam, com o motivo escrito
    mesma_entrevista:  provas que sao a mesma entrevista, com o canal a
                       que ela fica atribuida e o motivo escrito

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

O `mesma_entrevista` entrou a 2026-09-11, quando a unidade do projeto
passou a ser a entrevista e deixou de ser a emissao. Junta as
transmissoes da mesma entrevista e diz a qual dos canais ela fica
atribuida. Vive aqui, e nao num campo de cada linha do registo, por duas
razoes medidas:

1. **Funciona entre fontes.** Os cinco pares em que o mesmo programa
   passa nos dois canais do servico publico tem uma transmissao vinda de
   uma fonte automatica e outra do registo curado. Um campo escrito na
   linha do registo nunca chegaria a linha automatica, e as duas
   continuariam a contar como duas entrevistas.
2. **Ha uma so grafia do agrupamento.** Ate 2026-09-11 a chave era um
   campo de cada linha; duas linhas com a chave escrita de forma
   diferente eram dois grupos e duas contagens. E a licao decima oitava
   da KB, paga uma vez com o programa por apurar, e nao se repete aqui.

Porque o motivo e obrigatorio, nas duas listas: uma remocao ou um
agrupamento sem motivo sao indistinguiveis de um engano, e daqui a seis
meses ninguem sabe se aquela linha foi tratada por estar errada ou por
descuido. No `mesma_entrevista` o motivo e ainda a unica coisa que diz
se alguem leu as paginas, ou se o agrupamento vem herdado.

Porque o `canal` e obrigatorio e nao ha regra automatica que o adivinhe:
a KB ja mediu que o canal nao se le do dominio (8 linhas erradas em 8) e
que o identificador de video partilhado levanta a suspeita mas nao a
resolve. O canal a que uma entrevista fica atribuida e uma afirmacao de
quem leu a pagina, e escreve-se.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .modelos import RAIZ, url_normalizado

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


def ler_grupos(caminho: Path | None = None) -> dict[str, tuple[str, str]]:
    """{prova normalizada: (chave da entrevista, canal a que fica atribuida)}.

    A chave e o que junta as transmissoes; o canal e o que o site mostra
    e o que a contagem por canal soma. Uma prova que nao esteja aqui e
    uma entrevista por si, que e o caso da esmagadora maioria.

    Valida a serio, porque um erro aqui e uma contagem errada publicada:
    a chave, o canal e o motivo sao obrigatorios, a chave nao se repete e
    cada prova e um URL.

    O que **nao** se valida aqui e o numero de provas, e a razao vale a
    pena: ha grupos reais em que as duas transmissoes partilham a mesma
    pagina (o mesmo video servido nos dois dominios do grupo), e exigir
    duas provas obrigaria a escrever o mesmo endereco duas vezes. O erro
    que interessa apanhar e outro, e um endereco mal escrito nao o dava:
    quem o apanha e o aviso de recolha/entrevistas.py, que conta quantas
    transmissoes cada grupo juntou de facto.
    """
    caminho = caminho or FICHEIRO
    if not caminho.exists():
        return {}
    bruto = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    grupos: dict[str, tuple[str, str]] = {}
    chaves_vistas: set[str] = set()
    for posicao, grupo in enumerate(bruto.get("mesma_entrevista") or [], start=1):
        onde = f"{caminho.name}: mesma_entrevista, grupo {posicao}"
        if not isinstance(grupo, dict):
            raise ValueError(f"{onde}: tem de ter 'chave', 'canal', 'motivo' e 'provas'")
        chave = str(grupo.get("chave") or "").strip()
        canal = str(grupo.get("canal") or "").strip()
        motivo = str(grupo.get("motivo") or "").strip()
        provas = [str(u).strip() for u in (grupo.get("provas") or [])]
        if not chave:
            raise ValueError(f"{onde}: falta 'chave'")
        if chave in chaves_vistas:
            raise ValueError(f"{onde}: 'chave' repetida ({chave})")
        chaves_vistas.add(chave)
        if not canal:
            raise ValueError(f"{onde}: falta 'canal', que e o canal a que a entrevista fica atribuida")
        if not motivo:
            raise ValueError(f"{onde}: falta 'motivo'")
        if not provas:
            raise ValueError(f"{onde}: falta 'provas'")
        for prova in provas:
            if not prova.startswith(("https://", "http://")):
                raise ValueError(f"{onde}: prova tem de ser um URL ({prova})")
            grupos[url_normalizado(prova)] = (chave, canal)
    return grupos
