"""
Executa o pipeline completo, na ordem das camadas:

  infra -> ingestão (bronze) -> referências IBGE -> perfil -> visão canônica
        -> silver -> gold -> qualidade

Uso:
  python src/run_pipeline.py                    # tudo
  python src/run_pipeline.py --desde 202401     # ingere a partir de jan/2024
  python src/run_pipeline.py --etapas silver gold qualidade   # só algumas etapas
  python src/run_pipeline.py --local data/landing             # sem internet
"""
import argparse
import os
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
from db import conectar, executar_arquivo_sql, registrar_etapa  # noqa: E402

ETAPAS = ["infra", "ingestao", "ibge", "perfil", "canonica", "silver", "gold", "qualidade"]


def rodar_script(nome, *args):
    cmd = [sys.executable, os.path.join(AQUI, nome), *args]
    subprocess.run(cmd, check=True)


def rodar_sql(nome, etapa):
    conn = conectar()
    with registrar_etapa(conn, etapa, nome):
        executar_arquivo_sql(conn, os.path.join(RAIZ, "sql", nome))
    conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--etapas", nargs="+", choices=ETAPAS, default=ETAPAS)
    ap.add_argument("--desde")
    ap.add_argument("--ate")
    ap.add_argument("--local")
    args = ap.parse_args()

    inicio = time.time()
    for etapa in ETAPAS:
        if etapa not in args.etapas:
            continue
        print(f"\n=== {etapa.upper()} ===")
        if etapa == "infra":
            conn = conectar()
            executar_arquivo_sql(conn, os.path.join(RAIZ, "sql", "00_infra.sql"))
            conn.close()
        elif etapa == "ingestao":
            extra = []
            for flag in ("desde", "ate", "local"):
                if getattr(args, flag):
                    extra += [f"--{flag}", getattr(args, flag)]
            rodar_script("ingest_cat.py", *extra)
        elif etapa == "ibge":
            rodar_script("load_ibge.py")
        elif etapa == "perfil":
            rodar_script("profile_report.py")
        elif etapa == "canonica":
            rodar_script("build_canonical.py")
        elif etapa == "silver":
            rodar_sql("10_silver.sql", "silver")
        elif etapa == "gold":
            rodar_sql("20_gold.sql", "gold")
        elif etapa == "qualidade":
            rodar_script("quality.py")
    print(f"\nPipeline concluído em {time.time() - inicio:.1f} s.")


if __name__ == "__main__":
    main()
