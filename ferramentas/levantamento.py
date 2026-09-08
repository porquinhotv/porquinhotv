"""Levantamento automatico das fontes dos canais. Corre uma vez.

    python -m ferramentas.levantamento
    python -m ferramentas.levantamento --sem-arquivo      so as paginas
    python -m ferramentas.levantamento --canal <id>       so um canal

Le config/levantamento.yml e, para cada canal, sonda as paginas
declaradas, resolve os handles de YouTube para ids UC..., e pergunta ao
arquivo.pt quantas paginas de cada dominio falam do sujeito, por ano.
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
META_ATRIB = re.compile(r'(name|property|content)=["\']([^"\']*)["\']', re.IGNORECASE)
JSONLD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
ETIQUETAS = re.compile(r"<[^>]+>")
SCRIPTS = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
DURACAO_ISO = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


def carregar(caminho: Path = FICHEIRO_CONFIG) -> dict:
    return yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}


# --------------------------------------------------------------------------
# Analise de uma pagina HTML
# --------------------------------------------------------------------------


def _metadados(html: str) -> dict[str, str]:
    """name/property -> content das <meta>. Chaves em minusculas."""
    saida: dict[str, str] = {}
    for etiqueta in META.findall(html):
        pares = {k.lower(): v for k, v in META_ATRIB.findall(etiqueta)}
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


def _duracao_iso(valor: str) -> int | None:
    m = DURACAO_ISO.match(valor or "")
    if not m:
        return None
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


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
    se ha JSON-LD de video e se esse video declara duracao, os feeds
    anunciados e os ids de canal de YouTube presentes no HTML. E isto que
    decide se um adaptador pode ler a pagina tal como o servidor a envia.
    """
    titulo = html_mod.unescape(TITULO.search(html).group(1)).strip() if TITULO.search(html) else ""
    metadados = _metadados(html)
    blocos = _jsonld(html)

    texto_meta = " ".join(metadados.values())
    campos_jsonld: list[str] = []
    videos = 0
    com_duracao = 0
    for bloco in blocos:
        tipo = bloco.get("@type", "")
        tipos = tipo if isinstance(tipo, list) else [tipo]
        if any("Video" in str(t) for t in tipos):
            videos += 1
            if _duracao_iso(str(bloco.get("duration", ""))) is not None:
                com_duracao += 1
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
        "jsonld_videos_com_duracao": com_duracao,
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
# arquivo.pt: quantas paginas arquivadas por dominio, termo e ano
# --------------------------------------------------------------------------


def url_arquivo(api: str, termo: str, dominio: str, desde: str, ate: str, max_itens: int) -> str:
    parametros = {
        "q": f'"{termo}"',
        "siteSearch": dominio,
        "from": desde.replace("-", ""),
        "to": ate.replace("-", ""),
        "maxItems": str(max_itens),
        "dedupField": "url",
        "prettyPrint": "false",
    }
    return f"{api}?{urllib.parse.urlencode(parametros)}"


def ler_resposta_arquivo(texto: str) -> dict:
    """Total estimado, contagem por ano e ate cinco exemplos."""
    dados = json.loads(texto)
    itens = dados.get("response_items") or []
    por_ano: Counter = Counter()
    exemplos = []
    for item in itens:
        carimbo = str(item.get("tstamp") or "")
        if len(carimbo) >= 4:
            por_ano[carimbo[:4]] += 1
        if len(exemplos) < 5:
            exemplos.append(
                {
                    "titulo": (item.get("title") or "")[:160],
                    "url": item.get("originalURL") or "",
                    "arquivo": item.get("linkToArchive") or "",
                    "data": carimbo[:8],
                }
            )
    return {
        "total_estimado": int(dados.get("estimated_total_results") or 0),
        "itens_lidos": len(itens),
        "por_ano": dict(sorted(por_ano.items())),
        "exemplos": exemplos,
    }


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
    com_arquivo: bool = True,
    dormir: Callable[[float], None] = time.sleep,
) -> dict:
    tema = carregar_config()
    termos_sujeito = list(tema.sujeito.detetar)
    termos = termos_sujeito + list(config.get("termos_formato") or [])
    arquivo = config.get("arquivo") or {}
    desde = tema.tema.desde
    ate = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pausa = float(arquivo.get("pausa_s", 1.0))

    resultado = {
        "verificado_em": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "desde": desde,
        "termos": termos,
        "canais": [],
    }
    cache_arquivo: dict[tuple[str, str], dict] = {}
    cache_yt: dict[str, dict] = {}

    for canal in config.get("canais") or []:
        cid = canal["id"]
        if so_canal and cid != so_canal:
            continue
        if not tema.canal_valido(cid):
            print(f"AVISO canal desconhecido em levantamento.yml: {cid}", file=sys.stderr, flush=True)
            continue
        linha = {"canal": cid, "nome": tema.canais[cid].nome, "paginas": [], "youtube": [], "arquivo": {}}

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

        if com_arquivo and arquivo.get("api"):
            extras = list(arquivo.get("termos_extra") or [])
            for dominio in canal.get("dominios") or []:
                consultas = termos_sujeito + [f"{s} {e}" for s in termos_sujeito for e in extras]
                por_termo = {}
                for consulta in consultas:
                    chave = (dominio, consulta)
                    if chave not in cache_arquivo:
                        print(f"  {cid}: arquivo.pt {dominio} \"{consulta}\"", flush=True)
                        url = url_arquivo(arquivo["api"], consulta, dominio, desde, ate, int(arquivo.get("max_itens", 200)))
                        texto, erro = _sondar(url, obter)
                        if texto is None:
                            cache_arquivo[chave] = {"erro": erro}
                            print(f"  {cid}: arquivo.pt {dominio} falhou ({erro})", flush=True)
                        else:
                            try:
                                cache_arquivo[chave] = ler_resposta_arquivo(texto)
                            except (json.JSONDecodeError, ValueError) as exc:
                                cache_arquivo[chave] = {"erro": f"resposta ilegivel: {exc}"}
                        dormir(pausa)
                    por_termo[consulta] = cache_arquivo[chave]
                linha["arquivo"][dominio] = por_termo

        resultado["canais"].append(linha)
        print(f"{cid}: {len(linha['paginas'])} paginas, {len(linha['youtube'])} handles, {len(linha['arquivo'])} dominios", flush=True)

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
        f"Verificado em {resultado['verificado_em']}. Periodo pedido ao arquivo.pt: desde {resultado['desde']}.",
        "",
        "Termos procurados: " + ", ".join(resultado["termos"]) + ".",
        "",
        "Cada linha e um canal. \"Paginas\" conta as que responderam sobre as sondadas.",
        "\"Servidor\" diz se algum termo ja vem no HTML sem JavaScript (titulo, metadados, JSON-LD ou corpo).",
        "\"Video com duracao\" e o numero de blocos JSON-LD de video com duration declarada.",
        "\"arquivo.pt\" e o total estimado, somado por dominio, para o termo mais produtivo.",
        "",
        "| Canal | Paginas | Servidor | Metadados | Video com duracao | Feeds | YouTube | arquivo.pt | Anos com resultados |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in resultado["canais"]:
        paginas = c["paginas"]
        respondem = [p for p in paginas if p.get("responde")]
        servidor = any(p.get("termos_no_titulo") or p.get("termos_nos_metadados") or p.get("termos_no_jsonld") or p.get("termos_no_corpo") for p in respondem)
        metadados = any(p.get("termos_nos_metadados") or p.get("termos_no_jsonld") for p in respondem)
        videos = sum(p.get("jsonld_videos_com_duracao", 0) for p in respondem)
        feeds = sum(len(p.get("feeds") or []) for p in respondem)
        ids = [y["channel_id"] for y in c["youtube"] if y.get("channel_id")]
        total = 0
        anos: Counter = Counter()
        for por_termo in c["arquivo"].values():
            melhor = max((r for r in por_termo.values() if "erro" not in r), key=lambda r: r["total_estimado"], default=None)
            if melhor:
                total += melhor["total_estimado"]
                anos.update(melhor["por_ano"])
        anos_txt = ", ".join(f"{a} ({n})" for a, n in sorted(anos.items())) or "nenhum"
        linhas.append(
            f"| {c['nome']} | {len(respondem)}/{len(paginas)} | {_sim_nao(servidor)} | {_sim_nao(metadados)} | {videos} | {feeds} "
            f"| {', '.join(ids) or 'nenhum'} | {total} | {anos_txt} |"
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
                f"{p['jsonld_videos']} videos, {p['jsonld_videos_com_duracao']} com duracao; {len(p['feeds'])} feeds; "
                f"texto {p['bytes_texto']} de {p['bytes_html']} bytes"
            )
        for y in c["youtube"]:
            linhas.append(f"- YouTube @{y['handle']}: {y['channel_id'] or 'nao resolvido'}" + (f" ({y['erro']})" if y.get("erro") else ""))
        for dominio, por_termo in c["arquivo"].items():
            for consulta, r in por_termo.items():
                if "erro" in r:
                    linhas.append(f"- arquivo.pt {dominio} \"{consulta}\": erro ({r['erro']})")
                else:
                    linhas.append(f"- arquivo.pt {dominio} \"{consulta}\": {r['total_estimado']} estimados; por ano {r['por_ano'] or 'nenhum'}")
        linhas.append("")
    return "\n".join(linhas).rstrip() + "\n"


def escrever(resultado: dict, pasta: Path = PASTA_SAIDA) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "levantamento.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    (pasta / "LEVANTAMENTO.md").write_text(relatorio(resultado), encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--canal", help="so este canal")
    parser.add_argument("--sem-arquivo", action="store_true", help="nao consultar o arquivo.pt")
    args = parser.parse_args(argv)
    resultado = correr(carregar(), so_canal=args.canal, com_arquivo=not args.sem_arquivo)
    escrever(resultado)
    print(f"escrito em {PASTA_SAIDA}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
