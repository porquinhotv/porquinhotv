"""Feeds RSS de podcast.

Trazem data de publicacao (`pubDate`) sem scraping. A duracao que o
feed declara (`itunes:duration`) e ignorada desde 2026-09-10: o projeto
conta existencias, nao tempo. Seguem paginacao Atom
(`<atom:link rel="next">`) quando o feed a expoe; verificar sempre no
feed concreto com --dry-run em vez de assumir limites de documentacao.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Iterable

from ..modelos import ItemBruto
from ..rede import obter_texto
from .base import PluginDeFonte, registar

ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
ATOM = "{http://www.w3.org/2005/Atom}"
MAX_PAGINAS = 20


def data_rfc822(valor: str | None) -> str:
    if not valor:
        return ""
    try:
        momento = parsedate_to_datetime(valor)
    except (TypeError, ValueError):
        return ""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc).date().isoformat()


def _texto(no, etiqueta: str) -> str:
    achado = no.find(etiqueta)
    return (achado.text or "").strip() if achado is not None and achado.text else ""


def sem_html(valor: str) -> str:
    return re.sub(r"<[^>]+>", " ", valor)


def _pagina_seguinte(raiz: ET.Element) -> str | None:
    canal = raiz.find("channel")
    if canal is None:
        return None
    for ligacao in canal.findall(f"{ATOM}link"):
        if ligacao.get("rel") == "next":
            return ligacao.get("href") or None
    return None


def ler_feed(xml: str) -> tuple[list[ItemBruto], str | None]:
    """Itens de uma pagina do feed e o URL da pagina seguinte, se houver."""
    raiz = ET.fromstring(xml)
    itens: list[ItemBruto] = []
    for item in raiz.iter("item"):
        guid = _texto(item, "guid") or _texto(item, "link")
        publicado = data_rfc822(_texto(item, "pubDate"))
        if not guid or not publicado:
            # Sem data nao ha emissao. Fica de fora aqui, antes do
            # criterio, porque nem sequer e um candidato.
            continue
        itens.append(
            ItemBruto(
                id_nativo=guid,
                publicado_em=publicado,
                titulo=_texto(item, "title"),
                url=_texto(item, "link"),
                descricao=sem_html(_texto(item, "description") or _texto(item, f"{ITUNES}summary")),
                prova_url=_texto(item, "link"),
            )
        )
    return itens, _pagina_seguinte(raiz)


@registar
class FontePodcastRss(PluginDeFonte):
    tipo = "podcast_rss"

    def obter(self, termos: list[str] | None = None, registo: list | None = None) -> Iterable[ItemBruto]:
        if not self.fonte.url:
            return []
        vistos: set[str] = set()
        todos: list[ItemBruto] = []
        url = self.fonte.url
        for _ in range(MAX_PAGINAS):
            itens, seguinte = ler_feed(obter_texto(url))
            novos = [i for i in itens if i.id_nativo not in vistos]
            for item in novos:
                vistos.add(item.id_nativo)
                item.canal = self.fonte.canal
                item.programa = self.fonte.programa
            todos.extend(novos)
            if not seguinte or not novos:
                break
            url = seguinte
        return todos
