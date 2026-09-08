"""Ponto de entrada.

    python -m recolha.principal              recolhe e escreve docs/dados
    python -m recolha.principal --dry-run    recolhe, nao escreve nada
    python -m recolha.principal --fonte X    so uma fonte

Uma fonte que falhe nao derruba as outras. As fontes correm pela ordem de
config/fontes.yml; o registo curado deve vir primeiro, para ganhar os
empates na resolucao de blocos.
"""

from __future__ import annotations

import argparse
import sys

from . import armazem, criterio, resumo
from .fontes import base as fontes_base
from .fontes import manual, podcast_rss, youtube_feed  # noqa: F401  (registo dos plugins)
from .modelos import carregar_config


def _url_normalizado(url: str) -> str:
    return url.strip().rstrip("/").replace("http://", "https://").replace("www.", "")


def correr(so_fonte: str | None = None, dry_run: bool = False) -> int:
    config = carregar_config()
    existentes = armazem.carregar()
    aceites = []
    quarentena: list[dict] = []
    avisos: list[str] = []
    provas_vistas: dict[str, str] = {}

    for fonte in config.fontes:
        if not fonte.ativa or (so_fonte and fonte.id != so_fonte):
            continue
        plugin = fontes_base.plugin_para(fonte)
        if plugin is None:
            avisos.append(f"{fonte.id}: tipo desconhecido '{fonte.tipo}'")
            continue
        try:
            itens = list(plugin.obter())
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
    fundidas, adicionadas, atualizadas = armazem.fundir(existentes, aceites)
    agregados = resumo.construir(list(fundidas.values()), config)

    prefixo = "[dry-run] " if dry_run else ""
    print(f"{prefixo}+{adicionadas} novas, {atualizadas} atualizadas, {len(fundidas)} no total")
    print(f"{prefixo}{len(quarentena)} itens em quarentena nesta corrida")
    por_confirmar = sum(1 for e in quarentena if e["motivo"] == "por_confirmar")
    if por_confirmar:
        print(f"{prefixo}{por_confirmar} por confirmar no registo curado (ver quarentena)")

    if not dry_run:
        armazem.guardar(fundidas)
        resumo.guardar(agregados)
        armazem.guardar_quarentena(quarentena)

    for aviso in avisos:
        print(f"AVISO {aviso}", file=sys.stderr)
    return 0 if aceites or not avisos else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Recolha de emissoes")
    parser.add_argument("--fonte", help="correr apenas esta fonte")
    parser.add_argument("--dry-run", action="store_true", help="nao escrever em disco")
    args = parser.parse_args()
    return correr(so_fonte=args.fonte, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
