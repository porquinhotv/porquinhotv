"""Sonda de hipoteses. Corre a pedido, nao escreve dados do site.

    python -m ferramentas.sondar
    python -m ferramentas.sondar --grupo "Motores de busca alternativos"

Le config/sondagem.yml e, para cada URL candidato, regista o que se
consegue saber sem adivinhar: se responde, com que codigo, que tamanho
tem o HTML servido, se os termos aparecem nele, e quantas ligacoes uteis
se conseguem colher. Escreve sondagem/SONDAGEM.md.

Existe porque as duas perguntas que faltavam nao se respondem por
raciocinio. Qual e o parametro de paginacao de um site, e se um motor de
busca responde a uma maquina de datacenter, sao factos sobre servidores
que so se sabem perguntando. Uma hipotese que devolva 200 e zero
ligacoes e tao inutil como uma que devolva 403, e o relatorio mostra as
duas coisas para que a leitura nao se engane com o codigo de resposta.

Nada do que esta aqui e configuracao de recolha. O que passar na
sondagem e depois escrito a mao em config/fontes.yml, com os olhos
postos no relatorio.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import yaml

from recolha import extracao
from recolha.modelos import RAIZ, carregar_config, normalizar
from recolha.rede import ErroDeRede, obter_texto

FICHEIRO = RAIZ / "config" / "sondagem.yml"
PASTA = RAIZ / "sondagem"
PAUSA_S = 1.5


def carregar(caminho: Path = FICHEIRO) -> dict:
    return yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}


def analisar(html: str, url: str, termos: list[str], dominio_alvo: str, dominios_interesse: list[str] | None = None) -> dict:
    """O que esta hipotese devolveu, em numeros comparaveis entre si."""
    corpo = extracao.texto_visivel(html)
    palheiro = normalizar(corpo)
    presentes = [t for t in termos if normalizar(t) and normalizar(t) in palheiro]

    if dominio_alvo:
        ligacoes = extracao.ligacoes(html, url, dominio_alvo)
    else:
        # Num motor de busca interessa saber para quantos dominios
        # distintos ele aponta: e a medida de ter mesmo devolvido
        # resultados em vez de uma pagina de aviso.
        ligacoes = []
        for dominio in dominios_interesse or []:
            ligacoes += extracao.ligacoes(html, url, dominio)

    return {
        "responde": True,
        "bytes_html": len(html),
        "bytes_texto": len(corpo),
        "termos_presentes": presentes,
        "ligacoes": len(ligacoes),
        "exemplos": ligacoes[:3],
    }


def correr(config: dict, obter=obter_texto, so_grupo: str | None = None, dormir=time.sleep) -> dict:
    tema = carregar_config()
    termo = config.get("termo", "")
    termos = [termo] + [t for t in tema.sujeito.detetar]

    resultado = {
        "verificado_em": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "termo": termo,
        "grupos": [],
    }
    for grupo in config.get("grupos") or []:
        if so_grupo and grupo.get("nome") != so_grupo:
            continue
        linha = {"nome": grupo.get("nome", ""), "dominio_alvo": grupo.get("dominio_alvo", ""), "hipoteses": []}
        for modelo in grupo.get("hipoteses") or []:
            url = modelo.replace("{termo}", urllib.parse.quote_plus(termo))
            print(f"  a sondar {url}", flush=True)
            try:
                html = obter(url)
            except ErroDeRede as exc:
                linha["hipoteses"].append({"url": url, "responde": False, "erro": str(exc)})
                print(f"    nao responde: {exc}", flush=True)
            else:
                dados = analisar(html, url, termos, linha["dominio_alvo"], config.get("dominios_de_interesse") or [])
                linha["hipoteses"].append({"url": url, **dados})
                print(f"    {dados['bytes_texto']} bytes de texto, {dados['ligacoes']} ligacoes, termos {dados['termos_presentes']}", flush=True)
            dormir(PAUSA_S)
        resultado["grupos"].append(linha)
    return resultado


def relatorio(resultado: dict) -> str:
    linhas = [
        "# Sondagem de hipoteses",
        "",
        f"Verificado em {resultado['verificado_em']}. Consulta: {resultado['termo']}.",
        "",
        "Uma hipotese so serve se responder E trouxer ligacoes. Responder com 200",
        "e zero ligacoes e uma pagina de aviso, nao um resultado.",
        "",
    ]
    for grupo in resultado["grupos"]:
        linhas += [f"## {grupo['nome']}", ""]
        linhas += ["| Hipotese | Responde | Texto | Ligacoes | Termos |", "|---|---|---|---|---|"]
        for h in grupo["hipoteses"]:
            if not h.get("responde"):
                linhas.append(f"| {h['url']} | nao ({h.get('erro', '')[:60]}) | | | |")
            else:
                linhas.append(
                    f"| {h['url']} | sim | {h['bytes_texto']} | {h['ligacoes']} | {', '.join(h['termos_presentes']) or 'nenhum'} |"
                )
        linhas.append("")
        for h in grupo["hipoteses"]:
            for exemplo in h.get("exemplos") or []:
                linhas.append(f"- {h['url']} -> {exemplo}")
        linhas.append("")
    return "\n".join(linhas).rstrip() + "\n"


def escrever(resultado: dict, pasta: Path = PASTA) -> None:
    import json

    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "sondagem.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    (pasta / "SONDAGEM.md").write_text(relatorio(resultado), encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Sondagem de hipoteses")
    parser.add_argument("--grupo", help="so este grupo")
    args = parser.parse_args(argv)
    resultado = correr(carregar(), so_grupo=args.grupo)
    escrever(resultado)
    print(f"escrito em {PASTA}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
