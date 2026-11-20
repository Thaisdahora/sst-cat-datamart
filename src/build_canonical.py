"""
Gera a visão bronze.vw_cat_canonica, que traduz as colunas brutas da CAT
(guardadas em JSONB) para nomes padronizados usados pelas camadas seguintes.

Por que isso existe: os nomes das colunas no CSV do INSS podem variar entre
meses (acentos, abreviações, colunas novas). Em vez de "chumbar" nomes no SQL,
cada campo canônico é encontrado por regras (expressões regulares) aplicadas
às colunas registradas em meta.log_carga. Se mais de uma coluna corresponder
(por exemplo, um nome antigo e um novo), elas são combinadas com COALESCE.

O resultado do mapeamento é documentado em docs/mapeamento_colunas.md,
que serve de evidência e de dicionário de dados.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from db import conectar, registrar_etapa  # noqa: E402

DOCS = os.path.join(os.path.dirname(__file__), "..", "docs")

# campo canônico -> (regex de inclusão, regex de exclusão ou None, descrição)
REGRAS = [
    ("agente_causador",        r"agente", None, "Agente causador do acidente"),
    ("data_acidente",          r"^(data|dt)_?(do_)?acidente", r"munic|uf", "Data do acidente"),
    ("cbo_codigo",             r"cbo", r"nome|desc", "CBO do acidentado (código ou código-nome)"),
    ("cbo_nome",               r"cbo.*(nome|desc)", None, "CBO do acidentado (nome)"),
    ("cid_codigo",             r"(^|_)cid(_|$)", r"nome|desc", "CID-10 da lesão (código ou código-nome)"),
    ("cid_nome",               r"(^|_)cid_.*(nome|desc)", None, "CID-10 da lesão (nome)"),
    ("cnae_codigo",            r"cnae", r"nome|desc", "CNAE 2.0 do empregador (código ou código-nome)"),
    ("cnae_nome",              r"cnae.*(nome|desc)", None, "CNAE 2.0 do empregador (nome)"),
    ("emitente_cat",           r"emitente", None, "Quem emitiu a CAT"),
    ("especie_beneficio",      r"especie", None, "Espécie de benefício"),
    ("filiacao_segurado",      r"filiacao", None, "Filiação do segurado"),
    ("indica_obito",           r"obito", None, "Indica óbito do acidentado"),
    ("municipio_empregador",   r"munic.*empr", r"^uf", "Município do empregador"),
    ("natureza_lesao",         r"natureza", None, "Natureza da lesão"),
    ("origem_cadastramento",   r"origem", None, "Origem do cadastramento da CAT"),
    ("parte_corpo",            r"parte.*corpo", None, "Parte do corpo atingida"),
    ("sexo",                   r"^sexo", None, "Sexo do acidentado"),
    ("tipo_acidente",          r"tipo.*acidente", None, "Tipo de acidente (típico, trajeto, doença)"),
    ("uf_acidente",            r"uf.*acidente", None, "UF do município do acidente"),
    ("uf_empregador",          r"uf.*empregador", None, "UF do município do empregador"),
    ("data_afastamento",       r"afastamento", None, "Data do afastamento"),
    ("data_despacho_beneficio", r"despacho|ddb", None, "Data do despacho do benefício"),
    ("data_nascimento",        r"nascimento", None, "Data de nascimento do acidentado"),
    ("data_emissao_cat",       r"emissao", None, "Data de emissão da CAT"),
]


def colunas_observadas(cur):
    cur.execute(
        "SELECT DISTINCT unnest(colunas) FROM meta.log_carga WHERE status = 'OK' ORDER BY 1"
    )
    return [r[0] for r in cur.fetchall()]


def mapear(colunas):
    mapa, usadas = {}, set()
    for campo, inc, exc, _ in REGRAS:
        achadas = [
            c for c in colunas
            if re.search(inc, c) and not (exc and re.search(exc, c))
        ]
        mapa[campo] = achadas
        usadas.update(achadas)
    # No arquivo do INSS, CBO, CID-10 e CNAE aparecem duas vezes com o mesmo nome:
    # a primeira coluna traz só o código e a segunda traz código e descrição
    # (ex.: "513405" e "513405-Garçom"). Quando não existe uma coluna "nome"
    # explícita, a primeira vira o código e as demais viram o nome.
    for base in ("cbo", "cid", "cnae"):
        codigo, nome = f"{base}_codigo", f"{base}_nome"
        if not mapa[nome] and len(mapa[codigo]) >= 2:
            mapa[nome] = mapa[codigo][1:]
            mapa[codigo] = mapa[codigo][:1]
    nao_mapeadas = [c for c in colunas if c not in usadas]
    return mapa, nao_mapeadas


def gerar_sql(mapa):
    partes = []
    for campo, _, _, _ in REGRAS:
        chaves = mapa[campo]
        if not chaves:
            expr = "NULL::text"
        elif len(chaves) == 1:
            expr = f"dados->>'{chaves[0]}'"
        else:
            expr = "COALESCE(" + ", ".join(f"dados->>'{c}'" for c in chaves) + ")"
        partes.append(f"    {expr} AS {campo}")
    return (
        "CREATE OR REPLACE VIEW bronze.vw_cat_canonica AS\nSELECT\n"
        "    carga_id, competencia, linha,\n" + ",\n".join(partes) + "\nFROM bronze.cat_raw;"
    )


def documentar(mapa, nao_mapeadas, sql):
    os.makedirs(DOCS, exist_ok=True)
    linhas = [
        "# Mapeamento de colunas: CSV da CAT -> campos canônicos",
        "",
        "Gerado automaticamente por `src/build_canonical.py`.",
        "",
        "| Campo canônico | Descrição | Coluna(s) de origem no CSV |",
        "|---|---|---|",
    ]
    for campo, _, _, desc in REGRAS:
        origem = ", ".join(f"`{c}`" for c in mapa[campo]) or "**não encontrada**"
        linhas.append(f"| `{campo}` | {desc} | {origem} |")
    linhas += ["", "## Colunas do CSV sem mapeamento", ""]
    linhas += [f"- `{c}`" for c in nao_mapeadas] or ["- nenhuma"]
    linhas += ["", "## SQL gerado", "", "```sql", sql, "```", ""]
    with open(os.path.join(DOCS, "mapeamento_colunas.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))


def main():
    conn = conectar()
    with registrar_etapa(conn, "visao_canonica"):
        with conn.cursor() as cur:
            colunas = colunas_observadas(cur)
            if not colunas:
                raise RuntimeError("Nenhuma carga encontrada. Rode a ingestão primeiro.")
            mapa, nao_mapeadas = mapear(colunas)
            sql = gerar_sql(mapa)
            cur.execute("DROP VIEW IF EXISTS bronze.vw_cat_canonica CASCADE")
            cur.execute(sql)
        conn.commit()
        documentar(mapa, nao_mapeadas, sql)
        faltando = [c for c, v in mapa.items() if not v]
        print(f"Visão canônica criada. Campos sem origem: {faltando or 'nenhum'}")
        if nao_mapeadas:
            print(f"Colunas do CSV não usadas: {nao_mapeadas}")
    conn.close()


if __name__ == "__main__":
    main()
