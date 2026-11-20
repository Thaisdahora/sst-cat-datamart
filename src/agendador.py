"""
Agendador: mantém o data mart atualizado automaticamente pela API.

A cada ciclo (padrão: a cada 24 horas):
  1. consulta a API CKAN do INSS para ver se há meses novos publicados;
  2. carrega apenas o que for novo (ou republicado) na camada bronze;
  3. se algo novo entrou, atualiza referências do IBGE, silver, gold e qualidade.

Roda como serviço no Docker Compose (serviço "agendador"), então basta
"docker compose up -d" e ele fica trabalhando sozinho.

Variáveis de ambiente:
  INTERVALO_HORAS   intervalo entre verificações (padrão 24)
  DESDE             competência inicial AAAAMM (opcional)
"""
import datetime as dt
import os
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from db import conectar  # noqa: E402

INTERVALO_HORAS = float(os.environ.get("INTERVALO_HORAS", "24"))
DESDE = os.environ.get("DESDE")


def agora():
    return dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def esperar_banco(tentativas=30):
    for _ in range(tentativas):
        try:
            conectar().close()
            return
        except Exception:
            time.sleep(5)
    raise RuntimeError("Banco de dados indisponível.")


def assinatura_cargas():
    """Identifica o estado atual das cargas (quantas e quais versões)."""
    conn = conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('meta.log_carga') IS NOT NULL")
            if not cur.fetchone()[0]:
                return None
            cur.execute("SELECT count(*), coalesce(max(id), 0) FROM meta.log_carga WHERE status = 'OK'")
            return tuple(cur.fetchone())
    finally:
        conn.close()


def gold_existe():
    conn = conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('gold.fato_cat') IS NOT NULL")
            return cur.fetchone()[0]
    finally:
        conn.close()


def pipeline(*etapas):
    cmd = [sys.executable, os.path.join(AQUI, "run_pipeline.py"), "--etapas", *etapas]
    if DESDE and "ingestao" in etapas:
        cmd += ["--desde", DESDE]
    subprocess.run(cmd, check=True)


def ciclo():
    antes = assinatura_cargas()
    pipeline("infra", "ingestao")
    depois = assinatura_cargas()
    if depois != antes or not gold_existe():
        print(f"[{agora()}] Dados novos encontrados na API. Atualizando camadas...", flush=True)
        pipeline("ibge", "perfil", "canonica", "silver", "gold", "qualidade")
    else:
        print(f"[{agora()}] Nenhum mês novo publicado. Nada a atualizar.", flush=True)


def main():
    print(f"[{agora()}] Agendador iniciado. Verificando a API a cada {INTERVALO_HORAS:g} hora(s).", flush=True)
    esperar_banco()
    while True:
        try:
            ciclo()
        except Exception as e:  # não derruba o serviço por uma falha pontual (ex.: API fora do ar)
            print(f"[{agora()}] Falha no ciclo: {e}. Nova tentativa no próximo ciclo.", flush=True)
        if os.environ.get("RODAR_UMA_VEZ") == "1":
            break
        proximo = dt.datetime.now() + dt.timedelta(hours=INTERVALO_HORAS)
        print(f"[{agora()}] Próxima verificação: {proximo:%d/%m/%Y %H:%M}.", flush=True)
        time.sleep(INTERVALO_HORAS * 3600)


if __name__ == "__main__":
    main()
