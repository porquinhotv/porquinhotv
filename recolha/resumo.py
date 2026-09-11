"""Agregados prontos para o site.

O site nao calcula nada que nao esteja aqui, exceto somas de periodo a
partir das repartições diarias. Tudo o que e uma conta nova vive neste
ficheiro, com teste, e nunca no JavaScript.

Ha uma unidade so, e e o ponto deste ficheiro: a **entrevista
exclusiva**. Cada balde traz um numero, `entrevistas`. Uma entrevista que
passe em dois canais conta uma vez, e conta no canal a que esta
atribuida.

Ate 2026-09-11 cada balde trazia dois numeros, `emissoes` e
`entrevistas_distintas`, porque a unidade era a emissao e o site
escrevia os dois ao lado um do outro. O autor retirou o conceito de
emissao do projeto: dois numeros para a mesma coisa obrigavam quem lia o
site a perceber a diferenca antes de perceber o numero. `esquema` subiu
para 3 para que um site antigo nao leia um resumo novo e some campos que
ja nao existem.

Nao ha tempo, desde 2026-09-10, e nao ha duracao em campo nenhum.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from .modelos import DADOS_DIR, Config

RESUMO = DADOS_DIR / "resumo.json"


def semana_iso(iso: str) -> str:
    ano, semana, _ = date.fromisoformat(iso).isocalendar()
    return f"{ano}-W{semana:02d}"


ESQUEMA = 3


def _balde() -> dict:
    return {"entrevistas": 0}


def _fechar(balde: dict) -> dict:
    return {"entrevistas": balde["entrevistas"]}


def _somar(balde: dict, entrevista: dict) -> None:
    """Uma entrevista, um incremento.

    As entradas que chegam aqui ja vem dobradas por
    recolha/entrevistas.py: uma entrevista que passou em dois canais e uma
    entrada so. Nao ha nada a deduplicar neste ficheiro, e por isso o
    site pode somar periodos a partir das reparticoes diarias com uma
    soma simples.
    """
    balde["entrevistas"] += 1


def recordes(datas: list[str]) -> dict:
    """Ultima data, maior intervalo sem entrevistas e maior sequencia de
    dias seguidos com entrevista. Datas distintas, ordenadas."""
    if not datas:
        return {"ultima_data": None, "maior_jejum": None, "maior_maratona": None}
    dias = [date.fromisoformat(d) for d in datas]
    jejum = {"dias": 0, "de": None, "ate": None}
    maratona = {"dias": 1, "de": datas[0], "ate": datas[0]}
    inicio_corrida = 0
    for i in range(1, len(dias)):
        intervalo = (dias[i] - dias[i - 1]).days
        if intervalo - 1 > jejum["dias"]:
            jejum = {"dias": intervalo - 1, "de": datas[i - 1], "ate": datas[i]}
        if intervalo == 1:
            comprimento = i - inicio_corrida + 1
            if comprimento > maratona["dias"]:
                maratona = {"dias": comprimento, "de": datas[inicio_corrida], "ate": datas[i]}
        else:
            inicio_corrida = i
    return {
        "ultima_data": datas[-1],
        "maior_jejum": jejum if jejum["dias"] > 0 else None,
        "maior_maratona": maratona,
    }


def construir(entrevistas: list[dict], config: Config) -> dict:
    # Ambito visivel (decisao do autor, 2026-09-11): o site mostra e conta
    # a partir de tema.visivel_desde. As linhas anteriores nao se apagam,
    # continuam em entrevistas.json; aqui ficam fora de todos os agregados,
    # para que nenhum numero do site as some, e saem contadas em
    # `ambito.fora_do_ambito`, porque nada se descarta em silencio. A
    # razao esta na Metodologia: antes do corte a cobertura das vias de
    # recolha e residual e desigual entre canais, e somar esses anos seria
    # apresentar ausencia de cobertura como medicao.
    corte = config.tema.visivel_desde or config.tema.desde
    fora = _balde()
    visiveis = []
    for entrevista in entrevistas:
        if entrevista["data"] < corte:
            _somar(fora, entrevista)
        else:
            visiveis.append(entrevista)

    total = _balde()
    por_dia: dict = defaultdict(_balde)
    por_semana: dict = defaultdict(_balde)
    por_mes: dict = defaultdict(_balde)
    por_ano: dict = defaultdict(_balde)
    por_canal: dict = defaultdict(_balde)
    canal_por_dia: dict = defaultdict(lambda: defaultdict(lambda: {**_balde(), "declaradas": 0}))
    por_origem: dict = defaultdict(_balde)

    for entrevista in visiveis:
        data = entrevista["data"]
        _somar(total, entrevista)
        _somar(por_dia[data], entrevista)
        _somar(por_semana[semana_iso(data)], entrevista)
        _somar(por_mes[data[:7]], entrevista)
        _somar(por_ano[data[:4]], entrevista)
        # Uma entrevista conta no canal a que esta atribuida, e so nesse.
        # Somar tambem nos outros canais em que passou daria uma
        # reparticao cuja soma e maior do que o total, que e exactamente o
        # numero que o site deixou de publicar.
        _somar(por_canal[entrevista["canal"]], entrevista)
        _somar(por_origem[entrevista.get("origem") or "canal"], entrevista)
        celula = canal_por_dia[data][entrevista["canal"]]
        _somar(celula, entrevista)
        if entrevista.get("data_origem") == "declarada":
            celula["declaradas"] += 1

    datas = sorted(por_dia)
    tema = config.tema
    return {
        "esquema": ESQUEMA,
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tema": {
            "id": tema.id,
            "nome": tema.nome,
            "pergunta": tema.pergunta,
            "desde": tema.desde,
            "desde_rotulo": tema.desde_rotulo,
        },
        "sujeito": {"id": config.sujeito.id, "nome": config.sujeito.nome},
        # O ambito visivel, dito por extenso para o site e para quem abrir
        # o ficheiro: de onde o site conta, desde quando a recolha aceita,
        # e quanto existe no dataset antes do corte.
        "ambito": {
            "recolha_desde": tema.desde,
            "visivel_desde": corte,
            "rotulo": tema.visivel_rotulo or tema.desde_rotulo,
            "tab": tema.visivel_tab,
            "fora_do_ambito": _fechar(fora),
        },
        "primeiro_registo": datas[0] if datas else None,
        "ultimo_registo": datas[-1] if datas else None,
        "totais": _fechar(total),
        # Ate 2026-09-11 cada dia trazia tambem a lista das chaves de
        # entrevista, para o site poder contar distintas num periodo sem
        # duplicar simulcasts. Com a entrevista como unidade, uma entrada
        # e uma entrevista e a soma de um periodo e uma soma: a lista
        # deixou de ter para que servir.
        "por_dia": [{"data": d, **_fechar(por_dia[d])} for d in datas],
        "por_semana": [{"semana": s, **_fechar(por_semana[s])} for s in sorted(por_semana)],
        "por_mes": [{"mes": m, **_fechar(por_mes[m])} for m in sorted(por_mes)],
        "por_ano": [{"ano": a, **_fechar(por_ano[a])} for a in sorted(por_ano)],
        # Todos os canais medidos, pela ordem da configuracao, mesmo a zero:
        # um canal sem entrevistas e um dado, nao uma ausencia.
        "por_canal": [
            {"canal": c.id, "nome": c.nome, **_fechar(por_canal.get(c.id, _balde()))}
            for c in config.canais.values()
        ],
        "canal_por_dia": [
            {
                "data": d,
                "canais": {
                    canal: {**_fechar(celula), "declaradas": celula["declaradas"]}
                    for canal, celula in canal_por_dia[d].items()
                },
            }
            for d in datas
        ],
        # Quanto do que esta publicado vem do proprio canal e quanto vem
        # de clipping de imprensa. O site mostra-o; e uma medida da
        # qualidade da propria cobertura.
        "por_origem": {origem: _fechar(balde) for origem, balde in sorted(por_origem.items())},
        "recordes": recordes(datas),
        # Todas as fontes que provaram alguma transmissao, e nao so as das
        # entrevistas: uma fonte que so aparece na segunda transmissao de
        # um simulcast provou alguma coisa e nao desaparece da lista.
        "fontes": sorted(
            {
                t["fonte"]
                for e in visiveis
                for t in (e.get("transmissoes") or [{"fonte": e["fonte"]}])
            }
        ),
    }


def guardar(resumo: dict, caminho: Path = RESUMO) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(resumo, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
