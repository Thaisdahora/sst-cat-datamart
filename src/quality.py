"""
Regras de qualidade de dados. Cada regra calcula um valor, compara com um limite
e grava o resultado em meta.qualidade_resultado. Também gera docs/qualidade.md.

Dimensões avaliadas: completude, validade, unicidade, integridade e consistência.
Os limites são pontos de partida: ajuste-os depois de conhecer os dados reais
e registre a justificativa no relatório (isso é uma boa evidência de sprint).
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from db import conectar, registrar_etapa  # noqa: E402

DOCS = os.path.join(os.path.dirname(__file__), "..", "docs")

PCT_NULO = "SELECT round(100.0 * count(*) FILTER (WHERE {col} IS NULL) / NULLIF(count(*),0), 2) FROM silver.cat"
PCT_SK_NAO_INFORMADO = "SELECT round(100.0 * count(*) FILTER (WHERE {col} = -1) / NULLIF(count(*),0), 2) FROM gold.fato_cat"

# (regra, dimensão, camada, SQL, limite, operador, unidade)
REGRAS = [
    ("CNAE do empregador ausente", "completude", "silver", PCT_NULO.format(col="cnae_digitos"), 5, "<=", "%"),
    ("CBO do acidentado ausente", "completude", "silver", PCT_NULO.format(col="cbo_cod"), 10, "<=", "%"),
    ("Agente causador ausente", "completude", "silver", PCT_NULO.format(col="agente_causador"), 10, "<=", "%"),
    ("Parte do corpo ausente", "completude", "silver", PCT_NULO.format(col="parte_corpo"), 10, "<=", "%"),
    ("UF do empregador ausente", "completude", "silver", PCT_NULO.format(col="uf_empregador_txt"), 5, "<=", "%"),
    ("UF do acidente diferente da UF do empregador", "consistencia", "silver",
     "SELECT round(100.0 * count(*) FILTER (WHERE uf_acidente_txt IS NOT NULL AND uf_acidente_txt <> uf_empregador_txt)"
     " / NULLIF(count(*) FILTER (WHERE uf_acidente_txt IS NOT NULL),0), 2) FROM silver.cat", 30, "<=", "%"),
    ("Data do acidente inválida (rejeitada)", "validade", "bronze->silver",
     "SELECT round(100.0 * (SELECT count(*) FROM silver.cat_rejeitada WHERE motivo='DATA_ACIDENTE_INVALIDA')"
     " / NULLIF((SELECT count(*) FROM bronze.cat_raw),0), 2)", 1, "<=", "%"),
    ("Acidente com data no futuro", "validade", "silver",
     "SELECT count(*) FROM silver.cat WHERE data_acidente > current_date", 0, "<=", "registros"),
    ("Acidente posterior à emissão da CAT", "consistencia", "silver",
     "SELECT round(100.0 * count(*) FILTER (WHERE data_acidente > data_emissao_cat) / NULLIF(count(*),0), 2)"
     " FROM silver.cat", 1, "<=", "%"),
    ("Idade fora de 14 a 90 anos", "validade", "silver",
     "SELECT round(100.0 * count(*) FILTER (WHERE date_part('year', age(data_acidente, data_nascimento))"
     " NOT BETWEEN 14 AND 90) / NULLIF(count(*) FILTER (WHERE data_nascimento IS NOT NULL),0), 2)"
     " FROM silver.cat", 2, "<=", "%"),
    # Duplicidade separada em duas regras (ajuste da Sprint 2). A investigação mostrou que
    # 99% das cópias vêm de arquivos do INSS que acumulam os meses seguintes (ex.: o
    # arquivo 202506 traz junho, julho e agosto, que reaparecem em 202507 e 202508).
    # Essa sobreposição é estrutural da fonte e é tratada pela deduplicação; o limite
    # de 15% só alerta se ela crescer além do padrão observado (13%).
    ("Duplicados entre arquivos (sobreposição da fonte)", "unicidade", "bronze->silver",
     "SELECT round(100.0 * (SELECT count(*) FROM silver.cat_rejeitada r JOIN silver.cat s USING (hash_registro)"
     " WHERE r.motivo='DUPLICADO' AND r.competencia <> s.competencia)"
     " / NULLIF((SELECT count(*) FROM bronze.cat_raw),0), 2)", 15, "<=", "%"),
    # Cópias dentro do mesmo arquivo não são esperadas: aqui o limite continua baixo.
    ("Duplicados dentro do mesmo arquivo", "unicidade", "bronze->silver",
     "SELECT round(100.0 * (SELECT count(*) FROM silver.cat_rejeitada r JOIN silver.cat s USING (hash_registro)"
     " WHERE r.motivo='DUPLICADO' AND r.competencia = s.competencia)"
     " / NULLIF((SELECT count(*) FROM bronze.cat_raw),0), 2)", 1, "<=", "%"),
    # Regra nova (Sprint 2): meses com volume de acidentes muito abaixo do normal, que
    # indicam publicação incompleta na fonte (ex.: set/2024 a mai/2025). Considera só os
    # meses cobertos pelos arquivos carregados e ignora o último mês, ainda incompleto.
    ("Meses com volume de acidentes abaixo de 50% da mediana", "completude", "silver",
     "WITH m AS (SELECT date_trunc('month', data_acidente)::date AS mes, count(*) AS n FROM silver.cat"
     " WHERE data_acidente >= (SELECT to_date(min(competencia), 'YYYYMM') FROM meta.log_carga WHERE status = 'OK')"
     " GROUP BY 1),"
     " f AS (SELECT * FROM m WHERE mes < (SELECT max(mes) FROM m))"
     " SELECT count(*) FROM f WHERE n < 0.5 * (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY n) FROM f)",
     0, "<=", "meses"),
    ("CNAE sem correspondência no IBGE", "integridade", "gold",
     "SELECT round(100.0 * count(*) FILTER (WHERE secao_cod IS NULL) / NULLIF(count(*),0), 2)"
     " FROM gold.dim_atividade WHERE atividade_sk <> -1", 5, "<=", "%"),
    ("Fato sem UF identificada", "integridade", "gold", PCT_SK_NAO_INFORMADO.format(col="local_sk"), 5, "<=", "%"),
    ("Fato sem atividade identificada", "integridade", "gold", PCT_SK_NAO_INFORMADO.format(col="atividade_sk"), 5, "<=", "%"),
    ("Reconciliação bronze = silver + rejeitados", "consistencia", "bronze->silver",
     "SELECT abs((SELECT count(*) FROM bronze.cat_raw) - (SELECT count(*) FROM silver.cat)"
     " - (SELECT count(*) FROM silver.cat_rejeitada))", 0, "<=", "registros"),
    ("Reconciliação silver = fato", "consistencia", "silver->gold",
     "SELECT abs((SELECT count(*) FROM silver.cat) - (SELECT count(*) FROM gold.fato_cat))", 0, "<=", "registros"),
]


def main():
    conn = conectar()
    resultados = []
    with registrar_etapa(conn, "qualidade"):
        with conn.cursor() as cur:
            for regra, dim, camada, sql, limite, op, unidade in REGRAS:
                cur.execute(sql)
                valor = cur.fetchone()[0]
                valor = float(valor) if valor is not None else 0.0
                ok = valor <= limite if op == "<=" else valor >= limite
                status = "OK" if ok else "ALERTA"
                cur.execute(
                    """INSERT INTO meta.qualidade_resultado
                       (regra, dimensao, camada, valor, limite, unidade, status)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (regra, dim, camada, valor, limite, unidade, status),
                )
                resultados.append((regra, dim, camada, valor, op, limite, unidade, status))
        conn.commit()

    os.makedirs(DOCS, exist_ok=True)
    agora = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    linhas = [
        "# Relatório de qualidade de dados", "", f"Executado em {agora}.", "",
        "| Regra | Dimensão | Camada | Resultado | Limite | Status |",
        "|---|---|---|---|---|---|",
    ]
    for regra, dim, camada, valor, op, limite, unidade, status in resultados:
        linhas.append(f"| {regra} | {dim} | {camada} | {valor:g} {unidade} | {op} {limite:g} | {status} |")
    with open(os.path.join(DOCS, "qualidade.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    for r in resultados:
        print(f"[{r[7]:6}] {r[0]}: {r[3]:g} {r[6]} (limite {r[4]} {r[5]:g})")
    conn.close()


if __name__ == "__main__":
    main()
