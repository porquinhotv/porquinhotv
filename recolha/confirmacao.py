"""Confirmacao em rondas.

Decisao editorial do autor: uma transmissao vinda de fonte automatica
so entra no dataset publicado depois de ser encontrada em rondas
distintas.

O que isto protege, e o que nao protege, dito com clareza porque a
Metodologia tem de o dizer tambem:

PROTEGE de um erro transitorio da recolha. Uma pagina que veio truncada,
um JSON-LD malformado nesse dia, uma pesquisa que devolveu lixo por causa
de uma remodelacao a meio: qualquer destes injectaria uma entrevista
falsa numa recolha de ronda unica. Exigir que o mesmo bloco apareca outra vez,
noutra corrida, noutro dia, elimina esta classe de erro por completo.

NAO PROTEGE de a fonte estar errada. Se a pagina do canal diz o que nao
e, dira o mesmo nas tres rondas. Repetir a leitura de uma fonte nao a
torna mais verdadeira. O que aumenta mesmo a fiabilidade e a corroboracao
por fontes diferentes, e por isso o numero de fontes distintas que viram
cada bloco fica registado e e publicado ao lado de cada linha.

O registo de avistamentos vive em docs/dados/candidatos.json, e append-only
como o resto: um avistamento nunca e apagado, mesmo quando o bloco ja foi
promovido. E a trilha que permite a qualquer pessoa reconstruir porque e
que uma linha entrou e em que dia.
"""

from __future__ import annotations

import json
from pathlib import Path

from .modelos import DADOS_DIR, Transmissao

CANDIDATOS = DADOS_DIR / "candidatos.json"
ESQUEMA = 1


def carregar(caminho: Path = CANDIDATOS) -> dict[str, dict]:
    if not caminho.exists():
        return {}
    conteudo = json.loads(caminho.read_text(encoding="utf-8"))
    return {linha["bloco"]: linha for linha in conteudo.get("candidatos", [])}


def registar(candidatos: dict[str, dict], transmissoes: list[Transmissao], ronda: str) -> dict[str, dict]:
    """Averba um avistamento por bloco nesta ronda. Nunca apaga nada."""
    for transmissao in transmissoes:
        linha = candidatos.setdefault(
            transmissao.bloco,
            {"bloco": transmissao.bloco, "rondas": [], "fontes": [], "primeira_ronda": ronda, "titulo": transmissao.titulo, "prova_url": transmissao.prova_url},
        )
        if ronda not in linha["rondas"]:
            linha["rondas"].append(ronda)
        if transmissao.fonte not in linha["fontes"]:
            linha["fontes"].append(transmissao.fonte)
        linha["ultima_ronda"] = ronda
    return candidatos


def confirmados(candidatos: dict[str, dict], minimo: int) -> set[str]:
    return {bloco for bloco, linha in candidatos.items() if len(linha.get("rondas", [])) >= minimo}


def filtrar(
    transmissoes: list[Transmissao], candidatos: dict[str, dict], minimo: int, quarentena: list | None = None
) -> list[Transmissao]:
    """Deixa passar as transmissoes cujo bloco ja foi visto em `minimo` rondas.

    As restantes vao para a quarentena como `aguarda_confirmacao (n de m)`,
    visiveis e com o URL: nada e descartado em silencio, e quem consulta a
    quarentena ve exactamente o que esta a espera de segunda leitura.
    """
    prontos = confirmados(candidatos, minimo)
    passam: list[Transmissao] = []
    for transmissao in transmissoes:
        if transmissao.bloco in prontos:
            passam.append(transmissao)
            continue
        vistas = len(candidatos.get(transmissao.bloco, {}).get("rondas", []))
        if quarentena is not None:
            quarentena.append(
                {
                    "fonte": transmissao.fonte,
                    "id_nativo": transmissao.id,
                    "publicado_em": transmissao.publicado_em,
                    "titulo": transmissao.titulo,
                    "url": transmissao.prova_url,
                    "motivo": f"aguarda_confirmacao ({vistas} de {minimo} rondas)",
                    "excerto": "",
                }
            )
    return passam


def anotar(transmissoes: list[Transmissao], candidatos: dict[str, dict]) -> list[Transmissao]:
    """Escreve em cada transmissao quantas rondas e quantas fontes a viram.

    O site publica estes dois numeros ao lado da linha. Sao a medida
    honesta da forca de cada registo: rondas dizem que a leitura e
    estavel, fontes distintas dizem que ha corroboracao.
    """
    for transmissao in transmissoes:
        linha = candidatos.get(transmissao.bloco, {})
        transmissao.rondas = len(linha.get("rondas", []))
        transmissao.fontes_distintas = len(linha.get("fontes", []))
    return transmissoes


def guardar(candidatos: dict[str, dict], caminho: Path = CANDIDATOS) -> None:
    ordenados = sorted(candidatos.values(), key=lambda r: r["bloco"])
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps({"esquema": ESQUEMA, "total": len(ordenados), "candidatos": ordenados}, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
