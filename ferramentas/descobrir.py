"""Levantamento de fontes. Correr a mao, uma vez por canal ou programa.

    python -m ferramentas.descobrir https://www.canal.pt/programa/
    python -m ferramentas.descobrir https://exemplo.pt/feed.rss
    python -m ferramentas.descobrir UCxxxxxxxxxxxxxxxxxxxxxx

Dado o URL de uma pagina: lista os feeds RSS/Atom anunciados na pagina
(<link rel="alternate">), os links que parecem feeds, e os ids de canal
de YouTube (UC...) que aparecem no HTML.

Dado o URL de um feed: le a primeira pagina e resume, itens, intervalo de
datas, se tem duracoes, se pagina, e os dez titulos mais recentes. E com
isto que se verifica um feed antes de o configurar, em vez de assumir.

Dado um id de canal de YouTube: le o feed publico e mostra os titulos.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET

from recolha.fontes import podcast_rss, youtube_feed
from recolha.rede import obter_texto

ALTERNATE = re.compile(
    r'<link[^>]+rel=["\']alternate["\'][^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
ALTERNATE_INV = re.compile(
    r'<link[^>]+href=["\']([^"\']+)["\'][^>]+type=["\']application/(?:rss|atom)\+xml["\']',
    re.IGNORECASE,
)
PARECE_FEED = re.compile(r'https?://[^"\'\s<>]+?(?:\.rss|/rss|/feed|feed\.xml|\.xml)(?:[?#][^"\'\s<>]*)?', re.IGNORECASE)
CANAL_YT = re.compile(r"\b(UC[0-9A-Za-z_-]{22})\b")


def analisar_pagina(url: str) -> None:
    html = obter_texto(url)
    feeds: list[str] = []
    for padrao in (ALTERNATE, ALTERNATE_INV, PARECE_FEED):
        for achado in padrao.findall(html):
            if achado not in feeds:
                feeds.append(achado)
    canais = sorted(set(CANAL_YT.findall(html)))
    print(f"pagina: {url}")
    print(f"feeds anunciados ou prováveis: {len(feeds)}")
    for f in feeds[:30]:
        print(f"  {f}")
    print(f"ids de canal YouTube no HTML: {len(canais)}")
    for c in canais:
        print(f"  {c}  ->  https://www.youtube.com/feeds/videos.xml?channel_id={c}")
    if not feeds and not canais:
        print("  nada encontrado; a pagina pode carregar tudo por JavaScript")


def analisar_feed(url: str) -> None:
    xml = obter_texto(url)
    itens, seguinte = podcast_rss.ler_feed(xml)
    if not itens:
        # Talvez seja Atom (YouTube).
        try:
            entradas = youtube_feed.ler_feed(xml)
        except ET.ParseError:
            entradas = []
        if entradas:
            print(f"feed Atom: {url}")
            print(f"itens: {len(entradas)} (sem duracao, o feed nao a expoe)")
            for e in entradas[:10]:
                print(f"  {e.publicado_em}  {e.titulo}")
            return
        print("sem itens legiveis, ou sem duracao e data em todos os itens")
        return
    datas = sorted(i.publicado_em for i in itens)
    duracoes = [i.duracao_s for i in itens if i.duracao_s]
    print(f"feed: {url}")
    print(f"itens nesta pagina: {len(itens)}")
    print(f"datas: {datas[0]} a {datas[-1]}")
    if duracoes:
        print(f"duracoes: {min(duracoes)//60} a {max(duracoes)//60} minutos")
    print(f"pagina seguinte: {'sim, ' + seguinte if seguinte else 'nao'}")
    print("titulos mais recentes:")
    for i in sorted(itens, key=lambda x: x.publicado_em, reverse=True)[:10]:
        print(f"  {i.publicado_em}  {i.duracao_s//60:>3} min  {i.titulo}")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    alvo = argv[0]
    if CANAL_YT.fullmatch(alvo):
        analisar_feed(youtube_feed.FEED.format(id=alvo))
    elif re.search(r"\.(rss|xml)(\?|$)|/feed(/|\?|$)|feeds/videos", alvo):
        analisar_feed(alvo)
    else:
        analisar_pagina(alvo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
