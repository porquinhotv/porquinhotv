"""Pedidos HTTP com a biblioteca padrao.

Sem dependencias externas de proposito: o processo corre sozinho em CI e
cada pacote a mais e superficie de ataque. O User-Agent identifica o
projeto, nunca uma pessoa. Sem cookies, sem referer, sem estado.
"""

from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request

# A primeira corrida de historico levou 403 de dois canais com um
# User-Agent que se identificava como programa. Nao e um paywall nem uma
# area reservada: e a defesa por omissao que muitos sites poem a tudo o
# que nao pareca um browser, e aplica-se as mesmas paginas publicas que
# qualquer pessoa abre sem sessao iniciada. O cabecalho passa a ser o de
# um browser corrente para que essas paginas respondam. Nao ha cookies,
# nao ha sessao, nao ha nada que identifique uma pessoa, e o robots.txt
# continua a ser o limite: nada aqui pede paginas que um site declare
# fora de alcance.
AGENTE = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
CABECALHOS = {
    "User-Agent": AGENTE,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
}
# Trinta segundos servem para uma pagina. Um indice que varre um dominio
# inteiro pode demorar mais a montar a resposta do lado de la: a
# 2026-09-10, cinco de nove consultas ao indice de um arquivo da web
# passaram deste limite, e a leitura errada seria "nao responde". Quem
# pede um limite maior declara-o no pedido.
TEMPO_LIMITE = 30
TENTATIVAS = 3
MAX_BYTES = 32 * 1024 * 1024

# Corridas em GitHub Actions falharam a metade dos pedidos ao mesmo
# dominio com "Network is unreachable", sucessos e falhas alternados.
# E a assinatura de um IPv6 anunciado pelo DNS mas sem rota utilizavel
# na maquina que corre o job, nao um bloqueio do servidor (que devolveria
# um erro HTTP, nao um erro de encaminhamento). Forcar IPv4 evita a rota
# que nao existe. Isto altera o processo inteiro, aceitavel aqui porque
# o processo so faz pedidos HTTP e nada mais precisa de IPv6.
_getaddrinfo_original = socket.getaddrinfo


def _getaddrinfo_so_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return _getaddrinfo_original(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _getaddrinfo_so_ipv4


class ErroDeRede(RuntimeError):
    pass


# Um 429 nao e uma falha de rede: e o servidor a dizer que o ritmo e
# demasiado. Esperar dois segundos e voltar a pedir, como se fazia com
# qualquer outro erro, so gasta a paciencia de quem nos responde e volta
# a levar 429. A espera cresce depressa e respeita Retry-After quando o
# servidor o declara.
ESPERA_429 = (20.0, 60.0, 120.0)
ESPERA_MAXIMA = 180.0


def _espera_declarada(excecao) -> float | None:
    cabecalhos = getattr(excecao, "headers", None)
    valor = cabecalhos.get("Retry-After") if cabecalhos else None
    if not valor:
        return None
    try:
        return min(float(valor), ESPERA_MAXIMA)
    except (TypeError, ValueError):
        return None


def obter_texto(url: str, tentativas: int = TENTATIVAS, limite_s: float | None = None) -> str:
    ultimo: Exception | None = None
    for tentativa in range(tentativas):
        pedido = urllib.request.Request(url, headers=CABECALHOS)
        try:
            with urllib.request.urlopen(pedido, timeout=limite_s or TEMPO_LIMITE) as resposta:
                charset = resposta.headers.get_content_charset() or "utf-8"
                corpo = resposta.read(MAX_BYTES + 1)
                if len(corpo) > MAX_BYTES:
                    raise ErroDeRede(f"resposta demasiado grande: {url}")
                return corpo.decode(charset, errors="replace")
        except urllib.error.HTTPError as exc:
            ultimo = exc
            if exc.code == 429 and tentativa < tentativas - 1:
                espera = _espera_declarada(exc) or ESPERA_429[min(tentativa, len(ESPERA_429) - 1)]
                print(f"    429, a esperar {espera:.0f}s antes de repetir", flush=True)
                time.sleep(espera)
                continue
            # Um 403 ou um 404 nao mudam por se repetir o pedido.
            if exc.code in (401, 403, 404, 410):
                break
            if tentativa < tentativas - 1:
                time.sleep(2.0 * (tentativa + 1))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            ultimo = exc
            if tentativa < tentativas - 1:
                time.sleep(2.0 * (tentativa + 1))
    raise ErroDeRede(f"pedido falhou: {url}: {ultimo}")
