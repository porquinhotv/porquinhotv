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

AGENTE = "porquinho-tv/1.0 (contagem de emissoes; dados publicos)"
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


def obter_texto(url: str) -> str:
    ultimo: Exception | None = None
    for tentativa in range(TENTATIVAS):
        pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:
                charset = resposta.headers.get_content_charset() or "utf-8"
                corpo = resposta.read(MAX_BYTES + 1)
                if len(corpo) > MAX_BYTES:
                    raise ErroDeRede(f"resposta demasiado grande: {url}")
                return corpo.decode(charset, errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            ultimo = exc
            if tentativa < TENTATIVAS - 1:
                time.sleep(2.0 * (tentativa + 1))
    raise ErroDeRede(f"pedido falhou: {url}: {ultimo}")
