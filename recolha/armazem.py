"""Persistencia. Append-only.

Um registo que ja existe nunca perde a sua `primeira_vez`. Os ficheiros
sao escritos com chaves ordenadas e indentacao fixa para que o diff do git
seja legivel: o historico do repositorio e a trilha de auditoria.

Consequencia a nao esquecer: uma linha que deixe de ser produzida nao
desaparece sozinha. Corrigir uma regra que muda classificacoes obriga a
repor docs/dados e a recolher de novo, na mesma operacao.
"""

from __future__ import annotations

import json
from pathlib import Path

from .modelos import DADOS_DIR, Emissao

EMISSOES = DADOS_DIR / "emissoes.json"
QUARENTENA = DADOS_DIR / "quarentena.json"
ESQUEMA = 1


def carregar(caminho: Path = EMISSOES) -> dict[str, dict]:
    if not caminho.exists():
        return {}
    conteudo = json.loads(caminho.read_text(encoding="utf-8"))
    return {linha["id"]: linha for linha in conteudo.get("emissoes", [])}


def fundir(existentes: dict[str, dict], novas: list[Emissao]) -> tuple[dict, int, int]:
    adicionadas = 0
    atualizadas = 0
    for emissao in novas:
        linha = emissao.como_dict()
        atual = existentes.get(linha["id"])
        if atual is None:
            existentes[linha["id"]] = linha
            adicionadas += 1
            continue
        linha["primeira_vez"] = atual.get("primeira_vez", linha["primeira_vez"])
        if linha != atual:
            existentes[linha["id"]] = linha
            atualizadas += 1
    return existentes, adicionadas, atualizadas


def _escrever(caminho: Path, conteudo: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" para que o ficheiro seja identico seja qual for o
    # sistema que correu a recolha: em CRLF, o diff do git mostraria o
    # ficheiro inteiro alterado e a trilha de auditoria deixaria de servir.
    caminho.write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def guardar(linhas: dict[str, dict], caminho: Path = EMISSOES) -> None:
    ordenadas = sorted(linhas.values(), key=lambda r: (r["data"], r["canal"], r["id"]))
    _escrever(caminho, {"esquema": ESQUEMA, "total": len(ordenadas), "emissoes": ordenadas})


def guardar_quarentena(entradas: list[dict], caminho: Path = QUARENTENA) -> None:
    """Rejeitados desta corrida, com motivo. Substituido a cada corrida:
    e uma fotografia, nao um historico."""
    ordenadas = sorted(entradas, key=lambda e: (e["fonte"], e.get("publicado_em", ""), e["titulo"]))
    _escrever(caminho, {"esquema": ESQUEMA, "total": len(ordenadas), "entradas": ordenadas})
