"""Criterio de inclusao. O ficheiro mais importante do projeto.

Tudo o que decide se um item conta, e como conta, esta aqui. E curto de
proposito, para poder ser lido por inteiro por quem quiser contestar um
numero. As regras de configuracao que este ficheiro aplica estao em
config/porquinho.yml e config/fontes.yml.

Um item conta como emissao quando, por esta ordem:

1. a data de emissao (declarada, ou de publicacao na falta dela) nao e
   anterior ao inicio do tema;
2. o sujeito e identificado (no registo curado, por construcao; nas
   outras fontes, por nome no titulo, na sinopse ou nas etiquetas);
3. a classificacao por segmento lhe da um formato elegivel;
4. nenhum termo de exclusao aparece no titulo;
5. numa fonte automatica, o formato esta provado: o titulo diz
   entrevista, ou o programa e um programa de entrevista, ou a propria
   fonte declara o formato na configuracao. No registo curado e no
   clipping foi uma pessoa que leu a pagina, e isso e a prova;
6. o canal e um dos canais medidos;
7. a duracao e conhecida, ou a fonte e verificada a mao e pode registar
   uma emissao com a duracao por apurar.

Nao ha duracao minima. Uma entrevista curta e uma entrevista curta, e o
que separa entrevista de declaracao e o formato, nao o relogio.

O passo 5 existe porque o contrario ja aconteceu: com o formato a
`entrevista` por omissao, bastava nao haver termo de exclusao para uma
peca noticiosa de 55 segundos com o nome do sujeito ser publicada como
entrevista exclusiva. Sete das 42 emissoes publicadas a 8 de setembro de
2026 eram isso. A regra e agora a inversa: sem prova de formato nao ha
formato, e o que nao se sabe nao se publica.

Cada rejeicao vai para a quarentena com o motivo e um excerto. Nada
desaparece em silencio. Os motivos, para quem le a quarentena:

    sem_data                    a pagina nao declara data nenhuma
    anterior_ao_inicio          antes da data de inicio do tema
    sem_sujeito                 o nome nao aparece no titulo nem na descricao
    formato_nao_elegivel (x)    debate, declaracao, direto, ou outro formato
    formato_nao_apurado         fonte automatica sem prova de que e uma
                                entrevista: nem o titulo nem o programa o
                                dizem. Nao e uma rejeicao do formato, e a
                                ausencia dele
    canal_desconhecido          canal que nao esta em config/porquinho.yml
    por_confirmar               fonte automatica sem duracao: e um candidato
                                a verificar a mao, nao uma emissao
    fragmento_ou_repetido       outro item do mesmo bloco tem melhor prova
    ja_registado                o registo curado ja tem esta prova
"""

from __future__ import annotations

from .datas import resolver_data
from .modelos import (
    FORMATO_ELEGIVEL,
    Config,
    Emissao,
    Fonte,
    ItemBruto,
    contem_palavra,
    hoje_iso,
    id_estavel,
)


def programa_do_titulo(titulo: str, config: Config) -> str:
    """Nome do programa deduzido do titulo, quando a fonte nao o declara.

    Os canais escrevem o titulo como "Programa - Convidado - ep. N". A
    parte antes do primeiro separador e o nome do programa, exceto quando
    ja e o nome do sujeito, caso em que nao ha programa a deduzir.

    Isto importa alem da apresentacao: o bloco que junta fragmentos da
    mesma emissao e (canal, programa, dia). Com o programa sempre vazio,
    duas emissoes diferentes do mesmo canal no mesmo dia colidiam num so
    bloco e uma delas era descartada como repetida.

    Os separadores estao em config/porquinho.yml. Nenhum nome de programa
    vive no codigo.
    """
    for separador in config.separadores_programa:
        if separador in titulo:
            cabeca = titulo.split(separador)[0].strip()
            if cabeca and not config.sujeito.aparece_em(cabeca):
                return cabeca
    return ""


def classificar(item: ItemBruto, fonte: Fonte, config: Config) -> tuple[str, str, str, bool]:
    """(programa, canal, formato, formato_declarado) para este item.
    Classifica pelo titulo: a descricao fala de tudo e apanharia programas
    mencionados de passagem.

    `formato_declarado` diz se o formato veio de uma decisao escrita na
    configuracao (uma regra de segmento que correspondeu, ou a fonte com
    `formato` declarado) ou se e so a omissao do modelo. A distincao
    importa: a omissao nao e prova de nada.
    """
    for regra in fonte.segmentos:
        if regra.corresponde(item.titulo):
            return (
                regra.programa or item.programa or fonte.programa,
                regra.canal or item.canal or fonte.canal,
                regra.formato or fonte.formato,
                True,
            )
    programa = item.programa or fonte.programa or programa_do_titulo(item.titulo, config)
    return programa, item.canal or fonte.canal, fonte.formato, fonte.formato_declarado


def formato_provado(item: ItemBruto, programa: str, config: Config) -> bool:
    """So o titulo e o programa contam. A sinopse e as etiquetas servem
    para encontrar o sujeito, nao para provar o formato: uma peca que
    fale de uma entrevista nao e uma entrevista."""
    return config.prova_de_formato.cobre(item.titulo, programa)


def motivo_de_exclusao(item: ItemBruto, config: Config) -> str | None:
    """Primeiro motivo cujo termo aparece no titulo. So no titulo: a
    descricao fala de tudo, e um debate mencionado de passagem nao faz
    de uma entrevista um debate."""
    for motivo, termos in config.exclusoes.items():
        if contem_palavra(item.titulo, termos):
            return motivo
    return None


def rejeitar(quarentena: list | None, item: ItemBruto, fonte: Fonte, motivo: str) -> None:
    if quarentena is None:
        return
    quarentena.append(
        {
            "fonte": fonte.id,
            "id_nativo": item.id_nativo,
            "publicado_em": item.publicado_em,
            "titulo": item.titulo,
            "url": item.url,
            "motivo": motivo,
            "excerto": " ".join(item.descricao.split())[:280],
        }
    )


def avaliar(
    item: ItemBruto, fonte: Fonte, config: Config, quarentena: list | None = None
) -> Emissao | None:
    tema = config.tema
    # O sujeito procura-se no titulo, na sinopse e nas etiquetas: um
    # canal identifica o convidado nas tags de uma peca cujo titulo nao o
    # nomeia. A classificacao por formato continua a ser so pelo titulo.
    texto = f"{item.titulo} {item.descricao} {item.etiquetas}"

    data, origem = resolver_data(texto, item.publicado_em, item.data_declarada)
    if not data:
        # Sem data nao ha emissao: nao se sabe em que dia foi. Motivo
        # proprio, e nao `anterior_ao_inicio`: uma data que nao existe nao
        # e uma data anterior, e rotula-la assim faria a quarentena
        # afirmar uma coisa falsa sobre 59 das 64 rejeicoes da primeira
        # corrida de historico.
        rejeitar(quarentena, item, fonte, "sem_data")
        return None
    if data < tema.desde:
        rejeitar(quarentena, item, fonte, "anterior_ao_inicio")
        return None

    if fonte.tipo != "manual" and not config.sujeito.aparece_em(texto):
        rejeitar(quarentena, item, fonte, "sem_sujeito")
        return None

    programa, canal, formato, formato_declarado = classificar(item, fonte, config)
    if formato != FORMATO_ELEGIVEL:
        rejeitar(quarentena, item, fonte, f"formato_nao_elegivel ({formato})")
        return None

    exclusao = motivo_de_exclusao(item, config)
    if exclusao:
        rejeitar(quarentena, item, fonte, f"formato_nao_elegivel ({exclusao})")
        return None

    # A exclusao vem primeiro de proposito: "Debate com o sujeito" e um
    # debate, e dizer que nao se apurou o formato seria menos verdade.
    if fonte.tipo != "manual" and not formato_declarado and not formato_provado(item, programa, config):
        rejeitar(quarentena, item, fonte, "formato_nao_apurado")
        return None

    if not config.canal_valido(canal):
        rejeitar(quarentena, item, fonte, "canal_desconhecido")
        return None

    if item.duracao_s is None and not fonte.duracao_opcional:
        rejeitar(quarentena, item, fonte, "por_confirmar")
        return None

    bloco = id_estavel(canal, programa, data)
    return Emissao(
        id=f"{fonte.id}:{id_estavel(fonte.id, item.id_nativo)}",
        bloco=bloco,
        entrevista=item.mesma_entrevista or bloco,
        data=data,
        data_origem=origem,
        publicado_em=item.publicado_em,
        canal=canal,
        programa=programa,
        duracao_s=None if item.duracao_s is None else int(item.duracao_s),
        parcial=bool(item.parcial or fonte.assumir_parcial),
        origem=item.origem or fonte.origem,
        fonte=fonte.id,
        confianca=fonte.confianca,
        prova_url=item.prova_url or item.url,
        titulo=item.titulo,
        primeira_vez=hoje_iso(),
    )


def _melhor(a: Emissao, b: Emissao) -> bool:
    """True se `a` deve ficar no lugar de `b` no mesmo bloco.

    Uma emissao com duracao apurada ganha sempre a uma sem duracao: e o
    mesmo evento, com melhor prova. Entre duas com duracao ganha a mais
    longa, porque a curta e tipicamente um recorte da longa. Entre duas
    sem duracao ganha a que ja la estava, e as fontes correm pela ordem
    de config/fontes.yml, com o canal a frente do clipping.
    """
    if (a.duracao_s is None) != (b.duracao_s is None):
        return b.duracao_s is None
    if a.duracao_s is None:
        return False
    return a.duracao_s > b.duracao_s


def resolver_blocos(emissoes: list[Emissao], quarentena: list | None = None) -> list[Emissao]:
    """Um bloco (canal, programa, data) fica com uma so emissao.

    Os canais publicam a mesma entrevista como video integral mais varios
    recortes, e a imprensa noticia a mesma entrevista que o canal publica.
    Contar cada item daria varias entrevistas onde houve uma. Ver _melhor
    para o criterio de desempate.

    Ha mais do que uma emissao por dia no mesmo canal com frequencia: uma
    entrevista de manha num programa de entretenimento e outra a noite num
    noticiario sao duas emissoes, e contam as duas, porque o programa
    entra na chave e e diferente nas duas.

    O caso que esta chave nao resolve e o de duas emissoes do mesmo dia e
    canal cujo programa nao foi possivel apurar em nenhuma das duas: ficam
    com a mesma chave e uma delas e tratada como recorte da outra. O erro
    e sempre por defeito, nunca por excesso, e a quarentena diz que foi
    isso que aconteceu para que se veja em vez de se adivinhar.
    """
    por_bloco: dict[str, Emissao] = {}
    ordem: list[str] = []
    for emissao in emissoes:
        atual = por_bloco.get(emissao.bloco)
        if atual is None:
            por_bloco[emissao.bloco] = emissao
            ordem.append(emissao.bloco)
            continue
        vencedora, perdedora = (emissao, atual) if _melhor(emissao, atual) else (atual, emissao)
        por_bloco[emissao.bloco] = vencedora
        if quarentena is not None:
            quarentena.append(
                {
                    "fonte": perdedora.fonte,
                    "id_nativo": perdedora.id,
                    "publicado_em": perdedora.publicado_em,
                    "titulo": perdedora.titulo,
                    "url": perdedora.prova_url,
                    "motivo": (
                        f"fragmento_ou_repetido (ficou {vencedora.id})"
                        if vencedora.programa
                        else f"fragmento_ou_repetido (programa nao apurado, ficou {vencedora.id})"
                    ),
                    "excerto": "",
                }
            )
    return [por_bloco[b] for b in ordem]
