"""Criterio de inclusao. O ficheiro mais importante do projeto.

Tudo o que decide se um item conta, e como conta, esta aqui. E curto de
proposito, para poder ser lido por inteiro por quem quiser contestar um
numero. As regras de configuracao que este ficheiro aplica estao em
config/porquinho.yml e config/fontes.yml.

Um item conta como transmissao quando, por esta ordem:

1. a data em que a entrevista passou (declarada, ou a de publicacao na
   falta dela) nao e
   anterior ao inicio do tema;
2. o sujeito e identificado (no registo curado, por construcao; nas
   outras fontes, por nome no titulo, na sinopse ou nas etiquetas);
3. a classificacao por segmento lhe da um formato elegivel;
4. nenhum termo de exclusao aparece no titulo;
5. numa fonte automatica, o formato esta provado: o titulo diz
   entrevista, ou o programa e um programa de entrevista, ou a propria
   fonte declara o formato na configuracao. No registo curado e no
   clipping foi uma pessoa que leu a pagina, e isso e a prova;
6. o canal e um dos canais medidos.

A duracao nao entra em lado nenhum. Ate 2026-09-10 havia um passo 7 que
exigia duracao conhecida numa fonte automatica, e o site somava tempo.
Foi retirado por decisao do autor: o que se conta e a existencia da
entrevista, provada por uma pagina publica, e o tempo que ocupou nao
interessa. Uma peca curta que relate a entrevista prova-a tanto como o
video integral. Nao ha duracao minima, nem nunca houve.

O passo 5 existe porque o contrario ja aconteceu: com o formato a
`entrevista` por omissao, bastava nao haver termo de exclusao para uma
peca noticiosa de 55 segundos com o nome do sujeito ser publicada como
entrevista exclusiva. Sete das 42 linhas publicadas a 8 de setembro de
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
    fragmento_ou_repetido       outro item do mesmo bloco ja provou a transmissao
    ja_registado                o registo curado ja tem esta prova
"""

from __future__ import annotations

from .datas import resolver_data
from .modelos import (
    FORMATO_ELEGIVEL,
    Config,
    Fonte,
    ItemBruto,
    Transmissao,
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
    mesma transmissao e (canal, programa, dia). Com o programa sempre
    vazio, duas entrevistas diferentes do mesmo canal no mesmo dia
    colidiam num so bloco e uma delas era descartada como repetida.

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
) -> Transmissao | None:
    tema = config.tema
    # O sujeito procura-se no titulo, na sinopse e nas etiquetas: um
    # canal identifica o convidado nas tags de uma peca cujo titulo nao o
    # nomeia. A classificacao por formato continua a ser so pelo titulo.
    texto = f"{item.titulo} {item.descricao} {item.etiquetas}"

    data, origem = resolver_data(texto, item.publicado_em, item.data_declarada)
    if not data:
        # Sem data nao ha transmissao: nao se sabe em que dia foi. Motivo
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

    bloco = id_estavel(canal, programa, data)
    return Transmissao(
        id=f"{fonte.id}:{id_estavel(fonte.id, item.id_nativo)}",
        bloco=bloco,
        # Por omissao cada transmissao e uma entrevista. So a tabela
        # `mesma_entrevista` de config/curadoria.yml junta duas, e isso
        # acontece a publicacao, em recolha/entrevistas.py: aqui nao se
        # deduz agrupamento nenhum a partir do item.
        entrevista=bloco,
        data=data,
        data_origem=origem,
        publicado_em=item.publicado_em,
        canal=canal,
        programa=programa,
        origem=item.origem or fonte.origem,
        fonte=fonte.id,
        confianca=fonte.confianca,
        prova_url=item.prova_url or item.url,
        titulo=item.titulo,
        primeira_vez=hoje_iso(),
    )


def resolver_blocos(transmissoes: list[Transmissao], quarentena: list | None = None) -> list[Transmissao]:
    """Um bloco (canal, programa, data) fica com uma so transmissao.

    Os canais publicam a mesma entrevista como video integral mais varios
    recortes, e a imprensa noticia a mesma entrevista que o canal publica.
    Contar cada item daria varias entrevistas onde houve uma. Fica a
    primeira que chegou: as fontes correm pela ordem de config/fontes.yml,
    com o registo curado a frente de tudo e o canal a frente do clipping.
    Ate 2026-09-10 a duracao desempatava (a mais longa ganhava ao
    recorte); sem duracao no modelo, a ordem das fontes e o unico criterio,
    e e um criterio que qualquer pessoa le no ficheiro de configuracao.

    Ha mais do que uma entrevista por dia no mesmo canal com frequencia:
    uma de manha num programa de entretenimento e outra a noite num
    noticiario sao duas entrevistas, e contam as duas, porque o programa
    entra na chave e e diferente nas duas.

    O caso que esta chave nao resolve e o de duas entrevistas do mesmo dia
    e canal cujo programa nao foi possivel apurar em nenhuma das duas:
    ficam com a mesma chave e uma delas e tratada como recorte da outra. O
    erro e sempre por defeito, nunca por excesso, e a quarentena diz que
    foi isso que aconteceu para que se veja em vez de se adivinhar.

    **Uma transmissao sem programa apurado nao abre bloco proprio** quando o
    mesmo canal e o mesmo dia ja tem uma com programa apurado. Ver
    _absorver_sem_programa: o contrario inflacionava a contagem.
    """
    por_bloco: dict[str, Transmissao] = {}
    ordem: list[str] = []
    for transmissao in transmissoes:
        atual = por_bloco.get(transmissao.bloco)
        if atual is None:
            por_bloco[transmissao.bloco] = transmissao
            ordem.append(transmissao.bloco)
            continue
        vencedora, perdedora = atual, transmissao
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
    return _absorver_sem_programa([por_bloco[b] for b in ordem], quarentena)


def _absorver_sem_programa(transmissoes: list[Transmissao], quarentena: list | None) -> list[Transmissao]:
    """Junta ao bloco com programa apurado as transmissoes do mesmo canal e
    dia que ficaram sem programa.

    Reproduz um erro real, medido no dataset publicado a 2026-09-10: o
    mesmo episodio aparecia duas vezes no mesmo dia e canal, uma vez
    titulado "<programa> - <nome> - ep. 41", de onde a deducao tira o nome
    do programa, e outra titulada so "<programa>", que nao tem separador
    nenhum e de onde a deducao nao tira nada. Programa diferente, chave
    diferente, dois blocos, duas entrevistas contadas onde houve uma.
    Aconteceu em 2022-10-19, 2025-11-04 e 2026-01-21, tres em doze linhas
    da mesma fonte.

    A duracao mascarava isto ate 2026-09-10, e nao por desenho: as linhas
    sem programa nunca chegavam ao dataset porque morriam antes, na
    barreira da duracao.

    Absorve-se a que nao tem programa, e nao o contrario, porque "nao
    apurado" nao e uma afirmacao: nao se sabe qual foi o programa, logo
    nao se pode afirmar que foi outro. Duas transmissoes com programas
    apurados e diferentes no mesmo dia continuam a contar as duas, que e o
    caso real da manha num programa de entretenimento e da noite num
    noticiario. Erro por defeito, como manda a regra da casa.
    """
    com_programa = {(t.canal, t.data) for t in transmissoes if t.programa.strip()}
    ficam = []
    for transmissao in transmissoes:
        if transmissao.programa.strip() or (transmissao.canal, transmissao.data) not in com_programa:
            ficam.append(transmissao)
            continue
        if quarentena is not None:
            quarentena.append(
                {
                    "fonte": transmissao.fonte,
                    "id_nativo": transmissao.id,
                    "publicado_em": transmissao.publicado_em,
                    "titulo": transmissao.titulo,
                    "url": transmissao.prova_url,
                    "motivo": "fragmento_ou_repetido (sem programa apurado, o canal ja tem entrevista neste dia)",
                    "excerto": "",
                }
            )
    return ficam
