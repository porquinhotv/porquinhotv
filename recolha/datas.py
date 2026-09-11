"""Dia em que a entrevista passou.

A data em que um video ou episodio e publicado nao e a data em que a
entrevista foi para o ar. Diverge por horas ou dias, e a divergencia
espalha uma rubrica de dia fixo pela semana toda. Quando o texto declara
o dia em que passou, e esse que vale; quando nao declara, fica o de
publicacao, marcada como tal.

Prudencia: a data declarada so e aceite se cair entre o dia da publicacao
e 45 dias antes. Fora disso, e mais provavel ser outra data qualquer
mencionada no texto, e usa-se a de publicacao.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}

# "emitida no canal a 4 de setembro", "entrevista de 12 de maio de 2025",
# "foi para o ar dia 3 de junho". Ate 60 caracteres entre o marcador e a
# data, sem atravessar o fim da frase.
DECLARADA = re.compile(
    r"(?:emitid[oa]|exibid[oa]|transmitid[oa]|para o ar|entrevista de|entrevista realizada)"
    r"[^.;!?]{0,60}?\b(\d{1,2})\s+de\s+([a-z]+)(?:\s+de\s+(\d{4}))?",
    re.IGNORECASE,
)
ISO_NO_TEXTO = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
ATRASO_MAXIMO_DIAS = 45


def _sem_acentos(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


def _plausivel(candidata: date, publicacao: date) -> bool:
    atraso = (publicacao - candidata).days
    return 0 <= atraso <= ATRASO_MAXIMO_DIAS


def data_declarada(texto: str, publicado_iso: str) -> str | None:
    """Dia declarado no texto, em ISO, ou None."""
    if not publicado_iso:
        return None
    try:
        publicacao = date.fromisoformat(publicado_iso)
    except ValueError:
        return None

    limpo = _sem_acentos(texto)
    encontrado = DECLARADA.search(limpo)
    if encontrado:
        dia = int(encontrado.group(1))
        mes = MESES.get(encontrado.group(2).lower())
        if mes:
            anos = [int(encontrado.group(3))] if encontrado.group(3) else [publicacao.year, publicacao.year - 1]
            for ano in anos:
                try:
                    candidata = date(ano, mes, dia)
                except ValueError:
                    continue
                if _plausivel(candidata, publicacao):
                    return candidata.isoformat()

    iso = ISO_NO_TEXTO.search(limpo)
    if iso:
        try:
            candidata = date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
        if _plausivel(candidata, publicacao):
            return candidata.isoformat()
    return None


def resolver_data(texto: str, publicado_iso: str, declarada_pela_fonte: str = "") -> tuple[str, str]:
    """(data a usar, origem). Origem: "declarada" ou "publicacao".

    Uma fonte que ja conhece o dia em que passou (o registo curado) passa-o
    em `declarada_pela_fonte` e essa vale sem mais verificacao: a prova e
    o URL que acompanha a linha.
    """
    if declarada_pela_fonte:
        return declarada_pela_fonte, "declarada"
    encontrada = data_declarada(texto, publicado_iso)
    if encontrada:
        return encontrada, "declarada"
    return publicado_iso, "publicacao"
