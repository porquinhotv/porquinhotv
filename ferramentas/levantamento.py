"""Levantamento automatico das fontes dos canais. Corre uma vez.

    python -m ferramentas.levantamento
    python -m ferramentas.levantamento --canal <id>       so um canal

Le config/levantamento.yml e, para cada canal, sonda as paginas
declaradas e resolve os handles de YouTube para ids UC...
Escreve levantamento/levantamento.json e levantamento/LEVANTAMENTO.md.

Nao decide nada e nao toca em docs/dados. E a resposta a "o que expoe
cada canal?" antes de se escrever um unico adaptador. Uma linha por canal
mesmo quando a resposta e "nada encontrado": a ausencia tambem se
regista, com data.

Nenhum nome de canal, programa ou pessoa vive aqui. Tudo vem do YAML.
"""

from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
import time
import urllib.parse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import yaml

from recolha.modelos import RAIZ, carregar_config, normalizar
from recolha.rede import ErroDeRede, obter_texto

FICHEIRO_CONFIG = RAIZ / "config" / "levantamento.yml"
PASTA_SAIDA = RAIZ / "levantamento"
FEED_YT = "https://www.youtube.com/feeds/videos.xml?channel_id={id}"
PAGINA_YT = "https://www.youtube.com/@{handle}/about"

Obter = Callable[[str], str]

# Mesmos padroes de ferramentas/descobrir.py. Repetidos e nao importados
# de proposito: aquele modulo e uma ferramenta de linha de comandos com
# saida por print, este tem de devolver dados.
ALTERNATE = re.compile(
    r'<link[^>]+rel=["\']alternate["\'][^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
ALTERNATE_INV = re.compile(
    r'<link[^>]+href=["\']([^"\']+)["\'][^>]+type=["\']application/(?:rss|atom)\+xml["\']',
    re.IGNORECASE,
)
CANAL_YT = re.compile(r"\b(UC[0-9A-Za-z_-]{22})\b")
CANONICO_YT = re.compile(r'rel=["\']canonical["\'][^>]+href=["\']https://www\.youtube\.com/channel/(UC[0-9A-Za-z_-]{22})')
TITULO = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
META = re.compile(r"<meta\s[^>]*>", re.IGNORECASE)
# O valor fecha com a mesma aspa que o abriu. Com uma classe que parava em
# qualquer das duas, `content="esteve no 'Grande Programa' do canal"` ficava
# em "esteve no", e a palavra que provava o formato caia fora sem aviso.
META_ATRIB = re.compile(r'(name|property|content)=(["\'])(.*?)\2', re.IGNORECASE | re.DOTALL)
JSONLD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
ETIQUETAS = re.compile(r"<[^>]+>")
SCRIPTS = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


def carregar(caminho: Path = FICHEIRO_CONFIG) -> dict:
    return yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}


# --------------------------------------------------------------------------
# Analise de uma pagina HTML
# --------------------------------------------------------------------------


def _metadados(html: str) -> dict[str, str]:
    """name/property -> content das <meta>. Chaves em minusculas."""
    saida: dict[str, str] = {}
    for etiqueta in META.findall(html):
        pares = {k.lower(): v for k, _, v in META_ATRIB.findall(etiqueta)}
        chave = pares.get("name") or pares.get("property")
        if chave and "content" in pares:
            saida[chave.lower()] = html_mod.unescape(pares["content"])
    return saida


def _jsonld(html: str) -> list[dict]:
    blocos: list[dict] = []
    for bruto in JSONLD.findall(html):
        try:
            dados = json.loads(bruto.strip())
        except json.JSONDecodeError:
            continue
        pilha = dados if isinstance(dados, list) else [dados]
        while pilha:
            d = pilha.pop()
            if not isinstance(d, dict):
                continue
            blocos.append(d)
            if isinstance(d.get("@graph"), list):
                pilha.extend(d["@graph"])
    return blocos


def _texto_visivel(html: str) -> str:
    sem_scripts = SCRIPTS.sub(" ", html)
    return html_mod.unescape(ETIQUETAS.sub(" ", sem_scripts))


def _termos_presentes(texto: str, termos: list[str]) -> list[str]:
    palheiro = normalizar(texto)
    achados = []
    for termo in termos:
        if re.search(rf"\b{re.escape(normalizar(termo))}\b", palheiro):
            achados.append(termo)
    return achados


def analisar_html(html: str, termos: list[str]) -> dict:
    """O que uma pagina expoe sem JavaScript.

    Devolve onde os termos aparecem (titulo, metadados, JSON-LD, corpo),
    se ha JSON-LD de video, os feeds anunciados e os ids de canal de
    YouTube presentes no HTML. E isto que
    decide se um adaptador pode ler a pagina tal como o servidor a envia.
    """
    titulo = html_mod.unescape(TITULO.search(html).group(1)).strip() if TITULO.search(html) else ""
    metadados = _metadados(html)
    blocos = _jsonld(html)

    texto_meta = " ".join(metadados.values())
    campos_jsonld: list[str] = []
    videos = 0
    for bloco in blocos:
        tipo = bloco.get("@type", "")
        tipos = tipo if isinstance(tipo, list) else [tipo]
        if any("Video" in str(t) for t in tipos):
            videos += 1
        for chave in ("name", "headline", "description", "keywords", "about", "articleSection"):
            valor = bloco.get(chave)
            if isinstance(valor, list):
                valor = " ".join(str(v) for v in valor)
            if valor:
                campos_jsonld.append(str(valor))

    feeds: list[str] = []
    for padrao in (ALTERNATE, ALTERNATE_INV):
        for achado in padrao.findall(html):
            if achado not in feeds:
                feeds.append(achado)

    corpo = _texto_visivel(html)
    return {
        "titulo": titulo[:200],
        "termos_no_titulo": _termos_presentes(titulo, termos),
        "termos_nos_metadados": _termos_presentes(texto_meta, termos),
        "termos_no_jsonld": _termos_presentes(" ".join(campos_jsonld), termos),
        "termos_no_corpo": _termos_presentes(corpo, termos),
        "meta_keywords": bool(metadados.get("keywords") or metadados.get("news_keywords")),
        "jsonld_blocos": len(blocos),
        "jsonld_videos": videos,
        "feeds": feeds[:20],
        "ids_youtube": sorted(set(CANAL_YT.findall(html))),
        # Um corpo quase vazio com muitos scripts e o sintoma de pagina
        # montada por JavaScript: o adaptador teria de ir a API interna.
        "bytes_html": len(html),
        "bytes_texto": len(corpo.strip()),
    }


# --------------------------------------------------------------------------
# YouTube: handle -> id de canal, sem conta nem chave
# --------------------------------------------------------------------------


def id_de_canal_youtube(html: str) -> str | None:
    """O id vem do <link rel=canonical>; sem ele, o UC... mais frequente."""
    m = CANONICO_YT.search(html)
    if m:
        return m.group(1)
    contagem = Counter(CANAL_YT.findall(html))
    return contagem.most_common(1)[0][0] if contagem else None


# --------------------------------------------------------------------------
# Corrida
# --------------------------------------------------------------------------


def _sondar(url: str, obter: Obter) -> tuple[str | None, str | None]:
    try:
        return obter(url), None
    except ErroDeRede as exc:
        return None, str(exc)


def correr(
    config: dict,
    obter: Obter = obter_texto,
    so_canal: str | None = None,
    dormir: Callable[[float], None] = time.sleep,
    escrever_a_cada_canal: Callable[[dict], None] | None = None,
) -> dict:
    tema = carregar_config()
    termos_sujeito = list(tema.sujeito.detetar)
    termos = termos_sujeito + list(config.get("termos_formato") or [])
    desde = tema.tema.desde
    pausa = float(config.get("pausa_s", 1.0))

    resultado = {
        "verificado_em": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "desde": desde,
        "termos": termos,
        "canais": [],
    }
    cache_yt: dict[str, dict] = {}

    for canal in config.get("canais") or []:
        cid = canal["id"]
        if so_canal and cid != so_canal:
            continue
        if not tema.canal_valido(cid):
            print(f"AVISO canal desconhecido em levantamento.yml: {cid}", file=sys.stderr, flush=True)
            continue
        linha = {"canal": cid, "nome": tema.canais[cid].nome, "paginas": [], "youtube": []}

        for modelo in canal.get("paginas") or []:
            urls = [modelo.format(termo=urllib.parse.quote(t)) for t in termos_sujeito] if "{termo}" in modelo else [modelo]
            for url in urls:
                print(f"  {cid}: a sondar {url}", flush=True)
                html, erro = _sondar(url, obter)
                if html is None:
                    linha["paginas"].append({"url": url, "responde": False, "erro": erro})
                    print(f"  {cid}: nao respondeu ({erro})", flush=True)
                else:
                    linha["paginas"].append({"url": url, "responde": True, **analisar_html(html, termos)})
                dormir(pausa)

        for handle in canal.get("youtube") or []:
            if handle not in cache_yt:
                print(f"  {cid}: a resolver YouTube @{handle}", flush=True)
                html, erro = _sondar(PAGINA_YT.format(handle=handle), obter)
                uc = id_de_canal_youtube(html) if html else None
                cache_yt[handle] = {"handle": handle, "channel_id": uc, "feed": FEED_YT.format(id=uc) if uc else None, "erro": erro}
                dormir(pausa)
            linha["youtube"].append(cache_yt[handle])

        resultado["canais"].append(linha)
        print(f"{cid}: {len(linha['paginas'])} paginas, {len(linha['youtube'])} handles", flush=True)
        # Escrever a cada canal, nao so no fim: se o job for morto pelo
        # timeout ou cancelado a meio, o que ja foi apurado fica em disco
        # e no artefacto, em vez de se perder por inteiro.
        if escrever_a_cada_canal is not None:
            escrever_a_cada_canal(resultado)

    return resultado


# --------------------------------------------------------------------------
# Relatorio
# --------------------------------------------------------------------------


def _sim_nao(valor: bool) -> str:
    return "sim" if valor else "nao"


def relatorio(resultado: dict) -> str:
    """Markdown com uma linha por canal. Sem travessoes, em LF."""
    linhas = [
        "# Levantamento das fontes",
        "",
        f"Verificado em {resultado['verificado_em']}.",
        "",
        "Termos procurados: " + ", ".join(resultado["termos"]) + ".",
        "",
        "Cada linha e um canal. \"Paginas\" conta as que responderam sobre as sondadas.",
        "\"Servidor\" diz se algum termo ja vem no HTML sem JavaScript (titulo, metadados, JSON-LD ou corpo).",
        "\"Videos\" e o numero de blocos JSON-LD de video, que e onde um canal declara a pagina de uma entrevista.",
        "",
        "| Canal | Paginas | Servidor | Metadados | Videos | Feeds | YouTube |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in resultado["canais"]:
        paginas = c["paginas"]
        respondem = [p for p in paginas if p.get("responde")]
        servidor = any(p.get("termos_no_titulo") or p.get("termos_nos_metadados") or p.get("termos_no_jsonld") or p.get("termos_no_corpo") for p in respondem)
        metadados = any(p.get("termos_nos_metadados") or p.get("termos_no_jsonld") for p in respondem)
        videos = sum(p.get("jsonld_videos", 0) for p in respondem)
        feeds = sum(len(p.get("feeds") or []) for p in respondem)
        ids = [y["channel_id"] for y in c["youtube"] if y.get("channel_id")]
        linhas.append(
            f"| {c['nome']} | {len(respondem)}/{len(paginas)} | {_sim_nao(servidor)} | {_sim_nao(metadados)} | {videos} | {feeds} "
            f"| {', '.join(ids) or 'nenhum'} |"
        )

    linhas += ["", "## Detalhe por canal", ""]
    for c in resultado["canais"]:
        linhas += [f"### {c['nome']}", ""]
        for p in c["paginas"]:
            if not p.get("responde"):
                linhas.append(f"- {p['url']}: nao responde ({p.get('erro')})")
                continue
            onde = [n for n, chave in (("titulo", "termos_no_titulo"), ("metadados", "termos_nos_metadados"), ("jsonld", "termos_no_jsonld"), ("corpo", "termos_no_corpo")) if p.get(chave)]
            linhas.append(
                f"- {p['url']}: termos em {', '.join(onde) or 'lado nenhum'}; JSON-LD {p['jsonld_blocos']} blocos, "
                f"{p['jsonld_videos']} videos; {len(p['feeds'])} feeds; "
                f"texto {p['bytes_texto']} de {p['bytes_html']} bytes"
            )
        for y in c["youtube"]:
            linhas.append(f"- YouTube @{y['handle']}: {y['channel_id'] or 'nao resolvido'}" + (f" ({y['erro']})" if y.get("erro") else ""))
        linhas.append("")
    return "\n".join(linhas).rstrip() + "\n"


def carregar_anterior(pasta: Path = PASTA_SAIDA) -> dict[str, dict]:
    """Canais ja escritos numa corrida anterior, por id.

    Uma corrida com --canal reprocessa um canal so; sem isto, escrever()
    substituiria o ficheiro inteiro e apagaria os outros canais que uma
    corrida mais antiga ja tinha verificado.
    """
    caminho = pasta / "levantamento.json"
    if not caminho.exists():
        return {}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {c["canal"]: c for c in dados.get("canais") or [] if "canal" in c}


def mesclar(resultado: dict, anteriores: dict[str, dict], ordem: list[str]) -> dict:
    """Combina os canais desta corrida com os de corridas anteriores.

    Um canal reprocessado agora substitui a versao anterior; um canal nao
    tocado nesta corrida mantem-se tal como estava. A ordem final segue a
    ordem dos canais em config/porquinho.yml, para o relatorio ser sempre
    lido pela mesma sequencia.
    """
    por_id = dict(anteriores)
    for c in resultado.get("canais") or []:
        por_id[c["canal"]] = c
    combinado = dict(resultado)
    combinado["canais"] = [por_id[cid] for cid in ordem if cid in por_id]
    return combinado


def escrever(resultado: dict, pasta: Path = PASTA_SAIDA) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "levantamento.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    (pasta / "LEVANTAMENTO.md").write_text(relatorio(resultado), encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--canal", help="so este canal")
    args = parser.parse_args(argv)
    config = carregar()
    anteriores = carregar_anterior()
    ordem = [c["id"] for c in config.get("canais") or []]

    resultado = correr(
        config,
        so_canal=args.canal,
        escrever_a_cada_canal=lambda parcial: escrever(mesclar(parcial, anteriores, ordem)),
    )
    escrever(mesclar(resultado, anteriores, ordem))
    print(f"escrito em {PASTA_SAIDA}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
