"""Colheita do indice do Google Noticias por RSS. Corre em casa, nunca na CI.

    python -m ferramentas.gnews --saida D:\\porquinho-local
    python -m ferramentas.gnews --saida D:\\porquinho-local --triar
    python -m ferramentas.gnews --saida D:\\porquinho-local --resolver
    python -m ferramentas.gnews --saida D:\\porquinho-local --desde 2024-01-01

Le config/gnews.yml, pede o RSS de cada consulta em janelas mensais desde
o inicio do tema, e escreve na pasta de saida:

    bruto/<janela>__<n>.xml   cada resposta tal como veio, para auditoria
    estado.json               o que ja foi pedido, para retomar sem repetir
    candidatos.csv            um item por linha, deduplicado, por data
    triagem.csv               so o que uma pessoa tem de decidir (--triar)
    triagem.html              a mesma lista, com as ligacoes clicaveis

Isto e um detetor e nao uma fonte: aponta o dia e o canal de uma
entrevista provavel. A prova de cada linha e o URL do canal, e la vai
uma pessoa, a partir do que a coluna `url_final` aponta. Nada do que sai
daqui entra no repositorio; a pasta de saida tem de ficar fora dele, e o
programa recusa-se a escrever la dentro.

O RSS devolve no maximo cerca de cem itens por consulta. Uma janela que
devolva `limiar_divisao` itens ou mais e dividida ao meio ate caber,
senao o mes ficaria truncado em silencio, que e o erro mais dificil de
ver depois.

As ligacoes do RSS sao redirecionamentos do Google. `--resolver` segue
cada uma e guarda o destino em `url_final`. E um passo separado porque e
lento e pode falhar sem que a colheita se perca.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import yaml

from recolha.modelos import RAIZ, carregar_config, contem_palavra
from recolha.rede import CABECALHOS, ErroDeRede, TEMPO_LIMITE, obter_texto

FICHEIRO = RAIZ / "config" / "gnews.yml"
COLUNAS = [
    "data",
    "titulo",
    "fonte",
    "dominio_fonte",
    "canal_por_fonte",
    "canal_no_titulo",
    "formato_no_titulo",
    "url_google",
    "url_final",
    "consultas",
    "janelas",
]


def carregar(caminho: Path = FICHEIRO) -> dict:
    return yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}


# --- janelas ---------------------------------------------------------------


def janelas_mensais(desde: date, ate: date) -> list[tuple[date, date]]:
    """Meses de calendario entre `desde` e `ate`, inclusive. A primeira
    janela comeca em `desde` e nao no dia 1: nada anterior ao inicio do
    tema interessa, e pedir menos e sempre melhor."""
    janelas = []
    inicio = desde
    while inicio <= ate:
        proximo_mes = (inicio.replace(day=1) + timedelta(days=32)).replace(day=1)
        fim = min(proximo_mes - timedelta(days=1), ate)
        janelas.append((inicio, fim))
        inicio = fim + timedelta(days=1)
    return janelas


def dividir(janela: tuple[date, date]) -> list[tuple[date, date]]:
    inicio, fim = janela
    if inicio == fim:
        return [janela]
    meio = inicio + (fim - inicio) // 2
    return [(inicio, meio), (meio + timedelta(days=1), fim)]


def rotulo(janela: tuple[date, date]) -> str:
    return f"{janela[0].isoformat()}_{janela[1].isoformat()}"


def url_da_consulta(config: dict, consulta: str, janela: tuple[date, date]) -> str:
    # Um dia de folga de cada lado: nao esta documentado se after e before
    # incluem o dia, e a deduplicacao absorve a sobreposicao.
    depois = (janela[0] - timedelta(days=1)).isoformat()
    antes = (janela[1] + timedelta(days=1)).isoformat()
    q = f"{consulta} after:{depois} before:{antes}"
    parametros = {"q": q, **config.get("parametros", {})}
    return config["base"] + "?" + urllib.parse.urlencode(parametros, quote_via=urllib.parse.quote)


# --- leitura do RSS --------------------------------------------------------


def ler_rss(xml: str) -> list[dict]:
    """Um dicionario por item. O titulo do RSS traz o nome da fonte no fim,
    separado por ' - '; tira-se so quando coincide com a fonte declarada,
    para nao cortar um titulo que tenha um travessao proprio."""
    raiz = ET.fromstring(xml)
    itens = []
    for item in raiz.iter("item"):
        titulo = (item.findtext("title") or "").strip()
        fonte_el = item.find("source")
        fonte = (fonte_el.text or "").strip() if fonte_el is not None else ""
        fonte_url = fonte_el.get("url", "") if fonte_el is not None else ""
        sufixo = f" - {fonte}"
        if fonte and titulo.endswith(sufixo):
            titulo = titulo[: -len(sufixo)].strip()
        itens.append(
            {
                "guid": (item.findtext("guid") or "").strip(),
                "titulo": html.unescape(titulo),
                "fonte": fonte,
                "dominio_fonte": urllib.parse.urlsplit(fonte_url).hostname or "",
                "data": _data_iso(item.findtext("pubDate") or ""),
                "url_google": (item.findtext("link") or "").strip(),
            }
        )
    return itens


def _data_iso(valor: str) -> str:
    try:
        return parsedate_to_datetime(valor).astimezone(timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        return ""


# --- classificacao indicativa ---------------------------------------------


def canal_por_texto(config: dict, texto: str) -> str:
    """O canal cujo nome aparece no texto, ou vazio. Os nomes mais longos
    testam-se primeiro: o nome de um canal de noticias contem o nome do
    canal generalista do mesmo grupo, e a leitura curta daria o errado."""
    pares = []
    for canal, nomes in (config.get("canais_por_texto") or {}).items():
        for nome in nomes:
            pares.append((len(nome), nome, canal))
    for _, nome, canal in sorted(pares, reverse=True):
        if contem_palavra(texto, (nome,)):
            return canal
    return ""


def canal_por_dominio(config: dict, dominio: str) -> str:
    dominio = (dominio or "").lower().removeprefix("www.")
    for canal, dominios in (config.get("canais_por_dominio") or {}).items():
        if dominio in [d.lower() for d in dominios]:
            return canal
    return ""


def formato_no_titulo(config: dict, titulo: str) -> str:
    encontrados = []
    for formato, termos in (config.get("marcadores_formato") or {}).items():
        if contem_palavra(titulo, tuple(termos)):
            encontrados.append(formato)
    return "+".join(encontrados)


def classificar(config: dict, item: dict) -> dict:
    return {
        **item,
        "canal_por_fonte": canal_por_texto(config, item["fonte"]) or canal_por_dominio(config, item["dominio_fonte"]),
        "canal_no_titulo": canal_por_texto(config, item["titulo"]),
        "formato_no_titulo": formato_no_titulo(config, item["titulo"]),
    }


# --- estado e csv ----------------------------------------------------------


def pasta_de_saida(caminho: str) -> Path:
    pasta = Path(caminho).expanduser().resolve()
    try:
        pasta.relative_to(RAIZ)
    except ValueError:
        return pasta
    raise SystemExit(f"a pasta de saida nao pode ficar dentro do repositorio: {pasta}")


def ler_estado(pasta: Path) -> dict:
    caminho = pasta / "estado.json"
    if caminho.exists():
        return json.loads(caminho.read_text(encoding="utf-8"))
    return {"pedidos": {}}


def gravar_estado(pasta: Path, estado: dict) -> None:
    (pasta / "estado.json").write_text(json.dumps(estado, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8", newline="\n")


def ler_csv(pasta: Path) -> dict[str, dict]:
    caminho = pasta / "candidatos.csv"
    if not caminho.exists():
        return {}
    with caminho.open(encoding="utf-8-sig", newline="") as f:
        return {linha["url_google"]: linha for linha in csv.DictReader(f)}


def gravar_csv(pasta: Path, linhas: dict[str, dict]) -> None:
    # utf-8 com BOM: e o unico UTF-8 que o Excel em Windows abre com os
    # acentos certos sem passar pelo assistente de importacao.
    caminho = pasta / "candidatos.csv"
    ordenadas = sorted(linhas.values(), key=lambda l: (l.get("data") or "9999", l.get("fonte") or "", l.get("titulo") or ""))
    with caminho.open("w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUNAS, lineterminator="\n", extrasaction="ignore")
        escritor.writeheader()
        for linha in ordenadas:
            escritor.writerow({c: linha.get(c, "") for c in COLUNAS})


def juntar(linhas: dict[str, dict], item: dict, consulta: str, janela: str) -> None:
    """Deduplica pelo URL do Google, que e estavel por artigo. Guarda que
    consultas e janelas o trouxeram: um item visto por tres consultas
    apertadas merece mais atencao na triagem do que um visto so pela
    solta."""
    chave = item["url_google"]
    existente = linhas.get(chave)
    if existente is None:
        linhas[chave] = {**item, "url_final": "", "consultas": consulta, "janelas": janela}
        return
    for campo, valor in (("consultas", consulta), ("janelas", janela)):
        vistos = [v for v in existente.get(campo, "").split(" | ") if v]
        if valor not in vistos:
            existente[campo] = " | ".join(vistos + [valor])


# --- colheita ----------------------------------------------------------------


def colher(config: dict, pasta: Path, desde: date, ate: date, obter=obter_texto, dormir=time.sleep) -> dict:
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "bruto").mkdir(exist_ok=True)
    estado = ler_estado(pasta)
    linhas = ler_csv(pasta)
    consultas = config.get("consultas") or []
    limiar = int(config.get("limiar_divisao", 90))
    pausa = float(config.get("pausa_s", 6))
    resumo = {"pedidos": 0, "itens": 0, "divisoes": 0, "falhas": 0}

    pendentes = [(consulta, janela) for janela in janelas_mensais(desde, ate) for consulta in consultas]
    while pendentes:
        consulta, janela = pendentes.pop(0)
        chave = f"{consulta} @ {rotulo(janela)}"
        if chave in estado["pedidos"]:
            continue
        url = url_da_consulta(config, consulta, janela)
        try:
            xml = obter(url)
        except ErroDeRede as exc:
            print(f"  falhou {chave}: {exc}", flush=True)
            resumo["falhas"] += 1
            dormir(pausa)
            continue
        resumo["pedidos"] += 1
        n = len(estado["pedidos"]) + 1
        (pasta / "bruto" / f"{rotulo(janela)}__{n}.xml").write_text(xml, encoding="utf-8", newline="\n")
        try:
            itens = ler_rss(xml)
        except ET.ParseError as exc:
            print(f"  xml invalido em {chave}: {exc}", flush=True)
            estado["pedidos"][chave] = {"itens": None, "erro": str(exc)}
            gravar_estado(pasta, estado)
            dormir(pausa)
            continue
        if len(itens) >= limiar and janela[0] != janela[1]:
            metades = dividir(janela)
            print(f"  cheia ({len(itens)}) {chave}: dividida em {rotulo(metades[0])} e {rotulo(metades[1])}", flush=True)
            resumo["divisoes"] += 1
            pendentes = [(consulta, m) for m in metades] + pendentes
            estado["pedidos"][chave] = {"itens": len(itens), "dividida": True}
        else:
            for item in itens:
                juntar(linhas, classificar(config, item), consulta, rotulo(janela))
            resumo["itens"] += len(itens)
            estado["pedidos"][chave] = {"itens": len(itens)}
            print(f"  {len(itens):3d} itens  {chave}", flush=True)
        gravar_estado(pasta, estado)
        gravar_csv(pasta, linhas)
        dormir(pausa)
    resumo["linhas"] = len(linhas)
    return resumo


# --- resolucao dos redirecionamentos ---------------------------------------


def destino_na_pagina(html_texto: str) -> str:
    """O Google serve, em vez de um 302, uma pagina cujo unico conteudo
    util e o destino num atributo. E uma leitura de uma pagina do Google
    e nao de um canal, e pode partir; quando partir a coluna fica vazia e
    a ligacao do Google continua a abrir no browser."""
    m = re.search(r'data-n-au="([^"]+)"', html_texto)
    if m:
        return html.unescape(m.group(1))
    return ""


def seguir(url: str) -> tuple[str, str]:
    """(url final, corpo). Segue redirecionamentos HTTP normais."""
    pedido = urllib.request.Request(url, headers=CABECALHOS)
    with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:
        charset = resposta.headers.get_content_charset() or "utf-8"
        return resposta.geturl(), resposta.read(4 * 1024 * 1024).decode(charset, errors="replace")


def resolver_url(url: str, seguir_fn=seguir) -> str:
    try:
        final, corpo = seguir_fn(url)
    except Exception as exc:  # noqa: BLE001  (qualquer falha deixa a coluna vazia)
        print(f"  falhou {url[:60]}...: {exc}", flush=True)
        return ""
    if "news.google." not in (urllib.parse.urlsplit(final).hostname or ""):
        return final
    return destino_na_pagina(corpo)


def resolver(config: dict, pasta: Path, so_triados: bool = True, seguir_fn=seguir, dormir=time.sleep) -> dict:
    """Segue as ligacoes do Google ate ao destino.

    Por omissao so as linhas que a triagem reteve. Resolver as milhares
    de linhas da colheita inteira demora horas e nao serve para nada: o
    que interessa e o destino dos candidatos, e esses sao poucos.

    Imprime uma linha por ligacao. A primeira corrida ficou uma hora sem
    escrever nada no ecra e parecia parada quando estava a trabalhar.
    """
    linhas = ler_csv(pasta)
    triados = urls_triados(pasta) if so_triados else None
    pausa = float(config.get("pausa_resolucao_s", 2))
    alvo = [l for l in linhas.values() if not l.get("url_final") and (triados is None or l["url_google"] in triados)]
    resumo = {"alvo": len(alvo), "resolvidas": 0, "por_resolver": 0}
    print(f"  {len(alvo)} ligacoes por resolver", flush=True)
    for i, linha in enumerate(alvo, 1):
        final = resolver_url(linha["url_google"], seguir_fn)
        if final:
            linha["url_final"] = final
            resumo["resolvidas"] += 1
            canal = canal_por_dominio(config, urllib.parse.urlsplit(final).hostname or "")
            if canal and not linha.get("canal_por_fonte"):
                linha["canal_por_fonte"] = canal
        else:
            resumo["por_resolver"] += 1
        print(f"  {i}/{len(alvo)}  {(final or 'por resolver')[:90]}", flush=True)
        if i % 10 == 0:
            gravar_csv(pasta, linhas)
        dormir(pausa)
    gravar_csv(pasta, linhas)
    return resumo


# --- triagem ---------------------------------------------------------------

COLUNAS_TRIAGEM = ["decisao", "prova_url", "duracao", "programa", "canal", "nota", "grupo", "data", "titulo", "fonte", "formato_no_titulo", "url_google"]


def agrupar(config: dict, linhas: list[dict], sujeito) -> list[dict]:
    """Reduz a colheita ao que uma pessoa tem de olhar, em dois grupos.

    `sujeito`  o titulo nomeia o sujeito e indica entrevista. E o grupo
               denso: quase tudo aqui e uma emissao ou uma peca sobre uma.
    `programa` o titulo indica entrevista e a fonte e um canal, mas o
               sujeito nao aparece. Existe porque um canal titula os seus
               episodios com o nome do programa e a data, e o convidado
               fica so na sinopse, que o indice nao traz. Sem este grupo
               perdiam-se todas as emissoes desse canal.

    O que fica de fora e o ruido: pecas que citam o sujeito sem que nada
    no titulo sugira entrevista. Fica no `candidatos.csv`, que nao se
    apaga, para se poder voltar atras sem repetir a colheita.
    """
    retidas = []
    for linha in linhas:
        formato = linha.get("formato_no_titulo", "")
        if "entrevista" not in formato:
            continue
        tem_sujeito = sujeito.aparece_em(linha.get("titulo", ""))
        tem_canal = bool(linha.get("canal_por_fonte") or linha.get("canal_no_titulo"))
        if tem_sujeito and tem_canal:
            grupo = "sujeito"
        elif not tem_sujeito and linha.get("canal_por_fonte"):
            grupo = "programa"
        else:
            continue
        retidas.append({**linha, "grupo": grupo})
    return sorted(retidas, key=lambda l: (l.get("data") or "9999", l.get("grupo") or "", l.get("fonte") or ""))


def gravar_triagem(pasta: Path, retidas: list[dict]) -> None:
    """Um CSV para decidir e um HTML para ver.

    O CSV abre no Excel e tem as colunas de decisao a esquerda, para se
    escrever sem andar a rolar. O HTML existe porque as ligacoes do
    indice sao redirecionamentos que so abrem num browser: e a forma de
    ir ver a peca e copiar o URL do canal, que e a prova.
    """
    caminho = pasta / "triagem.csv"
    with caminho.open("w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUNAS_TRIAGEM, lineterminator="\n", extrasaction="ignore")
        escritor.writeheader()
        for linha in retidas:
            escritor.writerow({c: linha.get(c, "") for c in COLUNAS_TRIAGEM})

    partes = [
        "<!doctype html><meta charset='utf-8'><title>Triagem</title>",
        "<style>body{font:15px/1.5 system-ui;margin:2rem;max-width:70rem}"
        "tr:nth-child(even){background:#f4f4f4}td{padding:.3rem .5rem;vertical-align:top}"
        ".g{color:#777;font-size:.85em}</style>",
        f"<h1>Triagem: {len(retidas)} candidatos</h1><table>",
    ]
    for i, linha in enumerate(retidas, 1):
        titulo = html.escape(linha.get("titulo", ""))
        canal = linha.get("canal_no_titulo") or linha.get("canal_por_fonte") or ""
        partes.append(
            f"<tr><td>{i}</td><td>{html.escape(linha.get('data', ''))}</td>"
            f"<td><a href=\"{html.escape(linha.get('url_google', ''))}\" target=_blank>{titulo}</a>"
            f"<div class=g>{html.escape(linha.get('fonte', ''))} | {html.escape(canal)} | {html.escape(linha.get('grupo', ''))}</div></td></tr>"
        )
    partes.append("</table>")
    (pasta / "triagem.html").write_text("\n".join(partes), encoding="utf-8", newline="\n")


def urls_triados(pasta: Path) -> set[str]:
    caminho = pasta / "triagem.csv"
    if not caminho.exists():
        return set()
    with caminho.open(encoding="utf-8-sig", newline="") as f:
        return {linha["url_google"] for linha in csv.DictReader(f) if linha.get("url_google")}


def triar(config: dict, pasta: Path) -> dict:
    linhas = list(ler_csv(pasta).values())
    retidas = agrupar(config, linhas, carregar_config().sujeito)
    gravar_triagem(pasta, retidas)
    contagem = {}
    for linha in retidas:
        contagem[linha["grupo"]] = contagem.get(linha["grupo"], 0) + 1
    return {"colhidas": len(linhas), "retidas": len(retidas), **contagem}


# --- entrada -----------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Colheita local do Google Noticias por RSS")
    parser.add_argument("--saida", required=True, help="pasta fora do repositorio")
    parser.add_argument("--desde", help="AAAA-MM-DD; por omissao o inicio do tema")
    parser.add_argument("--ate", help="AAAA-MM-DD; por omissao hoje")
    parser.add_argument("--triar", action="store_true", help="reduzir a colheita a uma lista para decidir")
    parser.add_argument("--resolver", action="store_true", help="seguir as ligacoes dos candidatos triados ate ao destino")
    parser.add_argument("--tudo", action="store_true", help="com --resolver: resolver a colheita inteira, nao so os triados")
    args = parser.parse_args(argv)

    config = carregar()
    pasta = pasta_de_saida(args.saida)
    if args.triar:
        print(f"a triar {pasta}", flush=True)
        resumo = triar(config, pasta)
    elif args.resolver:
        print(f"a resolver ligacoes em {pasta}", flush=True)
        resumo = resolver(config, pasta, so_triados=not args.tudo)
    else:
        desde = date.fromisoformat(args.desde) if args.desde else date.fromisoformat(carregar_config().tema.desde)
        ate = date.fromisoformat(args.ate) if args.ate else datetime.now(timezone.utc).date()
        print(f"a colher de {desde} a {ate} para {pasta}", flush=True)
        resumo = colher(config, pasta, desde, ate)
    print(json.dumps(resumo, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
