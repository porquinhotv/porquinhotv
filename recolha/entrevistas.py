"""A unidade publicada: a entrevista exclusiva.

Decisao do autor, 2026-09-11, e e a mais estruturante desde a remocao da
duracao: **o site conta entrevistas exclusivas e deixou de contar
emissoes**. Uma entrevista que passe em dois canais conta uma vez, fica
atribuida a um deles, e o site escreve ao lado que passou tambem no
outro. O conceito de emissao desapareceu do projeto por inteiro.

O que muda, e o que nao muda:

- **Nao muda a recolha.** Cada fonte continua a devolver o facto de uma
  entrevista ter passado num canal, num dia, com prova. Esse facto passou
  a chamar-se transmissao (recolha/modelos.py) e continua a ser guardado,
  um por prova, com a sua `primeira_vez` intacta.
- **Muda o que se publica.** Este modulo dobra as transmissoes em
  entrevistas, e e a entrevista que vai para docs/dados/entrevistas.json,
  para o resumo e para o site.

Porque a dobragem e feita aqui, a publicacao, e nao na recolha: uma
transmissao e um facto verificado com prova propria e nao se perde. Se o
agrupamento mudar amanha, muda o que se publica e nao o que esta
guardado, sem `repor` e sem reescrever `primeira_vez` de nada.

O agrupamento vem todo de config/curadoria.yml, da tabela
`mesma_entrevista`, escrita por quem leu as paginas. Sem entrada na
tabela, cada transmissao e uma entrevista: e uma afirmacao positiva que
junta duas, nunca uma deducao. A KB ja pagou por deduzir isto de um
dominio (8 linhas erradas em 8) e de um identificador de video partilhado
(metade dos casos por apanhar).
"""

from __future__ import annotations

from .modelos import url_normalizado

# Campos que a entrevista herda da transmissao a que fica atribuida. O
# site le-os como lia os da emissao, e por isso a pagina de Fontes e o
# resumo nao precisaram de saber que a unidade mudou de nome.
HERDADOS = (
    "data",
    "data_origem",
    "publicado_em",
    "canal",
    "programa",
    "origem",
    "fonte",
    "confianca",
    "prova_url",
    "titulo",
    "rondas",
    "fontes_distintas",
)


def _chave(linha: dict, grupos: dict[str, tuple[str, str]]) -> str:
    entrada = grupos.get(url_normalizado(linha.get("prova_url") or ""))
    return entrada[0] if entrada else linha.get("entrevista") or linha["id"]


def agrupar(
    linhas: list[dict], grupos: dict[str, tuple[str, str]], avisos: list[str] | None = None
) -> list[dict]:
    """Transmissoes dentro, entrevistas fora. Uma entrada por entrevista.

    O canal a que a entrevista fica atribuida vem escrito na tabela.
    Quando um grupo tem mais do que um canal e a tabela nao o diz, fica o
    primeiro por ordem alfabetica **e escreve-se um aviso**: nao ha regra
    automatica que leia o canal certo, e a KB mediu duas vezes o custo de
    fingir que ha. O aviso e a interface: sai na consola da corrida, onde
    o autor o ve, e a entrada fica marcada com `principal_declarado`
    a falso para que quem abrir o ficheiro tambem o veja.

    `primeira_vez` da entrevista e a mais antiga do grupo: a entrevista
    apareceu no site no dia em que a primeira das suas transmissoes
    apareceu, e nao no dia em que a segunda a confirmou.
    """
    por_chave: dict[str, list[dict]] = {}
    ordem: list[str] = []
    for linha in linhas:
        chave = _chave(linha, grupos)
        if chave not in por_chave:
            por_chave[chave] = []
            ordem.append(chave)
        por_chave[chave].append(linha)

    # Um grupo escrito na tabela que so juntou uma transmissao nao esta a
    # juntar nada: quase sempre e um endereco mal copiado, e sem aviso
    # ficava a contar como duas entrevistas para sempre. E o unico erro
    # desta tabela que a validacao do ficheiro nao consegue apanhar,
    # porque depende do que as fontes devolveram.
    if avisos is not None:
        for chave in sorted({c for c, _ in grupos.values()}):
            juntou = len(por_chave.get(chave, []))
            if juntou < 2:
                avisos.append(
                    f"tabela mesma_entrevista: o grupo {chave} juntou {juntou} "
                    f"transmissoes; confirmar os enderecos das provas"
                )

    entrevistas = []
    for chave in ordem:
        transmissoes = sorted(por_chave[chave], key=lambda l: (l["data"], l["canal"], l["id"]))
        declarado = ""
        for linha in transmissoes:
            entrada = grupos.get(url_normalizado(linha.get("prova_url") or ""))
            if entrada and entrada[0] == chave:
                declarado = entrada[1]
                break
        canais = sorted({l["canal"] for l in transmissoes})
        if declarado:
            principal = declarado
        elif len(canais) == 1:
            principal = canais[0]
        else:
            principal = canais[0]
            if avisos is not None:
                avisos.append(
                    f"entrevista {chave}: passou em {', '.join(canais)} e a tabela "
                    f"mesma_entrevista nao diz a qual fica atribuida; ficou {principal}"
                )
        # A transmissao do canal a que a entrevista fica atribuida e a que
        # da a data, o programa e a prova que o site mostra. Se o canal
        # declarado nao tiver transmissao nenhuma (erro de escrita na
        # tabela), fica a primeira, e o aviso diz qual foi.
        cabeca = next((l for l in transmissoes if l["canal"] == principal), None)
        if cabeca is None:
            cabeca = transmissoes[0]
            principal = cabeca["canal"]
            if avisos is not None:
                avisos.append(
                    f"entrevista {chave}: a tabela mesma_entrevista atribui-a a "
                    f"{declarado}, que nao tem transmissao nenhuma; ficou {principal}"
                )
            declarado = ""
        entrada_final = {campo: cabeca.get(campo) for campo in HERDADOS}
        entrada_final.update(
            {
                "id": chave,
                "canais": [principal] + [c for c in canais if c != principal],
                "principal_declarado": bool(declarado),
                "primeira_vez": min(
                    (l.get("primeira_vez") or "" for l in transmissoes), default=""
                ),
                "transmissoes": transmissoes,
            }
        )
        entrevistas.append(entrada_final)
    return sorted(entrevistas, key=lambda e: (e["data"], e["canal"], e["id"]))
