"""Feed Atom publico de um canal de YouTube. Sem conta, sem chave.

    https://www.youtube.com/feeds/videos.xml?channel_id=UC...

Devolve os ultimos 15 videos com titulo, data de publicacao e descricao.
Os itens passam pelo criterio como qualquer fonte automatica: precisam de
prova positiva de formato no titulo e de serem vistos em rondas
distintas. Ate 2026-09-10 ficavam sempre na quarentena por nao trazerem
duracao; sem duracao no projeto, um video que o canal titula como
entrevista e prova de que ela passou.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Iterable

from ..modelos import ItemBruto
from ..rede import obter_texto
from .base import PluginDeFonte, registar

ATOM = "{http://www.w3.org/2005/Atom}"
YT = "{http://www.youtube.com/xml/schemas/2015}"
MEDIA = "{http://search.yahoo.com/mrss/}"
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={id}"


def ler_feed(xml: str) -> list[ItemBruto]:
    raiz = ET.fromstring(xml)
    itens: list[ItemBruto] = []
    for entrada in raiz.findall(f"{ATOM}entry"):
        video = entrada.findtext(f"{YT}videoId") or ""
        publicado = (entrada.findtext(f"{ATOM}published") or "")[:10]
        if not video or not publicado:
            continue
        grupo = entrada.find(f"{MEDIA}group")
        descricao = grupo.findtext(f"{MEDIA}description") if grupo is not None else ""
        url = f"https://www.youtube.com/watch?v={video}"
        itens.append(
            ItemBruto(
                id_nativo=video,
                publicado_em=publicado,
                titulo=entrada.findtext(f"{ATOM}title") or "",
                url=url,
                descricao=descricao or "",
                prova_url=url,
            )
        )
    return itens


@registar
class FonteYouTubeFeed(PluginDeFonte):
    tipo = "youtube_feed"

    def obter(self, termos: list[str] | None = None, registo: list | None = None) -> Iterable[ItemBruto]:
        if not self.fonte.channel_id:
            return []
        itens = ler_feed(obter_texto(FEED.format(id=self.fonte.channel_id)))
        for item in itens:
            item.canal = self.fonte.canal
            item.programa = self.fonte.programa
        return itens
