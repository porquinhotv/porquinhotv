"""Colheita do indice do Google Noticias por RSS. Corre em casa, nunca na CI.

    python -m ferramentas.gnews --saida D:\\porquinho-local
    python -m ferramentas.gnews --saida D:\\porquinho-local --triar
    python -m ferramentas.gnews --saida D:\\porquinho-local --verificar
    python -m ferramentas.gnews --saida D:\\porquinho-local --emitir
    python -m ferramentas.gnews --saida D:\\porquinho-local --emitir --imprensa
    python -m ferramentas.gnews --saida D:\\porquinho-local --resolver
    python -m ferramentas.gnews --saida D:\\porquinho-local --desde 2024-01-01

Le config/gnews.yml, pede o RSS de cada consulta em janelas mensais desde
o inicio do tema, e escreve na pasta de saida:

    bruto/<janela>__<n>.xml   cada resposta tal como veio, para auditoria
    estado.json               o que ja foi pedido, para retomar sem repetir
    candidatos.csv            um item por linha, deduplicado, por data
    triagem.csv               so o que uma pessoa tem de decidir (--triar),
                              com o que a pagina do canal diz (--verificar)
    triagem.html              a mesma lista, com as ligacoes clicaveis

Isto e um detetor e nao uma fonte: aponta o dia e o canal de uma
entrevista provavel. A prova de cada linha e uma pagina que uma pessoa
abriu, a partir do que a coluna `url_final` aponta: a do canal, que vai
para config/entrevistas.yml com `--emitir`, ou uma peca de imprensa que
relate a emissao, que vai para config/clipping.yml com `--emitir
--imprensa`. Nada do que sai da colheita entra no repositorio; a pasta
de saida tem de ficar fora dele, e o programa recusa-se a escrever la
dentro.

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
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import yaml

from recolha import extracao
from recolha.modelos import FICHEIRO_ENTREVISTAS, RAIZ, carregar_config, contem_palavra, normalizar
from recolha.rede import CABECALHOS, ErroDeRede, TEMPO_LIMITE, obter_texto

FICHEIRO = RAIZ / "config" / "gnews.yml"
FICHEIRO_CLIPPING = RAIZ / "config" / "clipping.yml"
FICHEIRO_PAGINAS_DE_CANAL = RAIZ / "config" / "paginas_de_canal.yml"
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


def seguir(url: str) -> tuple[str, str]:
    """(url final, corpo). Segue redirecionamentos HTTP normais."""
    pedido = urllib.request.Request(url, headers=CABECALHOS)
    with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:
        charset = resposta.headers.get_content_charset() or "utf-8"
        return resposta.geturl(), resposta.read(4 * 1024 * 1024).decode(charset, errors="replace")


ENDERECO_DECODE = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
PEDIDO_DECODE = (
    '[[["Fbv4je","[\\"garturlreq\\",[[\\"X\\",\\"X\\",[\\"X\\",\\"X\\"],null,null,1,1,'
    '\\"US:en\\",null,1,null,null,null,null,null,0,1],\\"X\\",\\"X\\",1,[1,1,1],1,1,null,0,0,null,0],'
    '\\"{id}\\",{ts},\\"{sg}\\"]",null,"generic"]]]'
)


def destino_na_pagina(html_texto: str) -> str:
    """Destino declarado num atributo, no formato antigo do indice.

    Deixou de aparecer: as ligacoes colhidas em 2026 trazem um
    identificador opaco e a pagina nao declara destino nenhum. Fica
    porque nao custa nada e resolve as ligacoes antigas que ainda
    existam guardadas.
    """
    m = re.search(r'data-n-au="([^"]+)"', html_texto)
    return html.unescape(m.group(1)) if m else ""


def parametros_de_decode(html_texto: str) -> tuple[str, str]:
    """Assinatura e carimbo temporal que a pagina do indice publica para
    o seu proprio codigo pedir o destino.

    Nao e um seletor de um site do qual se leem dados: nenhum numero do
    Porquinho TV sai daqui. E a chave para chegar a pagina do canal, que
    e onde a prova esta. Se um dia isto deixar de existir, o efeito e a
    coluna ficar vazia e o trabalho passar a ser feito a mao no browser,
    nunca um numero errado publicado.
    """
    sg = re.search(r'data-n-a-sg="([^"]+)"', html_texto)
    ts = re.search(r'data-n-a-ts="([^"]+)"', html_texto)
    if sg and ts:
        return html.unescape(sg.group(1)), ts.group(1)
    return "", ""


def identificador(url: str) -> str:
    caminho = urllib.parse.urlsplit(url).path
    return caminho.rsplit("/", 1)[-1]


def destino_na_resposta(corpo: str) -> str:
    """O endereco final dentro da resposta do indice.

    A resposta vem com um prefixo de defesa e varias camadas de JSON
    dentro de texto. Le-se camada a camada, e nao com uma expressao
    regular a apanhar o primeiro http que aparecer: essa apanharia
    tambem enderecos de recursos que nada tem que ver com o artigo.
    """
    for linha in corpo.splitlines():
        if "garturlres" not in linha:
            continue
        try:
            fora = json.loads(linha)
        except json.JSONDecodeError:
            continue
        for parte in fora:
            if isinstance(parte, list) and len(parte) > 2 and isinstance(parte[2], str) and "garturlres" in parte[2]:
                dentro = json.loads(parte[2])
                if len(dentro) > 1 and isinstance(dentro[1], str) and dentro[1].startswith("http"):
                    return dentro[1]
    return ""


def publicar(url: str, dados: bytes) -> str:
    pedido = urllib.request.Request(
        url,
        data=dados,
        headers={**CABECALHOS, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
    )
    with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:
        charset = resposta.headers.get_content_charset() or "utf-8"
        return resposta.read(8 * 1024 * 1024).decode(charset, errors="replace")


def resolver_url(url: str, seguir_fn=seguir, publicar_fn=publicar) -> str:
    """Endereco do artigo por tras de uma ligacao do indice, ou vazio.

    Tres caminhos, do mais simples para o mais fragil: um
    redirecionamento normal; o destino declarado na pagina; e, so
    quando nenhum dos dois existe, pedir o destino ao indice com a
    assinatura que a propria pagina publica.

    O terceiro caminho depende do funcionamento interno de um sitio de
    terceiros e ha de partir sem aviso. Escreveu-se assim, e nao de
    outra maneira, porque a alternativa e abrir cento e cinquenta
    ligacoes a mao. Quando partir, a coluna fica vazia e o trabalho
    volta a ser manual: nunca produz um endereco errado.
    """
    try:
        final, corpo = seguir_fn(url)
    except Exception as exc:  # noqa: BLE001  (qualquer falha deixa a coluna vazia)
        print(f"  falhou {url[:60]}...: {exc}", flush=True)
        return ""
    if "news.google." not in (urllib.parse.urlsplit(final).hostname or ""):
        return final
    declarado = destino_na_pagina(corpo)
    if declarado:
        return declarado
    sg, ts = parametros_de_decode(corpo)
    if not sg:
        return ""
    pedido = PEDIDO_DECODE.format(id=identificador(url).split("?")[0], ts=ts, sg=sg)
    dados = urllib.parse.urlencode({"f.req": pedido}).encode()
    try:
        return destino_na_resposta(publicar_fn(ENDERECO_DECODE, dados))
    except Exception as exc:  # noqa: BLE001
        print(f"  decode falhou: {exc}", flush=True)
        return ""


def resolver(config: dict, pasta: Path, so_triados: bool = True, limite: int | None = None, seguir_fn=seguir, dormir=time.sleep) -> dict:
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
    if limite:
        alvo = alvo[:limite]
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

COLUNAS_TRIAGEM = [
    "decisao", "prova_url", "duracao", "programa", "canal", "data_emissao", "nota", "sugestao",
    "sujeito_na_pagina", "duracao_na_pagina", "programa_na_pagina", "data_na_pagina", "titulo_na_pagina", "descricao_na_pagina",
    "grupo", "data", "titulo", "fonte", "formato_no_titulo", "url_google",
]


def agrupar(config: dict, linhas: list[dict], sujeito) -> list[dict]:
    """Reduz a colheita ao que uma pessoa tem de olhar, em dois grupos.

    `sujeito`  o titulo nomeia o sujeito e indica entrevista. E o grupo
               denso: quase tudo aqui e uma emissao ou uma peca sobre uma.
    `programa` o titulo indica entrevista e a fonte e um canal, mas o
               sujeito nao aparece. Existe porque um canal titula os seus
               episodios com o nome do programa e a data, e o convidado
               fica so na sinopse, que o indice nao traz. Sem este grupo
               perdiam-se todas as emissoes desse canal.
    `imprensa` o titulo nomeia o sujeito, a fonte nao e um canal, e a
               linha veio de uma consulta com a palavra "entrevista". E o
               grupo das pecas de jornal, que titulam com a citacao e
               deixam "em entrevista a X" para o lead, que o indice nao
               traz. A consulta e o unico sinal barato: o indice casou-a
               com o corpo da peca, logo a palavra esta la. Ate
               2026-09-09 estas linhas ficavam de fora e a via da
               imprensa nunca recebia nada: o clipping estava vazio por
               isso, nao por falta de pecas. So o `--verificar`, que le
               o lead, diz se a peca prova alguma coisa.

    O que fica de fora e o ruido: pecas que citam o sujeito sem que nada
    no titulo nem na consulta sugira entrevista. Fica no `candidatos.csv`,
    que nao se apaga, para se poder voltar atras sem repetir a colheita.
    """
    retidas = []
    for linha in linhas:
        formato = linha.get("formato_no_titulo", "")
        tem_formato = "entrevista" in formato
        tem_sujeito = sujeito.aparece_em(linha.get("titulo", ""))
        tem_canal = bool(linha.get("canal_por_fonte") or linha.get("canal_no_titulo"))
        pela_consulta = "entrevista" in normalizar(linha.get("consultas") or "")
        if tem_formato and tem_sujeito and tem_canal:
            grupo = "sujeito"
        elif tem_formato and not tem_sujeito and linha.get("canal_por_fonte"):
            grupo = "programa"
        elif tem_sujeito and not linha.get("canal_por_fonte") and (tem_formato or pela_consulta):
            grupo = "imprensa"
        else:
            continue
        retidas.append({**linha, "grupo": grupo})
    return sorted(retidas, key=lambda l: (l.get("data") or "9999", l.get("grupo") or "", l.get("fonte") or ""))


def fundir_triagem(retidas: list[dict], anteriores: list[dict]) -> list[dict]:
    """Uma nova triagem nunca apaga o que uma pessoa ja escreveu.

    O `--triar` reconstroi a lista a partir da colheita, e ate 2026-09-09
    gravava-a por cima da anterior: as decisoes, as provas e as colunas
    lidas nas paginas desapareciam. Nao doeu porque so tinha corrido uma
    vez. Com o grupo `imprensa` a acrescentar centenas de linhas a uma
    triagem com 150 decisoes tomadas, doia. A chave e o URL do indice,
    que e estavel por artigo; o que a pessoa ou o `--verificar` escreveram
    ganha ao que a colheita traz de novo.
    """
    por_url = {l.get("url_google"): l for l in anteriores if l.get("url_google")}
    fundidas = []
    for linha in retidas:
        anterior = por_url.get(linha.get("url_google"))
        if anterior is None:
            fundidas.append(linha)
            continue
        preenchido = {c: v for c, v in anterior.items() if v}
        fundidas.append({**linha, **preenchido, "grupo": linha["grupo"]})
    # Uma linha que a regra de agrupamento deixou de reter continua na
    # triagem: a decisao que uma pessoa tomou sobre ela nao caduca porque
    # a regra mudou.
    novas = {l.get("url_google") for l in retidas}
    fundidas.extend(l for l in anteriores if l.get("url_google") and l["url_google"] not in novas)
    return fundidas


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


LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL)


def enderecos_do_mapa(xml: str) -> list[str]:
    """Os `<loc>` de um mapa de sitio, seja indice ou lista de paginas.

    Um mapa nao e HTML e nao tem `href`: a funcao que colhe ligacoes de
    uma pagina devolve zero aqui, o que na primeira sondagem se leu como
    falha e nao era.
    """
    return [html.unescape(u) for u in LOC.findall(xml) if u.strip()]


def mapas_a_usar(indice_xml: str, prefixos: list[str]) -> list[str]:
    """Do indice, so os mapas que interessam, pelo nome do ficheiro."""
    escolhidos = []
    for url in enderecos_do_mapa(indice_xml):
        nome = url.rsplit("/", 1)[-1]
        if any(nome.startswith(p) for p in prefixos) and url not in escolhidos:
            escolhidos.append(url)
    return escolhidos


def linha_do_mapa(url: str, fonte: str) -> dict:
    """Uma linha de triagem feita so de um endereco.

    O mapa nao da titulo, data nem lead, por isso estas colunas ficam
    vazias e e o `--verificar` que as preenche, com o mesmo extrator de
    qualquer outra peca. A chave e o proprio endereco: nao ha URL de
    indice porque nao se passou por indice nenhum, e o `prova_url` ja fica
    resolvido, o que dispensa o `--resolver`.
    """
    return {
        "url_google": url,
        "prova_url": url,
        "fonte": fonte,
        "grupo": "imprensa",
        "data": "",
        "titulo": "",
        "formato_no_titulo": "",
        "nota": "vinda do mapa do sitio",
    }


def colher_mapas(config: dict, pasta: Path, sujeito=None, limite: int | None = None,
                 obter=obter_texto, dormir=time.sleep) -> dict:
    """Acrescenta a triagem as pecas cujo endereco nomeia o sujeito.

    Existe porque o indice de noticias nao traz tudo o que existe, coisa
    verificada a 2026-09-08, e o arquivo deste jornal recua ate 2019, que e
    onde faltam linhas. O que o mapa da e barato: um pedido por mil
    enderecos, em vez de uma pagina de listagem por cada 24 pecas.

    Nao apaga nem reescreve nada: uma linha que ja esteja na triagem fica
    como esta, com a decisao e as colunas que uma pessoa ou o
    `--verificar` escreveram.

    O `limite` existe para medir antes de gastar: as pecas do mapa mais
    antigo caem em 2019 a 2021 e dizem, em menos de uma hora, se a corrida
    completa se paga.
    """
    pasta.mkdir(parents=True, exist_ok=True)
    if sujeito is None:
        sujeito = carregar_config().sujeito
    caminho = pasta / "triagem.csv"
    anteriores: list[dict] = []
    if caminho.exists():
        with caminho.open(encoding="utf-8-sig", newline="") as f:
            anteriores = list(csv.DictReader(f))
    conhecidos = {l.get("url_google") for l in anteriores if l.get("url_google")}
    conhecidos |= {l.get("prova_url") for l in anteriores if l.get("prova_url")}

    resumo = {"mapas": 0, "enderecos": 0, "com_o_nome": 0, "novas": 0, "falhas": 0}
    novas: list[dict] = []
    for mapa in config.get("mapas") or []:
        indice = mapa.get("indice") or ""
        pausa = pausa_do_dominio(config, indice, float(config.get("pausa_resolucao_s", 2)))
        try:
            indice_xml = obter(indice)
        except ErroDeRede as exc:
            print(f"  indice nao respondeu: {exc}", flush=True)
            resumo["falhas"] += 1
            continue
        alvos = mapas_a_usar(indice_xml, list(mapa.get("prefixos") or []))
        print(f"  {mapa.get('nome', '')}: {len(alvos)} mapas, pausa de {pausa:.0f}s entre pedidos", flush=True)
        for i, alvo in enumerate(alvos, 1):
            if limite is not None and len(novas) >= limite:
                break
            dormir(pausa)
            try:
                xml = obter(alvo)
            except ErroDeRede as exc:
                print(f"  {i}/{len(alvos)}  falhou {alvo}: {exc}", flush=True)
                resumo["falhas"] += 1
                continue
            resumo["mapas"] += 1
            enderecos = enderecos_do_mapa(xml)
            resumo["enderecos"] += len(enderecos)
            do_sujeito = [u for u in enderecos if sujeito.aparece_em(u)]
            resumo["com_o_nome"] += len(do_sujeito)
            for url in do_sujeito:
                if url in conhecidos or limite is not None and len(novas) >= limite:
                    continue
                conhecidos.add(url)
                novas.append(linha_do_mapa(url, str(mapa.get("nome") or "")))
            print(f"  {i}/{len(alvos)}  {len(enderecos):4d} enderecos, {len(do_sujeito):3d} com o nome, {len(novas):3d} novas ate agora", flush=True)

    resumo["novas"] = len(novas)
    if novas:
        gravar_triagem(pasta, anteriores + novas)
    return resumo


def triar(config: dict, pasta: Path) -> dict:
    linhas = list(ler_csv(pasta).values())
    retidas = agrupar(config, linhas, carregar_config().sujeito)
    caminho = pasta / "triagem.csv"
    if caminho.exists():
        with caminho.open(encoding="utf-8-sig", newline="") as f:
            retidas = fundir_triagem(retidas, list(csv.DictReader(f)))
    gravar_triagem(pasta, retidas)
    contagem = {}
    for linha in retidas:
        contagem[linha["grupo"]] = contagem.get(linha["grupo"], 0) + 1
    return {"colhidas": len(linhas), "retidas": len(retidas), **contagem}


# --- verificacao na pagina do canal ----------------------------------------


def duracao_no_texto(config: dict, texto: str) -> int | None:
    """Duracao declarada no corpo, quando a pagina nao a publica para
    maquinas. Os padroes vivem em config/gnews.yml, cada um com as suas
    unidades.

    As unidades sao declaradas e nao deduzidas do numero de grupos. Uma
    primeira versao multiplicava tudo por sessenta a partir da direita e
    lia "1h 12min" como 72 segundos: um erro que ninguem veria, porque o
    numero sai plausivel. Zero nunca e duracao, aqui como em todo o
    projeto.
    """
    fatores = {"h": 3600, "min": 60, "s": 1}
    for regra in config.get("padroes_duracao") or []:
        achado = re.search(regra["padrao"], texto, re.IGNORECASE)
        if not achado:
            continue
        unidades = regra["unidades"]
        grupos = achado.groups()
        if len(grupos) != len(unidades):
            continue
        segundos = sum(int(g) * fatores[u] for g, u in zip(grupos, unidades) if g)
        if segundos > 0:
            return segundos
    return None


def desescapar(texto: str) -> str:
    """Desfaz entidades HTML ate o texto estabilizar, no maximo tres vezes.

    Uma pagina real serve o nome com o `&` ja escapado (`Andr&amp;#233;`).
    Uma passagem so devolve `Andr&#233;`, que foi parar ao registo curado
    como nome de programa e se ve na pagina de Fontes. Pior do que feio:
    o nome escapado nao e igual ao nome do sujeito, por isso a regra que
    recusa usar o nome do convidado como nome do programa nao disparava,
    e o programa entra na chave do bloco.

    O limite de tres existe para que um texto construido para nunca
    estabilizar nao prenda a ferramenta.
    """
    for _ in range(3):
        desfeito = html.unescape(texto)
        if desfeito == texto:
            break
        texto = desfeito
    return texto


def anotar(linha: dict, texto: str) -> None:
    """Acrescenta uma nota a linha, uma vez so.

    Cada corrida do `--verificar` acrescentava a nota outra vez: a mesma
    mensagem de 403 apareceu seis vezes na mesma celula, que passou a ser
    ilegivel precisamente nas linhas que mais precisam de explicacao. A
    nota diz o que se sabe da linha, nao quantas vezes se tentou.
    """
    notas = [n for n in (linha.get("nota") or "").split(" | ") if n.strip()]
    if texto not in notas:
        notas.append(texto)
    linha["nota"] = " | ".join(notas)


def programa_do_titulo(config: dict, titulo: str) -> str:
    """Parte do titulo antes do primeiro separador. Os canais escrevem
    "Programa - Convidado - ep. N". Os separadores vivem em YAML, como no
    resto do projeto."""
    for separador in config.get("separadores_programa") or []:
        if separador in titulo:
            return titulo.split(separador)[0].strip()
    return ""


def verificar_pagina(config: dict, html_texto: str, url: str, sujeito) -> dict:
    """O que a pagina do canal diz, que e o unico sitio onde esta a verdade.

    O indice de noticias da o dia e o titulo da peca; nao diz quem foi o
    convidado quando o canal titula o episodio pelo nome do programa, e
    nunca da duracao. Ler a propria pagina responde as duas perguntas com
    o extrator que ja existe, sem seletores de nenhum site.
    """
    dados = extracao.extrair(html_texto, url)
    # Desescapar antes de tudo: o nome do programa deduz-se do titulo, e um
    # titulo escapado da um nome de programa escapado, que entra na chave
    # do bloco.
    titulo_limpo = desescapar(dados.get("titulo") or "")
    descricao_limpa = desescapar(dados.get("descricao") or "")
    texto = f"{titulo_limpo} {descricao_limpa} {' '.join(dados.get('etiquetas') or [])}"
    duracao = dados.get("duracao_s") or duracao_no_texto(config, extracao.texto_visivel(html_texto))
    return {
        "sujeito_na_pagina": "sim" if sujeito.aparece_em(texto) else "nao",
        "duracao_na_pagina": "" if not duracao else str(duracao),
        "programa_na_pagina": programa_do_titulo(config, titulo_limpo),
        "data_na_pagina": dados.get("publicado_em", "") or "",
        "titulo_na_pagina": " ".join(titulo_limpo.split())[:200],
        # O lead da peca. Numa pagina de imprensa e onde esta escrito "esteve
        # ontem no <programa> do <canal> numa entrevista", que o titulo, quase
        # sempre uma citacao, nao diz. E o que `--emitir --imprensa` le.
        "descricao_na_pagina": " ".join(descricao_limpa.split())[:400],
    }


def sugerir(config: dict, linha: dict, canais_validos: set[str]) -> str:
    """O que `--emitir --imprensa` faria com esta linha se a decisao fosse
    sim, escrito para a pessoa ler antes de decidir.

    Com centenas de pecas de imprensa na triagem, pedir a uma pessoa que
    leia cada lead e aplique as quatro condicoes de cabeca e pedir-lhe que
    repita o que a ferramenta ja sabe fazer. A sugestao diz "sim" com a
    data e como foi lida, ou o motivo pelo qual a peca nao prova nada; a
    decisao continua a ser escrita a mao. Uma sugestao de sim com a data
    a vista e tambem a forma de ver duas pecas sobre a mesma entrevista
    lado a lado.
    """
    if canal_da_prova(config, linha.get("prova_url") or ""):
        return "prova do canal: entra por --emitir"
    if pagina_por_ler(linha):
        # Dizer "nao" aqui era afirmar que a peca nao prova nada quando o
        # que se sabe e que ninguem a leu. O `avaliar_peca` para no mesmo
        # sitio, pela mesma guarda, para que as duas leituras nao voltem a
        # discordar.
        return MOTIVO_POR_LER
    if linha["sujeito_na_pagina"] != "sim":
        return "nao: a pagina nao nomeia o sujeito"
    novo, motivo = avaliar_peca(config, linha, canais_validos)
    if novo is None:
        return f"nao: {motivo}"
    return f"sim: {novo['canal']} a {novo['data']} ({novo['como']})"


def sugerir_todas(config: dict, pasta: Path, canais_validos: set[str] | None = None) -> dict:
    """Reescreve a coluna `sugestao` de todas as linhas da triagem.

    Nao pede nada a rede: le so o que ja esta no CSV. Existe por duas
    razoes, ambas vistas na corrida de 2026-09-09. A primeira e um defeito:
    o `--verificar` so escrevia a sugestao das paginas que visitou nessa
    corrida, e as 150 linhas ja verificadas numa sessao anterior e as 124
    que nao responderam ficaram com a coluna vazia, precisamente as que
    mais precisam de um motivo escrito. A segunda e o ciclo de trabalho:
    depois de preencher `canal` ou `data_emissao` a mao no Excel, correr
    isto diz logo se a linha passa a entrar, sem esperar por outra volta
    de rede.
    """
    caminho = pasta / "triagem.csv"
    if not caminho.exists():
        raise SystemExit("nao ha triagem.csv: correr primeiro com --triar")
    with caminho.open(encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f))
    if canais_validos is None:
        canais_validos = set(carregar_config().canais)
    resumo = {"linhas": len(linhas), "sim": 0, "nao": 0, "por_ler": 0, "do_canal": 0, "ja_decididas": 0}
    motivos: dict[str, int] = {}
    for linha in linhas:
        sugestao = sugerir(config, linha, canais_validos)
        linha["sugestao"] = sugestao
        if linha.get("decisao"):
            resumo["ja_decididas"] += 1
        if sugestao.startswith("sim"):
            resumo["sim"] += 1
        elif sugestao.startswith("por ler"):
            resumo["por_ler"] += 1
        elif sugestao.startswith("prova do canal"):
            resumo["do_canal"] += 1
        elif sugestao.startswith("nao"):
            resumo["nao"] += 1
            motivo = sugestao[5:].split(";")[0]
            motivos[motivo] = motivos.get(motivo, 0) + 1
    gravar_triagem(pasta, linhas)
    # Os motivos ordenados dizem onde esta o trabalho: um motivo que domina
    # e um sinal de que ha uma regra a cortar de mais, nao 600 pecas mas.
    for motivo, quantas in sorted(motivos.items(), key=lambda p: -p[1]):
        print(f"  {quantas:4d}  {motivo}", flush=True)
    return resumo


def verificar(config: dict, pasta: Path, sujeito=None, canais_validos: set[str] | None = None, obter=obter_texto, dormir=time.sleep) -> dict:
    """Visita cada candidato triado e escreve o que a pagina diz.

    Nao decide nada: preenche colunas e, quando a pagina nao nomeia o
    sujeito, propoe `nao` na decisao com o motivo. Numa peca de imprensa
    escreve ainda a coluna `sugestao` (ver `sugerir`). A decisao continua
    a ser de uma pessoa, e uma decisao ja escrita nunca e substituida.
    """
    caminho = pasta / "triagem.csv"
    if not caminho.exists():
        raise SystemExit("nao ha triagem.csv: correr primeiro com --triar")
    with caminho.open(encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f))
    finais = {l["url_google"]: l.get("url_final", "") for l in ler_csv(pasta).values()}
    if sujeito is None or canais_validos is None:
        editorial = carregar_config()
        sujeito = sujeito or editorial.sujeito
        canais_validos = canais_validos if canais_validos is not None else set(editorial.canais)
    omissao = float(config.get("pausa_resolucao_s", 2))
    resumo = {"visitadas": 0, "com_sujeito": 0, "sem_sujeito": 0, "com_duracao": 0, "sem_pagina": 0}

    for i, linha in enumerate(linhas, 1):
        if linha.get("sujeito_na_pagina"):
            continue
        url = linha.get("prova_url") or finais.get(linha["url_google"]) or resolver_url(linha["url_google"])
        # A pausa e a do dominio que se vai pedir, nao uma so para todos: um
        # dominio que pede 300 segundos nao pode arrastar os outros, nem ser
        # arrastado por eles.
        pausa = pausa_do_dominio(config, url or "", omissao)
        if not url:
            anotar(linha, "ligacao por resolver")
            resumo["sem_pagina"] += 1
            print(f"  {i}/{len(linhas)}  sem ligacao", flush=True)
            dormir(pausa)
            continue
        linha["prova_url"] = linha.get("prova_url") or url
        try:
            html_texto = obter(url)
        except ErroDeRede as exc:
            anotar(linha, f"pagina nao respondeu: {exc}")
            resumo["sem_pagina"] += 1
            print(f"  {i}/{len(linhas)}  falhou {url[:70]}", flush=True)
            dormir(pausa)
            continue
        linha.update(verificar_pagina(config, html_texto, url, sujeito))
        resumo["visitadas"] += 1
        if linha["sujeito_na_pagina"] == "sim":
            resumo["com_sujeito"] += 1
        else:
            resumo["sem_sujeito"] += 1
            if not linha.get("decisao"):
                linha["decisao"] = "nao"
                anotar(linha, "a pagina do canal nao nomeia o sujeito")
        if linha["duracao_na_pagina"]:
            resumo["com_duracao"] += 1
        espera = f"  (a esperar {pausa:.0f}s)" if pausa > omissao else ""
        print(f"  {i}/{len(linhas)}  {linha['sujeito_na_pagina']:4s} {linha['duracao_na_pagina'] or '-':>6s}  {linha['titulo_na_pagina'][:60]}{espera}", flush=True)
        if i % 10 == 0:
            gravar_triagem(pasta, linhas)
        dormir(pausa)
    gravar_triagem(pasta, linhas)
    # A sugestao escreve-se para todas as linhas, nao so para as visitadas
    # agora: as de sessoes anteriores e as que nao responderam tambem
    # precisam do motivo escrito.
    resumo.update(sugerir_todas(config, pasta, canais_validos))
    return resumo


# --- geracao do registo curado ---------------------------------------------


# Motivo unico para uma peca cuja pagina nunca foi lida. E uma constante
# porque e escrito em dois sitios, a sugestao e a emissao, e foram esses
# dois sitios a discordar: ver `pagina_por_ler`.
MOTIVO_POR_LER = "por ler: a pagina nao respondeu; abrir no browser"


def pausa_do_dominio(config: dict, url: str, omissao: float) -> float:
    """O ritmo que o proprio sitio pede, quando pede algum.

    Um `robots.txt` pode declarar `Crawl-Delay`, e um dos dominios de onde
    vem a maior parte da prova de imprensa pede 300 segundos. Nao ha
    bloqueio: as paginas respondem a qualquer ritmo. O numero cumpre-se
    porque o projeto ja recusou uma fonte cujo `robots.txt` bloqueia
    maquinas, e as duas coisas nao podem valer ao mesmo tempo.

    Os dominios e os segundos vivem em YAML, com a medicao ao lado.
    """
    dominio = (urllib.parse.urlsplit(url).hostname or "").lower()
    por_dominio = config.get("pausa_por_dominio") or {}
    for nome, segundos in por_dominio.items():
        if dominio == nome or dominio.endswith("." + nome):
            return float(segundos)
    return omissao


def pagina_por_ler(linha: dict) -> bool:
    """A pagina da peca nunca foi lida, logo nao ha lead para avaliar.

    124 das 851 linhas de 2026-09-09 nao responderam, umas a 403 e outras
    a recusar a maquina. Ate 2026-09-09 a noite o `sugerir` parava aqui e
    devolvia "por ler", mas o `emitir_imprensa` avaliava a linha na mesma,
    so com o titulo que o indice deu. As duas leituras discordavam sobre a
    mesma linha, e a peca do Expresso de 2026-02-05 saiu recusada com um
    motivo que nao era o dela.

    Pior do que o motivo errado: um titulo de indice que dissesse o canal,
    a palavra e o dia bastava para publicar uma emissao a partir de uma
    pagina que ninguem abriu. "Nao sei" nao e "nao", mas tambem nao e
    "sim".
    """
    return not (linha.get("sujeito_na_pagina") or "").strip()


def canal_da_prova(config: dict, url: str) -> str:
    return canal_por_dominio(config, urllib.parse.urlsplit(url).hostname or "")


def vetada(linha: dict) -> bool:
    """Uma linha so fica de fora se alguem escrever uma recusa.

    Ate 2026-09-09 era o contrario: so entrava o que dissesse `sim`, e com
    a triagem a passar de 150 para 851 linhas isso queria dizer que
    ninguem escrevia o `sim` e nada entrava. A avaliacao das quatro
    condicoes passou a ser a decisao, e a coluna `decisao` passou a servir
    para uma coisa so: travar uma linha que a avaliacao aceitaria. Vale
    para o veto escrito a mao e para o que o `--verificar` escreve quando
    a pagina nao nomeia o sujeito.

    Isto vale so para a prova de imprensa. O registo do canal
    (`--emitir`) continua a exigir `sim` escrito, porque a excecao que lhe
    permite saltar a prova positiva de formato e as rondas e uma pessoa
    ter aberto a pagina.
    """
    return bool((linha.get("decisao") or "").strip()) and not decidida_sim(linha)


def decidida_sim(linha: dict) -> bool:
    """Aceita `sim` como for escrito, com ou sem acentos e maiusculas.

    A recusa escreve-se de varias maneiras (`nao`, `não`, `n`) e nao ha
    forma segura de as prever todas; por isso a regra e o contrario:
    so entra o que diz sim, e tudo o resto fica de fora. Erro por
    defeito, que e a regra do projeto.
    """
    valor = unicodedata.normalize("NFKD", (linha.get("decisao") or "").strip().lower())
    return "".join(c for c in valor if not unicodedata.combining(c)) == "sim"


def emitir(config: dict, pasta: Path, canais_validos: set[str]) -> tuple[list[dict], list[str]]:
    """Converte as decisoes da triagem em linhas do registo curado.

    Agrupa por (canal, data): varias linhas da triagem sao a mesma
    emissao vista por fontes diferentes, e uma emissao entra uma vez. O
    simulcast fica agrupado por `mesma_entrevista`, que e a data: canais
    diferentes no mesmo dia sao duas emissoes com a mesma chave, que e
    exatamente a decisao editorial 3.

    Recusa e nao adivinha:
      - sem `sim` na decisao, fica de fora;
      - prova fora dos nove canais, fica de fora com aviso. Uma peca de
        imprensa sobre a entrevista nao e a pagina do canal e nao entra no
        registo do canal; e material para `--emitir --imprensa`, que a
        escreve no clipping com as suas proprias regras;
      - sem duracao, a linha entra sem `duracao_s`. Conta como emissao e
        nunca como tempo. Nunca zero, nunca estimativa.
    """
    caminho = pasta / "triagem.csv"
    with caminho.open(encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f))

    avisos: list[str] = []
    blocos: dict[tuple[str, str], dict] = {}
    for linha in linhas:
        if not decidida_sim(linha):
            continue
        prova = (linha.get("prova_url") or "").strip()
        canal = (linha.get("canal") or "").strip() or canal_da_prova(config, prova)
        # A folha de calculo reescreve qualquer coluna que pareca uma
        # data: 2024-03-20 volta como 20/03/2024. Cortar dez caracteres
        # escreveria essa forma no registo e o coletor rejeitava-a. Le-se
        # com a mesma funcao que le as datas dos sites.
        # `data_emissao`, escrita a mao, ganha a tudo: a data que a pagina
        # declara e a da publicacao, e um canal que publica na terca o
        # artigo sobre a entrevista de segunda deslocava a emissao um dia.
        data = (
            extracao.data_para_iso(linha.get("data_emissao") or "")
            or extracao.data_para_iso(linha.get("data_na_pagina") or "")
            or extracao.data_para_iso(linha.get("data") or "")
        )
        if not data:
            avisos.append(f"{linha.get('titulo', '')[:60]}: data ilegivel ({linha.get('data', '')!r})")
            continue
        if canal not in canais_validos:
            avisos.append(f"{data} {linha.get('titulo', '')[:60]}: prova fora dos nove canais, e imprensa? usar --imprensa ({prova[:60]})")
            continue
        if not prova.startswith("http"):
            avisos.append(f"{data} {linha.get('titulo', '')[:60]}: sem prova")
            continue
        duracao = (linha.get("duracao") or linha.get("duracao_na_pagina") or "").strip()
        programa = (linha.get("programa") or linha.get("programa_na_pagina") or "").strip()
        novo = {
            "data": data,
            "canal": canal,
            "programa": programa or "não apurado",
            "prova": prova,
            # Titulos colhidos antes de a leitura desfazer as entidades
            # ficaram com `&#233;` em vez de `é`. Desfazer aqui evita
            # obrigar a repetir a verificacao inteira so por causa disso.
            "titulo": html.unescape((linha.get("titulo_na_pagina") or linha.get("titulo") or "").strip()),
            "mesma_entrevista": data,
        }
        if duracao.isdigit() and int(duracao) > 0:
            novo["duracao_s"] = int(duracao)

        chave = (canal, data)
        antigo = blocos.get(chave)
        if antigo is None:
            blocos[chave] = novo
            continue
        # Entre duas linhas do mesmo bloco fica a que tem duracao apurada,
        # e entre duas com duracao a mais longa: a curta e tipicamente um
        # recorte da mesma emissao. E a mesma regra do coletor.
        if novo.get("duracao_s", 0) > antigo.get("duracao_s", 0):
            blocos[chave] = novo

    # Por data e depois por canal: o ficheiro le-se como uma cronologia,
    # que e como quem contesta um numero o vai percorrer.
    ordenadas = sorted(blocos.values(), key=lambda l: (l["data"], l["canal"]))
    # A chave de simulcast so faz sentido quando ha mais do que um canal
    # no mesmo dia; sozinha nao agrupa nada e so poluia o ficheiro.
    por_data: dict[str, int] = {}
    for linha in ordenadas:
        por_data[linha["data"]] = por_data.get(linha["data"], 0) + 1
    for linha in ordenadas:
        if por_data[linha["data"]] < 2:
            linha.pop("mesma_entrevista", None)
    return ordenadas, avisos


def emitir_paginas_de_canal(config: dict, pasta: Path, canais_validos: set[str],
                            ja_no_registo: set[tuple[str, str]] | None = None) -> tuple[list[dict], list[str]]:
    """As provas em dominio de canal que ninguem escreveu `sim`.

    Eram 150 a 2026-09-09, ja colhidas e verificadas, paradas so porque o
    `--emitir` exige uma aprovacao escrita linha a linha. Esse padrao foi
    abandonado no clipping por nao escalar, e nao ha razao para o manter
    aqui: a avaliacao decide e uma pessoa veta.

    O que muda em relacao ao `--emitir` nao e o crivo desta funcao, e o
    destino. Estas linhas vao para uma fonte que **nao** tem a isencao do
    registo curado, por isso e o coletor que lhes aplica a prova positiva
    de formato e as rondas. Aqui so se recusa o que nem sequer e
    candidato: sem data legivel, sem prova, ou prova que nao e de um canal.
    As que nao tiverem duracao apurada vao parar a quarentena como
    `por_confirmar`, com o motivo escrito, e o numero sai no ecra.

    Uma emissao que o registo verificado a mao ja tenha nao se repete: a
    leitura humana ganha, e o coletor poria esta na quarentena de qualquer
    maneira.
    """
    caminho = pasta / "triagem.csv"
    with caminho.open(encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f))
    ja_no_registo = ja_no_registo or set()

    avisos: list[str] = []
    motivos: dict[str, int] = {}
    blocos: dict[tuple[str, str], dict] = {}
    for linha in linhas:
        prova = (linha.get("prova_url") or "").strip()
        if not prova.startswith("http"):
            continue
        canal = (linha.get("canal") or "").strip() or canal_da_prova(config, prova)
        # Sem canal a prova e de imprensa e pertence ao outro modo. Nao e
        # erro nem se conta: sao centenas e ja tem o seu proprio ecra.
        if not canal or canal not in canais_validos:
            continue
        if vetada(linha):
            motivos["vetada a mao"] = motivos.get("vetada a mao", 0) + 1
            continue
        if pagina_por_ler(linha):
            motivos["por ler: a pagina nao respondeu"] = motivos.get("por ler: a pagina nao respondeu", 0) + 1
            continue
        if (linha.get("sujeito_na_pagina") or "").strip() != "sim":
            motivos["a pagina nao nomeia o sujeito"] = motivos.get("a pagina nao nomeia o sujeito", 0) + 1
            continue
        data = (
            extracao.data_para_iso(linha.get("data_emissao") or "")
            or extracao.data_para_iso(linha.get("data_na_pagina") or "")
            or extracao.data_para_iso(linha.get("data") or "")
        )
        if not data:
            motivos["data ilegivel"] = motivos.get("data ilegivel", 0) + 1
            continue
        rotulo = html.unescape((linha.get("titulo_na_pagina") or linha.get("titulo") or "").strip())
        if (canal, data) in ja_no_registo:
            motivos["ja no registo verificado a mao"] = motivos.get("ja no registo verificado a mao", 0) + 1
            continue
        programa = (linha.get("programa") or linha.get("programa_na_pagina") or "").strip()
        novo = {
            "data": data,
            "canal": canal,
            "programa": programa or "não apurado",
            "prova": prova,
            "titulo": rotulo,
            "mesma_entrevista": data,
        }
        duracao = (linha.get("duracao") or linha.get("duracao_na_pagina") or "").strip()
        if duracao.isdigit() and int(duracao) > 0:
            novo["duracao_s"] = int(duracao)

        chave = (canal, data)
        antigo = blocos.get(chave)
        # A mesma regra de desempate do coletor: com duracao ganha a sem
        # duracao, e entre duas com duracao ganha a mais longa, porque a
        # curta e tipicamente um recorte da mesma emissao.
        if antigo is None or novo.get("duracao_s", 0) > antigo.get("duracao_s", 0):
            blocos[chave] = novo

    for motivo, quantas in sorted(motivos.items(), key=lambda p: -p[1]):
        avisos.append(f"{quantas} paginas: {motivo}")
    ordenadas = sorted(blocos.values(), key=lambda l: (l["data"], l["canal"]))
    com_duracao = sum(1 for l in ordenadas if l.get("duracao_s"))
    avisos.append(f"{com_duracao} de {len(ordenadas)} com duracao apurada")
    por_data: dict[str, int] = {}
    for linha in ordenadas:
        por_data[linha["data"]] = por_data.get(linha["data"], 0) + 1
    for linha in ordenadas:
        if por_data[linha["data"]] < 2:
            linha.pop("mesma_entrevista", None)
    return ordenadas, avisos


def escrever_registo(entrevistas: list[dict], caminho: Path) -> None:
    """Reescreve config/entrevistas.yml, preservando o cabecalho.

    O cabecalho documenta os campos e e a primeira coisa que ve quem
    abrir o ficheiro para contestar um numero.
    """
    texto = caminho.read_text(encoding="utf-8")
    marca = "\nentrevistas:"
    cabecalho = texto.split(marca)[0]
    corpo = yaml.safe_dump({"entrevistas": entrevistas}, allow_unicode=True, sort_keys=False, width=1000)
    caminho.write_text(cabecalho + "\n" + corpo, encoding="utf-8", newline="\n")


# --- prova de imprensa -----------------------------------------------------
#
# Uma peca de imprensa prova que a entrevista existiu e em que dia, e mais
# nada. Nao prova a duracao, e raramente a duracao lhe interessa. Vai para
# config/clipping.yml, com `origem: imprensa` declarada na fonte, e o site
# mostra-a assim. As quatro condicoes abaixo sao as que qualquer pessoa
# consegue verificar abrindo a peca; cada recusa fica escrita com o motivo.


def canais_no_texto(config: dict, texto: str) -> list[str]:
    """Todos os canais nomeados no texto, dos nomes mais longos para os mais
    curtos. O nome do canal de noticias contem o do generalista do mesmo
    grupo; retirar o longo antes de procurar o curto evita contar os dois."""
    palheiro = normalizar(texto)
    pares = []
    for canal, nomes in (config.get("canais_por_texto") or {}).items():
        for nome in nomes:
            pares.append((len(nome), normalizar(nome), canal))
    encontrados: list[str] = []
    for _, nome, canal in sorted(pares, reverse=True):
        padrao = rf"\b{re.escape(nome)}\b"
        if re.search(padrao, palheiro):
            palheiro = re.sub(padrao, " ", palheiro)
            if canal not in encontrados:
                encontrados.append(canal)
    return encontrados


def entrevista_datada_por_extenso(config: dict, texto: str) -> bool:
    """A peca situa a entrevista noutro periodo, escrito por extenso.

    "Disse em entrevista ao canal em dezembro de 2021 que (...), hoje um
    novo militante diz outra coisa" tem a palavra do dia numa frase que
    fala do presente e a entrevista datada a um ano de distancia. Lido
    pelo marcador, entrava com a data da peca.

    Duas formas de a frase datar a entrevista, e as duas foram medidas em
    pecas reais a 2026-09-09:

    - um mes seguido de ano ("em dezembro de 2021", "Em novembro de
      2020"): e uma data escrita por extenso e conta onde quer que
      esteja na frase;
    - um ano sozinho, mas so a menos de `janela_do_ano` caracteres da
      palavra. A primeira versao desta regra aceitava um ano sozinho em
      qualquer sitio da frase, e cortou uma emissao certa por causa de um
      "revogado em 2005" que estava a 366 caracteres, a falar de outra
      coisa. Era erro por excesso numa regra escrita para evitar erro por
      excesso.
    """
    regras = config.get("imprensa") or {}
    termos = tuple((config.get("marcadores_formato") or {}).get("entrevista") or ())
    meses = "|".join(re.escape(normalizar(m)) for m in (regras.get("meses") or ()) if m)
    janela = int(regras.get("janela_do_ano", 60))
    ano = r"\b(19|20)\d{2}\b"
    for frase in re.split(r"[.!?\n]+", texto):
        if not contem_palavra(frase, termos):
            continue
        plana = normalizar(frase)
        if meses and re.search(rf"\b({meses})\b\s+de\s+{ano}", plana):
            return True
        onde = [m.start() for t in termos for m in re.finditer(re.escape(normalizar(t)), plana)]
        if any(min(abs(m.start() - i) for i in onde) <= janela for m in re.finditer(ano, plana) if onde):
            return True
    return False


def data_de_emissao(config: dict, texto: str, publicado: str) -> tuple[str, str]:
    """O dia da emissao que a peca fixa, a partir do dia em que foi publicada.

    Devolve (data, como). "Ontem" recua um dia, "amanha" avanca um, "hoje"
    e os seus equivalentes sao o proprio dia. Um dia da semana precisa de
    saber para que lado se le: numa peca que anuncia ("nao perca", "sera
    as 21h") e o proximo com esse nome, publicacao inclusive; numa peca
    que relata ("esteve", "disse") e o mais recente. Sem verbo de relato
    nem marca de anuncio, "esta segunda-feira" tanto e a que passou como
    a que vem, e a data fica vazia: adivinhar o lado era errar uma semana.

    Sem nenhum destes, a data fica vazia e a linha espera por uma pessoa:
    a data de publicacao de uma peca nao e a data da emissao, e escreve-la
    seria inventar um dia.

    Os anuncios contam desde 2026-09-09, por decisao do autor: uma
    entrevista anunciada a um canal raramente se cancela ou adia. O que
    muda para o leitor e visivel na linha, porque `publicado_em` fica
    anterior a `data`.

    Limite conhecido: a publicacao le-se em UTC e uma peca escrita depois
    da meia-noite sobre "esta noite" cai no dia seguinte. E por isso que a
    coluna `data_emissao`, escrita a mao, ganha sempre a esta leitura.
    """
    regras = config.get("imprensa") or {}
    dia = extracao.data_para_iso(publicado or "")
    if not dia:
        return "", ""
    publicado_em = date.fromisoformat(dia)
    if entrevista_datada_por_extenso(config, texto):
        return "", "a peca situa a entrevista noutro periodo, por extenso"
    if contem_palavra(texto, tuple(regras.get("ontem") or ())):
        return (publicado_em - timedelta(days=1)).isoformat(), "ontem"
    if contem_palavra(texto, tuple(regras.get("amanha") or ())):
        return (publicado_em + timedelta(days=1)).isoformat(), "amanhã"
    anuncia = bool(contem_palavra(texto, tuple(regras.get("anuncio") or ())))
    relata = bool(contem_palavra(texto, tuple(regras.get("relato") or ())))
    for nome, indice in (regras.get("dias_da_semana") or {}).items():
        if contem_palavra(texto, (nome,)):
            if anuncia:
                avanco = (int(indice) - publicado_em.weekday()) % 7
                return (publicado_em + timedelta(days=avanco)).isoformat(), f"{nome}, anúncio"
            if relata:
                recuo = (publicado_em.weekday() - int(indice)) % 7
                return (publicado_em - timedelta(days=recuo)).isoformat(), nome
            return "", "dia da semana sem verbo que diga se ja foi ou vai ser"
    if contem_palavra(texto, tuple(regras.get("hoje") or ())):
        return dia, "hoje, anúncio" if anuncia and not relata else "hoje"
    return "", ""


def avaliar_peca(config: dict, linha: dict, canais_validos: set[str]) -> tuple[dict | None, str]:
    """Aplica a uma peca de imprensa as quatro condicoes para contar.

    Devolve (linha do clipping, "") quando a peca prova a emissao, ou
    (None, motivo) quando nao prova, com o motivo escrito para a pessoa
    saber o que falta. E a mesma funcao que o `--verificar` usa para
    escrever a coluna `sugestao` e que o `--emitir --imprensa` usa para
    decidir: uma so leitura das regras, para que a sugestao que a pessoa
    ve na triagem seja o que a emissao vai fazer.

      0. ter sido lida. Uma peca cuja pagina nao respondeu nao se avalia
         pelo titulo que o indice lhe deu: ver `pagina_por_ler`;
      1. nomear um canal, e um so. "Em entrevista a televisao" nao serve;
         duas emissoras no mesmo lead e a pessoa que escolhe (coluna
         `canal`);
      2. dizer entrevista, no titulo ou no lead, e nao dizer debate nem
         declaracoes no titulo. A classificacao pelo titulo e a regra do
         projeto; o lead entra aqui porque os jornais titulam com a
         citacao e deixam "numa entrevista exclusiva" para a primeira frase;
      3. fixar o dia da emissao (ver `data_de_emissao`), ou ter o dia
         escrito a mao em `data_emissao`;
      4. relatar ou anunciar. Ate 2026-09-09 so o relato contava; o
         anuncio passou a contar por decisao do autor, com a data lida
         para a frente. A peca que nem relata nem anuncia e que so fixa o
         dia por um nome de semana continua a esperar por uma pessoa.
    """
    if pagina_por_ler(linha):
        return None, MOTIVO_POR_LER

    prova = (linha.get("prova_url") or "").strip()
    titulo = html.unescape((linha.get("titulo_na_pagina") or linha.get("titulo") or "").strip())
    lead = html.unescape((linha.get("descricao_na_pagina") or "").strip())
    texto = f"{titulo} {lead}"

    a_mao = (linha.get("canal") or "").strip()
    nomeados = canais_no_texto(config, texto)
    canal = a_mao or (nomeados[0] if len(nomeados) == 1 else "")
    if not canal:
        motivo = "nomeia mais de um canal" if len(nomeados) > 1 else "nao nomeia o canal"
        return None, f"{motivo}; escrever o canal a mao"
    if canal not in canais_validos:
        return None, f"canal fora dos nove ({canal})"

    formato_titulo = formato_no_titulo(config, titulo)
    if "entrevista" not in formato_no_titulo(config, texto):
        return None, "a peca nao diz entrevista"
    if any(f != "entrevista" for f in formato_titulo.split("+") if f):
        return None, f"o titulo diz {formato_titulo}, nao e entrevista a solo"

    publicado = extracao.data_para_iso(linha.get("data_na_pagina") or "") or extracao.data_para_iso(linha.get("data") or "")
    data_a_mao = extracao.data_para_iso(linha.get("data_emissao") or "")
    if data_a_mao:
        data, como = data_a_mao, "a mao"
    else:
        data, como = data_de_emissao(config, texto, publicado)
        if not data:
            motivo = como or "a peca nao fixa o dia da emissao"
            return None, f"{motivo}; escrever data_emissao"

    novo = {
        "data": data,
        "canal": canal,
        "programa": (linha.get("programa") or "").strip() or "não apurado",
        "prova": prova,
        "titulo": titulo,
        "mesma_entrevista": data,
        "como": como,
    }
    if publicado and publicado != data:
        novo["publicado_em"] = publicado
    return novo, ""


def duplicados_provaveis(blocos: dict[tuple[str, str], dict]) -> list[str]:
    """Duas pecas sobre o mesmo canal com um dia de intervalo.

    Varios jornais escrevem sobre a mesma entrevista e nem todos fixam o
    dia da mesma maneira: um diz "ontem", outro "esta noite" numa peca
    publicada depois da meia-noite, e a mesma emissao fica com duas datas.
    Fundir as duas seria adivinhar qual esta certa; deixar as duas seria
    contar uma entrevista como duas. Fica o aviso, e a pessoa decide com
    as duas pecas abertas.
    """
    avisos = []
    por_canal: dict[str, list[str]] = {}
    for canal, data in blocos:
        por_canal.setdefault(canal, []).append(data)
    for canal, datas in por_canal.items():
        datas.sort()
        for a, b in zip(datas, datas[1:]):
            if (date.fromisoformat(b) - date.fromisoformat(a)).days == 1:
                avisos.append(f"{a} e {b} em {canal}: um dia de intervalo, possivel duplicado; confirmar com as duas pecas abertas")
    return avisos


def _distancia_ao_dia(linha: dict) -> tuple[int, int]:
    publicado = date.fromisoformat(linha.get("publicado_em") or linha["data"])
    emissao = date.fromisoformat(linha["data"])
    return abs((publicado - emissao).days), 1 if publicado < emissao else 0


def emitir_imprensa(config: dict, pasta: Path, canais_validos: set[str], ja_no_canal: set[tuple[str, str]] | None = None) -> tuple[list[dict], list[str]]:
    """Converte as decisoes da triagem em linhas do clipping de imprensa.

    Le as mesmas linhas de `--emitir`, mas so as cuja prova NAO e uma
    pagina de um canal: as do canal pertencem ao outro modo e aqui sao
    ignoradas em silencio, nao e um erro. As condicoes para entrar estao
    em `avaliar_peca`, que e tambem o que escreve a coluna `sugestao`.

    Uma emissao que ja esteja no registo do canal nao se repete aqui: a
    prova do canal e melhor, e o coletor poria esta na quarentena. Entre
    varias pecas sobre a mesma emissao fica uma, e as que ficam a um dia
    de distancia no mesmo canal saem como aviso, nao como duas linhas.
    """
    caminho = pasta / "triagem.csv"
    with caminho.open(encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f))
    ja_no_canal = ja_no_canal or set()

    avisos: list[str] = []
    motivos: dict[str, int] = {}
    blocos: dict[tuple[str, str], dict] = {}
    for linha in linhas:
        if vetada(linha):
            continue
        prova = (linha.get("prova_url") or "").strip()
        if not prova.startswith("http") or canal_da_prova(config, prova):
            continue
        novo, motivo = avaliar_peca(config, linha, canais_validos)
        rotulo_linha = html.unescape((linha.get("titulo_na_pagina") or linha.get("titulo") or "").strip())[:60]
        if novo is None:
            # Uma linha que alguem marcou `sim` e a avaliacao recusa e um
            # desacordo e sai por inteiro. As outras sao centenas e saem
            # contadas por motivo: 571 linhas no ecra escondem as que
            # interessam.
            if decidida_sim(linha):
                avisos.append(f"{rotulo_linha}: {motivo}")
            else:
                chave_motivo = motivo.split(";")[0]
                motivos[chave_motivo] = motivos.get(chave_motivo, 0) + 1
            continue
        novo.pop("como", None)
        if (novo["canal"], novo["data"]) in ja_no_canal:
            avisos.append(f"{novo['data']} {rotulo_linha}: ja no registo do canal")
            continue
        chave = (novo["canal"], novo["data"])
        antigo = blocos.get(chave)
        # Duas pecas sobre a mesma emissao: fica a publicada mais perto do
        # dia, que e a que menos depende de memoria. A distancia igual
        # ganha a que relata, porque prova que aconteceu, sobre a que so
        # anunciava.
        if antigo is None or _distancia_ao_dia(novo) < _distancia_ao_dia(antigo):
            blocos[chave] = novo

    for motivo, quantas in sorted(motivos.items(), key=lambda p: -p[1]):
        avisos.append(f"{quantas} pecas: {motivo}")
    avisos.extend(duplicados_provaveis(blocos))
    ordenadas = sorted(blocos.values(), key=lambda l: (l["data"], l["canal"]))
    por_data: dict[str, int] = {}
    for linha in ordenadas:
        por_data[linha["data"]] = por_data.get(linha["data"], 0) + 1
    for linha in ordenadas:
        if por_data[linha["data"]] < 2:
            linha.pop("mesma_entrevista", None)
    return ordenadas, avisos


def emissoes_do_registo(caminho: Path) -> set[tuple[str, str]]:
    """Os pares (canal, data) que o registo do canal ja tem."""
    if not caminho.exists():
        return set()
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    return {(str(l.get("canal") or ""), str(l.get("data") or "")) for l in (dados.get("entrevistas") or [])}


# --- entrada -----------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Colheita local do Google Noticias por RSS")
    parser.add_argument("--saida", required=True, help="pasta fora do repositorio")
    parser.add_argument("--desde", help="AAAA-MM-DD; por omissao o inicio do tema")
    parser.add_argument("--ate", help="AAAA-MM-DD; por omissao hoje")
    parser.add_argument("--triar", action="store_true", help="reduzir a colheita a uma lista para decidir")
    parser.add_argument("--emitir", action="store_true", help="escrever config/entrevistas.yml a partir das decisoes")
    parser.add_argument("--imprensa", action="store_true", help="com --emitir: escrever config/clipping.yml com as provas de imprensa")
    parser.add_argument("--canal", action="store_true", help="com --emitir: escrever config/paginas_de_canal.yml com as provas de canal que ninguem leu")
    parser.add_argument("--verificar", action="store_true", help="ler a pagina do canal de cada candidato triado")
    parser.add_argument("--sugerir", action="store_true", help="reescrever a coluna sugestao sem pedir nada a rede")
    parser.add_argument("--resolver", action="store_true", help="seguir as ligacoes dos candidatos triados ate ao destino")
    parser.add_argument("--mapa", action="store_true", help="acrescentar a triagem as pecas cujo endereco nomeia o sujeito, pelos mapas de sitio")
    parser.add_argument("--limite", type=int, help="com --resolver ou --mapa: parar ao fim de N, para medir antes de gastar")
    parser.add_argument("--tudo", action="store_true", help="com --resolver: resolver a colheita inteira, nao so os triados")
    args = parser.parse_args(argv)

    config = carregar()
    pasta = pasta_de_saida(args.saida)
    if args.emitir and args.canal:
        editorial = carregar_config()
        entrevistas, avisos = emitir_paginas_de_canal(
            config, pasta, set(editorial.canais), emissoes_do_registo(FICHEIRO_ENTREVISTAS)
        )
        for aviso in avisos:
            print(f"  {aviso}", flush=True)
        escrever_registo(entrevistas, FICHEIRO_PAGINAS_DE_CANAL)
        resumo = {"paginas_de_canal": len(entrevistas)}
    elif args.emitir and args.imprensa:
        editorial = carregar_config()
        entrevistas, avisos = emitir_imprensa(config, pasta, set(editorial.canais), emissoes_do_registo(FICHEIRO_ENTREVISTAS))
        for aviso in avisos:
            print(f"  fora: {aviso}", flush=True)
        escrever_registo(entrevistas, FICHEIRO_CLIPPING)
        resumo = {"emissoes_imprensa": len(entrevistas), "fora": len(avisos)}
    elif args.emitir:
        editorial = carregar_config()
        entrevistas, avisos = emitir(config, pasta, set(editorial.canais))
        for aviso in avisos:
            print(f"  fora: {aviso}", flush=True)
        escrever_registo(entrevistas, FICHEIRO_ENTREVISTAS)
        resumo = {"emissoes": len(entrevistas), "fora": len(avisos)}
    elif args.verificar:
        print(f"a verificar candidatos de {pasta}", flush=True)
        resumo = verificar(config, pasta)
    elif args.sugerir:
        print(f"a rever as sugestoes de {pasta}", flush=True)
        resumo = sugerir_todas(config, pasta)
    elif args.mapa:
        print(f"a colher os mapas de sitio para {pasta}", flush=True)
        resumo = colher_mapas(config, pasta, limite=args.limite)
    elif args.triar:
        print(f"a triar {pasta}", flush=True)
        resumo = triar(config, pasta)
    elif args.resolver:
        print(f"a resolver ligacoes em {pasta}", flush=True)
        resumo = resolver(config, pasta, so_triados=not args.tudo, limite=args.limite)
    else:
        desde = date.fromisoformat(args.desde) if args.desde else date.fromisoformat(carregar_config().tema.desde)
        ate = date.fromisoformat(args.ate) if args.ate else datetime.now(timezone.utc).date()
        print(f"a colher de {desde} a {ate} para {pasta}", flush=True)
        resumo = colher(config, pasta, desde, ate)
    print(json.dumps(resumo, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
