"""Agregados prontos para o site.

O site nao calcula nada que nao esteja aqui, exceto somas de periodo a
partir das repartições diarias. Tudo o que e uma conta nova vive neste
ficheiro, com teste, e nunca no JavaScript.

Unidades, para nao haver confusao:

- emissoes: entrevistas emitidas, uma por canal e dia. A mesma entrevista
  em dois canais sao duas emissoes.
- entrevistas_distintas: emissoes agrupadas pela chave `entrevista`.
- tempo_s: soma das duracoes das emissoes que tem duracao apurada. Com um
  so interveniente, tempo de emissao e tempo de pessoa sao a mesma coisa.
- sem_duracao: emissoes provadas cuja duracao nao foi possivel apurar.
  Contam como evento e nao contam no tempo. Este campo existe para que
  ninguem leia `tempo_s` como se fosse o tempo de todas as emissoes: sem
  ele, um total baixo pareceria uma medicao em vez de uma lacuna.
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


def _balde() -> dict:
    return {"emissoes": 0, "tempo_s": 0, "sem_duracao": 0, "entrevistas": set()}


def _fechar(balde: dict) -> dict:
    return {
        "emissoes": balde["emissoes"],
        "entrevistas_distintas": len(balde["entrevistas"]),
        "tempo_s": balde["tempo_s"],
        "sem_duracao": balde["sem_duracao"],
    }


def _somar(balde: dict, linha: dict) -> None:
    balde["emissoes"] += 1
    duracao = linha.get("duracao_s")
    if duracao is None:
        balde["sem_duracao"] += 1
    else:
        balde["tempo_s"] += int(duracao)
    balde["entrevistas"].add(linha["entrevista"])


def recordes(datas: list[str]) -> dict:
    """Ultima data, maior intervalo sem emissoes e maior sequencia de dias
    seguidos com emissao. Datas distintas, ordenadas."""
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


def construir(linhas: list[dict], config: Config) -> dict:
    total = _balde()
    por_dia: dict = defaultdict(_balde)
    por_semana: dict = defaultdict(_balde)
    por_mes: dict = defaultdict(_balde)
    por_ano: dict = defaultdict(_balde)
    por_canal: dict = defaultdict(_balde)
    canal_por_dia: dict = defaultdict(lambda: defaultdict(lambda: {**_balde(), "declaradas": 0, "parciais": 0}))
    por_origem: dict = defaultdict(_balde)

    for linha in linhas:
        data = linha["data"]
        _somar(total, linha)
        _somar(por_dia[data], linha)
        _somar(por_semana[semana_iso(data)], linha)
        _somar(por_mes[data[:7]], linha)
        _somar(por_ano[data[:4]], linha)
        _somar(por_canal[linha["canal"]], linha)
        _somar(por_origem[linha.get("origem") or "canal"], linha)
        celula = canal_por_dia[data][linha["canal"]]
        _somar(celula, linha)
        if linha.get("data_origem") == "declarada":
            celula["declaradas"] += 1
        if linha.get("parcial"):
            celula["parciais"] += 1

    datas = sorted(por_dia)
    tema = config.tema
    return {
        "esquema": 1,
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tema": {
            "id": tema.id,
            "nome": tema.nome,
            "pergunta": tema.pergunta,
            "desde": tema.desde,
            "desde_rotulo": tema.desde_rotulo,
        },
        "sujeito": {"id": config.sujeito.id, "nome": config.sujeito.nome},
        "primeiro_registo": datas[0] if datas else None,
        "ultimo_registo": datas[-1] if datas else None,
        "totais": _fechar(total),
        # `chaves` sao as chaves de entrevista do dia, para o site poder
        # contar entrevistas distintas em qualquer periodo sem duplicar
        # simulcasts nem repeticoes. E a unica lista por dia; e curta.
        "por_dia": [
            {"data": d, **_fechar(por_dia[d]), "chaves": sorted(por_dia[d]["entrevistas"])}
            for d in datas
        ],
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
                    canal: {
                        **_fechar(celula),
                        "declaradas": celula["declaradas"],
                        "parciais": celula["parciais"],
                    }
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
        "fontes": sorted({linha["fonte"] for linha in linhas}),
    }


def guardar(resumo: dict, caminho: Path = RESUMO) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(resumo, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
