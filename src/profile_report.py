"""
Perfilamento dos dados brutos (camada bronze). Gera docs/perfil_bronze.md com:
  - volumetria por competência (arquivo mensal)
  - mudanças de layout entre meses (colunas que entram ou saem)
  - percentual de valores vazios por coluna
  - exemplos de valores de cada coluna (para conferir o mapeamento)
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from db import conectar, registrar_etapa  # noqa: E402

DOCS = os.path.join(os.path.dirname(__file__), "..", "docs")


def main():
    conn = conectar()
    with registrar_etapa(conn, "perfil_bronze"), conn.cursor() as cur:
        cur.execute(
            "SELECT competencia, linhas, array_length(colunas,1), encoding, separador, colunas "
            "FROM meta.log_carga WHERE status='OK' ORDER BY competencia"
        )
        cargas = cur.fetchall()
        cur.execute("SELECT count(*) FROM bronze.cat_raw")
        total = cur.fetchone()[0]
        cur.execute(
            """SELECT k.key,
                      round(100.0 * count(*) FILTER (WHERE k.value IS NULL OR k.value = '') / count(*), 2)
               FROM (SELECT dados FROM bronze.cat_raw LIMIT 300000) r, jsonb_each_text(r.dados) k
               GROUP BY k.key ORDER BY k.key"""
        )
        nulos = cur.fetchall()
        exemplos = {}
        for chave, _ in nulos:
            cur.execute(
                """SELECT DISTINCT dados->>%s FROM
                     (SELECT dados FROM bronze.cat_raw WHERE dados->>%s IS NOT NULL LIMIT 2000) s
                   LIMIT 4""",
                (chave, chave),
            )
            exemplos[chave] = [str(r[0])[:40] for r in cur.fetchall()]

    agora = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    md = ["# Perfil dos dados brutos (bronze)", "", f"Gerado em {agora}. Total de linhas: **{total:,}**".replace(",", "."), ""]
    md += ["## Volumetria por arquivo mensal", "", "| Competência | Linhas | Colunas | Encoding | Separador |", "|---|---|---|---|---|"]
    for comp, linhas, ncol, enc, sep, _ in cargas:
        md.append(f"| {comp} | {linhas:,} | {ncol} | {enc} | `{sep}` |".replace(",", "."))
    md += ["", "## Mudanças de layout entre meses", ""]
    anterior, mudancas = None, 0
    for comp, _, _, _, _, cols in cargas:
        atual = set(cols)
        if anterior is not None and atual != anterior:
            mudancas += 1
            md.append(f"- **{comp}**: entraram {sorted(atual - anterior) or '-'}; saíram {sorted(anterior - atual) or '-'}")
        anterior = atual
    if not mudancas:
        md.append("- Nenhuma mudança de layout detectada.")
    md += ["", "## Completude e exemplos por coluna (amostra de até 300 mil linhas)", "", "| Coluna | % vazio | Exemplos |", "|---|---|---|"]
    for chave, pct in nulos:
        ex = "; ".join(e.replace("|", "/") for e in exemplos.get(chave, []))
        md.append(f"| `{chave}` | {pct} | {ex} |")
    os.makedirs(DOCS, exist_ok=True)
    with open(os.path.join(DOCS, "perfil_bronze.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(f"Perfil gerado em docs/perfil_bronze.md ({total} linhas, {len(cargas)} arquivos).")
    conn.close()


if __name__ == "__main__":
    main()
