"""Extracao generica de dados estruturados de uma pagina HTML.

Nenhum seletor CSS de nenhum site. Le apenas o que os sites publicam em
formatos normalizados, porque e isso que sobrevive a uma remodelacao do
site:

    JSON-LD          <script type="application/ld+json">, schema.org
    OpenGraph        <meta property="og:...">
    Dublin Core      <meta name="article:published_time"> e afins
    itemprop         <meta itemprop="duration">, microdados
    <time datetime>  data legivel por maquina no corpo

Um adaptador escrito contra a estrutura HTML de um canal parte na
primeira remodelacao do site e passa a devolver zero em silencio. Um
extrator que le schema.org continua a funcionar, porque os sites mantem
esses campos para os motores de busca e para as redes sociais. E a
diferenca entre uma recolha que se mantem sozinha e uma que exige
manutencao a cada mes.

Devolve sempre o que conseguiu apurar e nunca inventa: uma data que nao
existe fica vazia. Quem decide o que fazer com isso e
recolha/criterio.py. A duracao deixou de ser lida a 2026-09-10: o
projeto conta existencias e nao tempo, e um campo que ninguem usa e um
campo que ninguem verifica.
"""

from __future__ import annotations

import html as html_mod
import json
import re
import unicodedata
from datetime import datetime

ETIQUETAS = re.compile(r"<[^>]+>")
SCRIPTS = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
JSONLD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
META = re.compile(r"<meta\s[^>]*>", re.IGNORECASE)
# O valor fecha com a mesma aspa que o abriu. Com uma classe que parava em
# qualquer das duas, `content="esteve no 'Grande Programa' do canal"` ficava
# em "esteve no", e a palavra que provava o formato caia fora sem aviso.
META_ATRIB = re.compile(r'(name|property|itemprop|content)=(["\'])(.*?)\2', re.IGNORECASE | re.DOTALL)
TITULO = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
TEMPO = re.compile(r'<time[^>]+datetime=["\']([^"\']+)["\']', re.IGNORECASE)
LIGACAO = re.compile(r'<a\s[^>]*href=["\']([^"\'#]+)["\']', re.IGNORECASE)

CAMPOS_DATA = (
    "article:published_time",
    "og:published_time",
    "datepublished",
    "date",
    "dc.date",
    "dcterms.created",
    "pubdate",
    "sailthru.date",
)
CAMPOS_DESCRICAO = ("og:description", "description", "twitter:description")
# Etiquetas e sinopses. Um canal marca a peca com o nome do convidado
# muitas vezes sem o escrever no titulo: sem ler isto, a entrevista era
# rejeitada por `sem_sujeito` quando a propria pagina a identificava.
CAMPOS_ETIQUETAS = (
    "keywords",
    "news_keywords",
    "article:tag",
    "article:section",
    "og:article:tag",
    "tags",
    "subject",
)
CAMPOS_TITULO = ("og:title", "twitter:title", "title")


# Meses em portugues, pelas tres primeiras letras e sem acentos, que e
# como um site abrevia uma data escrita para pessoas ("24 jun 2026", "24
# de junho de 2026"). Nao e configuracao editorial: e a lingua em que os
# sitios escrevem, e nao nomeia canal, programa nem pessoa nenhuma.
MESES_ABREVIADOS = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
# Dia, mes por palavra e ano, com "de" opcional dos dois lados e ponto
# opcional na abreviatura. Exige os tres campos de proposito: sem o dia,
# "Eleicoes 2024" numa lista de etiquetas passaria por data.
DATA_POR_EXTENSO = re.compile(r"\b(\d{1,2})\s*(?:de\s+)?([^\W\d_]{3,9})\.?\s*(?:de\s+)?(\d{4})\b", re.IGNORECASE)


def _sem_acentos(texto: str) -> str:
    """Minusculas sem acentos. Aqui e nao em modelos.py para nao criar uma
    dependencia circular entre a extracao e a configuracao."""
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()


def data_para_iso(valor) -> str:
    """AAAA-MM-DD a partir das formas que os sites publicam. Vazio se nao."""
    if not valor:
        return ""
    texto = str(valor).strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", texto)
    if m:
        return m.group(0)
    # 15/03/2021 e 15-03-2021, comuns em sites portugueses.
    m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", texto)
    if m:
        dia, mes, ano = m.groups()
        try:
            return datetime(int(ano), int(mes), int(dia)).strftime("%Y-%m-%d")
        except ValueError:
            return ""
    # Data escrita por extenso. Procura-se em qualquer sitio do valor,
    # ao contrario das formas numericas acima, porque esta aparece no
    # meio de uma lista de etiquetas e nao sozinha num campo proprio.
    for dia, mes, ano in DATA_POR_EXTENSO.findall(texto):
        chave = _sem_acentos(mes)[:3]
        if chave in MESES_ABREVIADOS:
            try:
                return datetime(int(ano), MESES_ABREVIADOS.index(chave) + 1, int(dia)).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return ""


def metadados(html: str) -> dict[str, str]:
    """name, property ou itemprop -> content, com chaves em minusculas."""
    saida: dict[str, str] = {}
    for etiqueta in META.findall(html):
        pares = {k.lower(): v for k, _, v in META_ATRIB.findall(etiqueta)}
        chave = pares.get("property") or pares.get("name") or pares.get("itemprop")
        conteudo = pares.get("content")
        if chave and conteudo:
            saida.setdefault(chave.lower(), html_mod.unescape(conteudo))
    return saida


def blocos_jsonld(html: str) -> list[dict]:
    """Todos os objectos JSON-LD da pagina, incluindo os de dentro de @graph."""
    blocos: list[dict] = []
    for bruto in JSONLD.findall(html):
        try:
            dados = json.loads(bruto.strip())
        except json.JSONDecodeError:
            continue
        pilha = dados if isinstance(dados, list) else [dados]
        vistos = 0
        while pilha and vistos < 200:
            vistos += 1
            d = pilha.pop()
            if isinstance(d, list):
                pilha.extend(d)
                continue
            if not isinstance(d, dict):
                continue
            blocos.append(d)
            for chave in ("@graph", "video", "hasPart", "mainEntity", "itemListElement"):
                filho = d.get(chave)
                if isinstance(filho, (list, dict)):
                    pilha.append(filho) if isinstance(filho, dict) else pilha.extend(filho)
    return blocos


def _tipos(bloco: dict) -> list[str]:
    tipo = bloco.get("@type", "")
    return [str(t).lower() for t in (tipo if isinstance(tipo, list) else [tipo])]


def texto_visivel(html: str) -> str:
    return " ".join(html_mod.unescape(ETIQUETAS.sub(" ", SCRIPTS.sub(" ", html))).split())


def extrair(html: str, url: str = "") -> dict:
    """Titulo, descricao, data e etiquetas de uma pagina, se existirem.

    A ordem de preferencia e sempre a mesma: JSON-LD primeiro, porque e o
    campo declarado para maquinas; depois os metadados; so depois o que se
    consegue ler do corpo. Um campo que nenhuma dessas camadas declare fica
    por apurar, e nao e adivinhado a partir do texto.
    """
    metas = metadados(html)
    blocos = blocos_jsonld(html)

    titulo = ""
    descricao = ""
    data = ""
    e_video = False
    etiquetas: list[str] = []

    for bloco in blocos:
        tipos = _tipos(bloco)
        if any("video" in t for t in tipos):
            e_video = True
        if any(t in ("newsarticle", "article", "videoobject", "tvepisode", "webpage", "mediaobject") for t in tipos) or e_video:
            titulo = titulo or str(bloco.get("name") or bloco.get("headline") or "")
            descricao = descricao or str(bloco.get("description") or "")
            data = data or data_para_iso(bloco.get("datePublished") or bloco.get("uploadDate") or bloco.get("dateCreated"))
        for chave in ("keywords", "about", "articleSection", "genre", "alternateName"):
            valor = bloco.get(chave)
            if isinstance(valor, dict):
                valor = valor.get("name")
            if isinstance(valor, list):
                valor = " ".join(str(v.get("name") if isinstance(v, dict) else v) for v in valor)
            if valor:
                etiquetas.append(str(valor))

    for campo in CAMPOS_TITULO:
        if not titulo and metas.get(campo):
            titulo = metas[campo]
    for campo in CAMPOS_DESCRICAO:
        if not descricao and metas.get(campo):
            descricao = metas[campo]
    for campo in CAMPOS_DATA:
        if not data and metas.get(campo):
            data = data_para_iso(metas[campo])
    for campo in CAMPOS_ETIQUETAS:
        if metas.get(campo):
            etiquetas.append(metas[campo])

    if not titulo:
        m = TITULO.search(html)
        titulo = html_mod.unescape(m.group(1)).strip() if m else ""
    if not data:
        for bruto in TEMPO.findall(html):
            data = data_para_iso(bruto)
            if data:
                break
    if not data:
        # Ultimo recurso, e so depois de tudo o que e declarado como data
        # ter falhado: o dia escrito no meio das etiquetas. Um leitor de
        # um canal publica paginas de episodio sem schema.org e sem campo
        # de data nenhum, com o dia so na lista de palavras-chave. Sem
        # isto, 194 episodios de um programa de entrevistas foram para a
        # quarentena como `sem_data` a 2026-09-10, todos lidos e todos com
        # duracao apurada.
        for etiqueta in etiquetas:
            data = data_para_iso(etiqueta)
            if data:
                break

    return {
        "url": url,
        "titulo": " ".join(titulo.split())[:300],
        "descricao": " ".join(descricao.split())[:1000],
        "publicado_em": data,
        "etiquetas": " ".join(dict.fromkeys(" ".join(etiquetas).split()))[:600],
        "e_video": e_video,
        # Guardado para a quarentena poder mostrar contexto de uma
        # rejeicao sem obrigar a reabrir a pagina.
        "excerto": texto_visivel(html)[:400],
    }


def _desembrulhar(url: str) -> str:
    """Endereco real de dentro de um redireccionamento, quando existe.

    Ha paginas que nao ligam directamente ao destino: poem o endereco
    verdadeiro num parametro do seu proprio URL de saida. Sem desfazer
    isso, uma pagina cheia de resultados uteis parece nao ter nenhum,
    porque nenhuma ligacao pertence ao dominio que se procura.

    Generico de proposito: qualquer parametro cujo valor seja um endereco
    http serve, sem nomear nenhum servico.
    """
    from urllib.parse import parse_qs, urlparse

    partes = urlparse(url)
    if not partes.query:
        return url
    for valores in parse_qs(partes.query).values():
        for valor in valores:
            if valor.startswith(("http://", "https://")):
                return valor
    return url


def ligacoes(html: str, base: str, dominio: str, padrao: str = "") -> list[str]:
    """URLs candidatos a artigo, do mesmo dominio, pela ordem da pagina.

    Recolhe todos os href, resolve os relativos contra `base` e mantem os
    que ficam no dominio. `padrao` e uma expressao regular opcional para
    apertar; sem ela usa-se a heuristica de um caminho com pelo menos dois
    segmentos e um slug com hifen, que e a forma de praticamente todos os
    URL de artigo e exclui a navegacao.
    """
    from urllib.parse import parse_qs, urljoin, urlparse

    compilado = re.compile(padrao) if padrao else None
    saida: list[str] = []
    vistos: set[str] = set()
    for bruto in LIGACAO.findall(html):
        alvo = html_mod.unescape(bruto).strip()
        if alvo.startswith(("mailto:", "tel:", "javascript:")):
            continue
        completo = _desembrulhar(urljoin(base, alvo))
        partes = urlparse(completo)
        if partes.scheme not in ("http", "https"):
            continue
        if not (partes.netloc == dominio or partes.netloc.endswith("." + dominio)):
            continue
        limpo = completo.split("#")[0].rstrip("/")
        if limpo in vistos:
            continue
        if compilado is not None:
            if not compilado.search(limpo):
                continue
        else:
            segmentos = [s for s in partes.path.split("/") if s]
            if len(segmentos) < 2 or "-" not in segmentos[-1]:
                continue
        vistos.add(limpo)
        saida.append(limpo)
    return saida
