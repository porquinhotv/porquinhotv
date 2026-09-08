"""Feed Atom publico de um canal de YouTube. Sem conta, sem chave.

    https://www.youtube.com/feeds/videos.xml?channel_id=UC...

Devolve os ultimos 15 videos com titulo, data de publicacao e descricao.
Nao devolve duracao. Por isso estes itens nunca entram no dataset por
esta via: o criterio manda-os para a quarentena como `por_confirmar`, com
o URL, e a duracao e confirmada a mao no registo curado, onde cada linha
leva prova. E um detetor, nao um medidor.
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
                duracao_s=None,
                descricao=descricao or "",
                prova_url=url,
            )
        )
    return itens


@registar
class FonteYouTubeFeed(PluginDeFonte):
    tipo = "youtube_feed"

    def obter(self) -> Iterable[ItemBruto]:
        if not self.fonte.channel_id:
            return []
        itens = ler_feed(obter_texto(FEED.format(id=self.fonte.channel_id)))
        for item in itens:
            item.canal = self.fonte.canal
            item.programa = self.fonte.programa
        return itens
