"""Requisições HTTP com novas tentativas para falhas temporárias.

APIs públicas às vezes ficam fora do ar por alguns segundos ou minutos
(erros 429, 500, 502, 503 e 504). Em vez de derrubar o pipeline na primeira
falha, tentamos de novo algumas vezes, esperando um pouco mais a cada vez
(espera exponencial: 5 s, 10 s, 20 s, 40 s...).

Erros definitivos, como 403 (proibido) ou 404 (não encontrado), não são
repetidos, porque tentar de novo não resolveria.
"""
import time

import requests

ERROS_TEMPORARIOS = {429, 500, 502, 503, 504}


def get_com_retry(url, tentativas=5, espera_inicial=5, **kwargs):
    kwargs.setdefault("timeout", 120)
    espera = espera_inicial
    for tentativa in range(1, tentativas + 1):
        try:
            resp = requests.get(url, **kwargs)
            if resp.status_code in ERROS_TEMPORARIOS and tentativa < tentativas:
                print(f"    {url} respondeu {resp.status_code} (indisponível). "
                      f"Nova tentativa em {espera} s ({tentativa}/{tentativas})...", flush=True)
                resp.close()
                time.sleep(espera)
                espera *= 2
                continue
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout) as e:
            if tentativa == tentativas:
                raise
            print(f"    Falha de conexão ({type(e).__name__}). Nova tentativa em {espera} s "
                  f"({tentativa}/{tentativas})...", flush=True)
            time.sleep(espera)
            espera *= 2
    raise RuntimeError("não deveria chegar aqui")
