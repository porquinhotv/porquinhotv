"""Configuracao e modelo de dados.

Toda a decisao editorial vive em YAML. Nenhum modulo Python conhece o nome
de um canal, de um programa ou de uma pessoa: se conhecer, e um bug.

Ficheiros de configuracao:

    config/porquinho.yml    tema, sujeito, canais, criterio de inclusao
    config/fontes.yml       de onde vem a informacao e como e classificada
    config/entrevistas.yml  registo curado, uma linha por emissao, com prova
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
CONFIG_DIR = RAIZ / "config"
FICHEIRO_TEMA = CONFIG_DIR / "porquinho.yml"
FICHEIRO_FONTES = CONFIG_DIR / "fontes.yml"
FICHEIRO_ENTREVISTAS = CONFIG_DIR / "entrevistas.yml"
# Os dados publicam-se dentro do site: quem contesta um numero descarrega
# o dataset no mesmo sitio onde viu o numero.
DADOS_DIR = RAIZ / "docs" / "dados"

FORMATO_ELEGIVEL = "entrevista"


def normalizar(texto: str) -> str:
    """Minusculas, sem acentos, sem pontuacao. Para comparar palavras."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()


def contem_palavra(texto: str, termos: tuple[str, ...]) -> str | None:
    """Devolve o primeiro termo presente no texto, por palavra inteira."""
    palheiro = normalizar(texto)
    for termo in termos:
        padrao = rf"\b{re.escape(normalizar(termo))}\b"
        if re.search(padrao, palheiro):
            return termo
    return None


@dataclass(frozen=True)
class Tema:
    id: str
    nome: str
    pergunta: str
    desde: str
    desde_rotulo: str = "desde sempre"
    # Rondas distintas em que um bloco tem de ser visto antes de entrar
    # no dataset publicado. Ver recolha/confirmacao.py.
    rondas_para_confirmar: int = 2


@dataclass(frozen=True)
class Sujeito:
    id: str
    nome: str
    detetar: tuple[str, ...] = ()

    def aparece_em(self, texto: str) -> bool:
        return contem_palavra(texto, self.detetar) is not None


@dataclass(frozen=True)
class Canal:
    id: str
    nome: str


@dataclass(frozen=True)
class Segmento:
    """Classifica um item de uma fonte que mistura programas.

    As regras sao tentadas por ordem; a primeira que corresponder decide o
    programa, o canal e o formato. Uma regra sem `se_titulo_tem` e o
    catch-all e deve ser a ultima.
    """

    se_titulo_tem: tuple[str, ...] = ()
    programa: str = ""
    canal: str = ""
    formato: str = FORMATO_ELEGIVEL

    def corresponde(self, texto: str) -> bool:
        if not self.se_titulo_tem:
            return True
        return contem_palavra(texto, self.se_titulo_tem) is not None


@dataclass(frozen=True)
class Fonte:
    id: str
    tipo: str
    ativa: bool = True
    url: str = ""
    canal: str = ""
    programa: str = ""
    formato: str = FORMATO_ELEGIVEL
    confianca: str = "media"
    ficheiro: str = ""
    channel_id: str = ""
    # De onde vem a informacao: "canal" quando e o proprio canal a
    # publicar, "imprensa" quando e clipping de imprensa escrita. So muda
    # o que o site mostra ao lado de cada linha, nunca o que conta.
    origem: str = "canal"
    # Uma fonte com duracao_opcional pode registar uma emissao sem
    # duracao apurada: o evento conta, o tempo nao. So faz sentido em
    # fontes verificadas por uma pessoa, com prova. Numa fonte automatica
    # a falta de duracao significa "ainda nao verificado", nao "sem
    # duracao", e por isso vai para a quarentena.
    duracao_opcional: bool = False
    # Uma fonte que so publica recortes marca tudo como parcial. O numero
    # publicado passa a ser um limite inferior declarado, nao uma adivinha.
    assumir_parcial: bool = False
    # Fonte do tipo busca_site: modelos de URL da pesquisa do proprio
    # site, com {termo} e opcionalmente {pagina}; dominio a que os
    # candidatos tem de pertencer; expressao regular opcional para
    # apertar o que conta como URL de artigo; e dois limites que evitam
    # que uma pesquisa mal apertada gere milhares de pedidos.
    busca: tuple[str, ...] = ()
    # Substitui os termos de deteccao do sujeito na construcao das
    # consultas desta fonte. Vazio usa os do sujeito.
    termos_busca: tuple[str, ...] = ()
    dominio: str = ""
    padrao_artigo: str = ""
    max_candidatos: int = 40
    paginas_max: int = 1
    # Segundos de espera entre pedidos desta fonte. Um motor de busca
    # externo responde 429 a um ritmo que o site de um canal aceita sem
    # se queixar, por isso o valor e por fonte e nao global.
    pausa_s: float = 0.5
    segmentos: tuple[Segmento, ...] = ()


@dataclass(frozen=True)
class Config:
    tema: Tema
    sujeito: Sujeito
    canais: dict[str, Canal]
    exclusoes: dict[str, tuple[str, ...]]
    separadores_programa: tuple[str, ...] = ()
    fontes: tuple[Fonte, ...] = ()

    def canal_valido(self, canal_id: str) -> bool:
        return canal_id in self.canais


@dataclass
class ItemBruto:
    """O que uma fonte devolve antes de qualquer decisao editorial.

    duracao_s a None significa que a fonte nao a conhece. O que acontece
    a seguir depende da fonte: numa fonte verificada a mao (registo
    curado, clipping) a emissao entra com duracao por apurar; numa fonte
    automatica vai para a quarentena como `por_confirmar`.
    """

    id_nativo: str
    publicado_em: str
    titulo: str
    url: str
    duracao_s: int | None = None
    descricao: str = ""
    canal: str = ""
    programa: str = ""
    data_declarada: str = ""
    parcial: bool = False
    mesma_entrevista: str = ""
    prova_url: str = ""
    origem: str = ""
    # Etiquetas, tags e seccao declaradas pela pagina. Um canal marca a
    # peca com o nome do convidado sem o escrever sempre no titulo.
    etiquetas: str = ""


@dataclass
class Emissao:
    """Uma entrevista exclusiva emitida num canal, num dia.

    A unidade e a emissao, nao a entrevista: a mesma entrevista emitida em
    dois canais sao duas emissoes, e a Metodologia diz isso por palavras.
    `entrevista` agrupa emissoes da mesma entrevista para que o site possa
    tambem contar entrevistas distintas.

    duracao_s a None quer dizer que a entrevista aconteceu e esta provada,
    mas que a duracao nao foi possivel apurar. Conta como evento e nunca
    como tempo. O site diz isso por palavras em vez de inventar um numero.
    """

    id: str
    bloco: str
    entrevista: str
    data: str
    data_origem: str
    publicado_em: str
    canal: str
    programa: str
    duracao_s: int | None
    parcial: bool
    origem: str
    fonte: str
    confianca: str
    prova_url: str
    titulo: str
    primeira_vez: str = ""
    # Preenchidos por recolha/confirmacao.py. Publicados ao lado de cada
    # linha: rondas mede a estabilidade da leitura, fontes_distintas mede
    # a corroboracao. Sao coisas diferentes e o site nao as confunde.
    rondas: int = 0
    fontes_distintas: int = 0

    def como_dict(self) -> dict:
        return asdict(self)


def _ler_yaml(caminho: Path) -> dict:
    return yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}


def carregar_config(
    tema_path: Path = FICHEIRO_TEMA, fontes_path: Path = FICHEIRO_FONTES
) -> Config:
    bruto = _ler_yaml(tema_path)
    t = bruto["tema"]
    s = bruto["sujeito"]
    tema = Tema(
        id=t["id"],
        nome=t["nome"],
        pergunta=t.get("pergunta", ""),
        desde=str(t["desde"]),
        desde_rotulo=t.get("desde_rotulo", "desde sempre"),
        rondas_para_confirmar=int(t.get("rondas_para_confirmar", 2)),
    )
    sujeito = Sujeito(id=s["id"], nome=s["nome"], detetar=tuple(s.get("detetar", [])))
    canais = {c["id"]: Canal(id=c["id"], nome=c["nome"]) for c in bruto.get("canais", [])}
    exclusoes = {
        motivo: tuple(termos or []) for motivo, termos in (bruto.get("exclusoes") or {}).items()
    }

    fontes_bruto = _ler_yaml(fontes_path).get("fontes", []) if fontes_path.exists() else []
    fontes = tuple(
        Fonte(
            id=f["id"],
            tipo=f["tipo"],
            ativa=f.get("ativa", True),
            url=f.get("url", ""),
            canal=f.get("canal", ""),
            programa=f.get("programa", ""),
            formato=f.get("formato", FORMATO_ELEGIVEL),
            confianca=f.get("confianca", "media"),
            ficheiro=f.get("ficheiro", ""),
            channel_id=f.get("channel_id", ""),
            origem=f.get("origem", "canal"),
            duracao_opcional=bool(f.get("duracao_opcional", False)),
            assumir_parcial=bool(f.get("assumir_parcial", False)),
            busca=tuple(f.get("busca", []) or []),
            termos_busca=tuple(f.get("termos_busca", []) or []),
            dominio=f.get("dominio", ""),
            padrao_artigo=f.get("padrao_artigo", ""),
            max_candidatos=int(f.get("max_candidatos", 40)),
            paginas_max=int(f.get("paginas_max", 1)),
            pausa_s=float(f.get("pausa_s", 0.5)),
            segmentos=tuple(
                Segmento(
                    se_titulo_tem=tuple(r.get("se_titulo_tem", []) or []),
                    programa=r.get("programa", ""),
                    canal=r.get("canal", ""),
                    formato=r.get("formato", FORMATO_ELEGIVEL),
                )
                for r in f.get("segmentos", [])
            ),
        )
        for f in fontes_bruto
    )

    for fonte in fontes:
        for canal_id in [fonte.canal] + [seg.canal for seg in fonte.segmentos]:
            if canal_id and canal_id not in canais:
                raise ValueError(f"fonte {fonte.id}: canal desconhecido '{canal_id}'")

    return Config(
        tema=tema,
        sujeito=sujeito,
        canais=canais,
        exclusoes=exclusoes,
        separadores_programa=tuple(bruto.get("separadores_programa", []) or []),
        fontes=fontes,
    )


def id_estavel(*partes: str) -> str:
    """Identificador deterministico: a mesma coisa da sempre o mesmo id."""
    resumo = hashlib.sha1("::".join(partes).encode("utf-8")).hexdigest()
    return resumo[:12]


def hoje_iso() -> str:
    return date.today().isoformat()
