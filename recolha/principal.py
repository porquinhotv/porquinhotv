"""Ponto de entrada.

    python -m recolha.principal              recolhe e escreve docs/dados
    python -m recolha.principal --dry-run    recolhe, nao escreve nada
    python -m recolha.principal --fonte X    so uma fonte
    python -m recolha.principal --paginas 20 mais paginas de pesquisa (historico)
    python -m recolha.principal --ronda X    identificador desta ronda
    python -m recolha.principal --estado F   escreve o resumo da corrida em F

Uma fonte que falhe nao derruba as outras. As fontes correm pela ordem de
config/fontes.yml; o registo curado deve vir primeiro, para ganhar os
empates na resolucao de blocos.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

from . import armazem, confirmacao, criterio, resumo
from .fontes import base as fontes_base
from .fontes import busca_site, manual, podcast_rss, youtube_feed  # noqa: F401  (registo dos plugins)
from .modelos import carregar_config, hoje_iso


def _url_normalizado(url: str) -> str:
    return url.strip().rstrip("/").replace("http://", "https://").replace("www.", "")


def _contar_recusas(quarentena: list[dict], prefixo: str = "") -> None:
    """As recusas contadas por fonte e por motivo, com um exemplo cada.

    Sem isto, uma fonte nova que devolva zero emissoes nao diz porque:
    a 2026-09-10 uma lista de episodios trouxe 194 paginas, todas lidas
    e todas com duracao, e a corrida terminou com \"194 itens em
    quarentena\" e mais nada. O motivo estava escrito em cada linha da
    quarentena e nao aparecia em lado nenhum, e o `--dry-run` nem sequer
    a escreve em disco.

    Uma linha por motivo, nunca uma por registo: sao centenas.
    """
    if not quarentena:
        return
    contagem: Counter = Counter()
    exemplos: dict[tuple[str, str], str] = {}
    for entrada in quarentena:
        # O motivo leva um parentesis com o pormenor ("formato_nao_elegivel
        # (debate)"). Agrupa-se pelo motivo inteiro, que e o que distingue
        # um debate de um direto.
        chave = (entrada.get("fonte", ""), entrada.get("motivo", ""))
        contagem[chave] += 1
        exemplos.setdefault(chave, (entrada.get("titulo") or entrada.get("url") or "")[:70])
    for (fonte_id, motivo), quantos in contagem.most_common():
        print(f"{prefixo}  {quantos:5d}  {fonte_id}: {motivo}  ex.: {exemplos[(fonte_id, motivo)]}")


def correr(so_fonte: str | None = None, dry_run: bool = False, paginas: int = 0, ronda: str = "", estado: str = "") -> int:
    config = carregar_config()
    existentes = armazem.carregar()
    aceites = []
    quarentena: list[dict] = []
    avisos: list[str] = []
    diario: list[str] = []
    provas_vistas: dict[str, str] = {}

    for fonte in config.fontes:
        if not fonte.ativa or (so_fonte and fonte.id != so_fonte):
            continue
        if paginas and fonte.tipo == "busca_site":
            fonte = replace(fonte, paginas_max=paginas, max_candidatos=max(fonte.max_candidatos, paginas * 20))
        plugin = fontes_base.plugin_para(fonte)
        if plugin is None:
            avisos.append(f"{fonte.id}: tipo desconhecido '{fonte.tipo}'")
            continue
        try:
            itens = list(plugin.obter(termos=list(config.sujeito.detetar), registo=diario))
        except Exception as exc:  # noqa: BLE001  uma fonte nao derruba a corrida
            avisos.append(f"{fonte.id}: {exc}")
            continue

        contadas = 0
        for item in itens:
            chave = _url_normalizado(item.prova_url or item.url)
            anterior = provas_vistas.get(chave)
            if anterior and anterior != fonte.id:
                criterio.rejeitar(quarentena, item, fonte, f"ja_registado ({anterior})")
                continue
            emissao = criterio.avaliar(item, fonte, config, quarentena)
            if emissao is None:
                continue
            provas_vistas.setdefault(chave, fonte.id)
            aceites.append(emissao)
            contadas += 1
        print(f"{fonte.id}: {len(itens)} itens, {contadas} emissoes")

    aceites = criterio.resolver_blocos(aceites, quarentena)

    # Confirmacao em rondas. O registo curado e o clipping sao verificados
    # a mao e entram na hora; as fontes automaticas so entram depois de o
    # mesmo bloco aparecer em rondas distintas. Ver recolha/confirmacao.py
    # para o que isto protege e o que nao protege.
    # Por omissao a ronda e o dia: duas corridas no mesmo dia leem o
    # mesmo e nao devem contar como duas confirmacoes. A corrida de
    # historico passa identificadores proprios, porque ai cada ronda e
    # uma releitura completa e independente das paginas.
    ronda = ronda or hoje_iso()
    candidatos = confirmacao.carregar()
    # Verificadas a mao: o tipo declarado na configuracao, nunca o nome
    # da fonte. Um prefixo de nome parte em silencio quando alguem
    # renomeia uma fonte, e o silencio aqui significava publicar sem
    # confirmacao.
    a_mao = {f.id for f in config.fontes if f.tipo == "manual"}
    manuais = [e for e in aceites if e.fonte in a_mao]
    automaticas = [e for e in aceites if e.fonte not in a_mao]
    candidatos = confirmacao.registar(candidatos, automaticas, ronda)
    minimo = config.tema.rondas_para_confirmar
    confirmadas = confirmacao.filtrar(automaticas, candidatos, minimo, quarentena)
    # Quantas emissoes esta corrida viu mas ainda nao pode publicar. E o
    # sinal que decide se vale a pena uma segunda ronda hoje: sem nada a
    # espera, uma segunda leitura nao teria nada para confirmar.
    por_confirmar = len(automaticas) - len(confirmadas)
    aceites = manuais + confirmadas
    aceites = confirmacao.anotar(aceites, candidatos)

    fundidas, adicionadas, atualizadas = armazem.fundir(existentes, aceites)
    agregados = resumo.construir(list(fundidas.values()), config)

    prefixo = "[dry-run] " if dry_run else ""
    print(f"{prefixo}+{adicionadas} novas, {atualizadas} atualizadas, {len(fundidas)} no total")
    print(f"{prefixo}{len(quarentena)} itens em quarentena nesta corrida")
    _contar_recusas(quarentena, prefixo)
    # `por_confirmar` e o que ficou a aguardar rondas, e e o que o
    # workflow diario le para decidir se corre uma segunda ronda. Ate
    # 2026-09-10 esta variavel era reescrita aqui com a contagem do
    # motivo de quarentena `por_confirmar` (fonte automatica sem
    # duracao), que era outra coisa: com esse motivo a zero, a segunda
    # ronda nunca corria mesmo havendo blocos a espera. O motivo deixou
    # de existir com a duracao, e a variavel passou a dizer o que o nome
    # diz.
    if por_confirmar:
        print(f"{prefixo}{por_confirmar} a aguardar confirmacao noutra ronda")

    if not dry_run:
        armazem.guardar(fundidas)
        resumo.guardar(agregados)
        armazem.guardar_quarentena(quarentena)
        confirmacao.guardar(candidatos)

    if estado:
        Path(estado).write_text(
            json.dumps(
                {
                    "ronda": ronda,
                    "adicionadas": adicionadas,
                    "atualizadas": atualizadas,
                    "por_confirmar": por_confirmar,
                    "total": len(fundidas),
                },
                ensure_ascii=False,
                indent=1,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )

    for linha in diario:
        print(f"  {linha}", flush=True)

    for aviso in avisos:
        print(f"AVISO {aviso}", file=sys.stderr)
    return 0 if aceites or not avisos else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Recolha de emissoes")
    parser.add_argument("--fonte", help="correr apenas esta fonte")
    parser.add_argument("--dry-run", action="store_true", help="nao escrever em disco")
    parser.add_argument("--paginas", type=int, default=0, help="paginas de pesquisa por termo (historico)")
    parser.add_argument("--ronda", default="", help="identificador desta ronda (por omissao, o dia)")
    parser.add_argument("--estado", default="", help="ficheiro onde escrever o resumo da corrida")
    args = parser.parse_args()
    return correr(so_fonte=args.fonte, dry_run=args.dry_run, paginas=args.paginas, ronda=args.ronda, estado=args.estado)


if __name__ == "__main__":
    raise SystemExit(main())
