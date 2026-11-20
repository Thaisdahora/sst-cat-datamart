"""
Carrega tabelas de referência da API pública do IBGE (sem chave de acesso):
  - CNAE 2.0, nível de classe, com a hierarquia grupo > divisão > seção
  - Unidades da Federação, com a região

Esses dados enriquecem a CAT: a CAT traz o código CNAE do empregador, e o IBGE
traz a hierarquia completa, permitindo comparar setores em vários níveis.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from db import conectar, registrar_etapa  # noqa: E402
from http_util import get_com_retry  # noqa: E402

IBGE_BASE = os.environ.get("IBGE_BASE", "https://servicodados.ibge.gov.br")


def _get(caminho):
    return get_com_retry(f"{IBGE_BASE}{caminho}").json()


def _so_digitos(valor):
    return "".join(ch for ch in str(valor or "") if ch.isdigit())


def carregar_cnae(cur):
    classes = _get("/api/v2/cnae/classes")
    linhas = []
    for c in classes:
        grupo = c.get("grupo") or {}
        divisao = grupo.get("divisao") or {}
        secao = divisao.get("secao") or {}
        linhas.append((
            _so_digitos(c.get("id")).zfill(5),
            c.get("descricao"),
            _so_digitos(grupo.get("id")).zfill(3) if grupo.get("id") else None,
            grupo.get("descricao"),
            _so_digitos(divisao.get("id")).zfill(2) if divisao.get("id") else None,
            divisao.get("descricao"),
            secao.get("id"),
            secao.get("descricao"),
        ))
    cur.execute("TRUNCATE bronze.ibge_cnae_classe")
    cur.executemany(
        """INSERT INTO bronze.ibge_cnae_classe
           (classe_cod, classe_desc, grupo_cod, grupo_desc, divisao_cod, divisao_desc, secao_cod, secao_desc)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (classe_cod) DO NOTHING""",
        linhas,
    )
    return len(linhas)


def carregar_ufs(cur):
    ufs = _get("/api/v1/localidades/estados")
    linhas = [
        (u["id"], u["sigla"], u["nome"], (u.get("regiao") or {}).get("sigla"), (u.get("regiao") or {}).get("nome"))
        for u in ufs
    ]
    cur.execute("TRUNCATE bronze.ibge_uf")
    cur.executemany(
        "INSERT INTO bronze.ibge_uf (uf_cod, sigla, nome, regiao_sigla, regiao_nome) VALUES (%s,%s,%s,%s,%s)",
        linhas,
    )
    return len(linhas)


def ja_tem_dados(cur, tabela):
    cur.execute(f"SELECT count(*) FROM {tabela}")
    return cur.fetchone()[0] > 0


def main():
    """Carrega cada referência separadamente. Se a API do IBGE estiver fora do ar
    mesmo depois das novas tentativas, mantém a versão já carregada anteriormente
    (dados de referência mudam raramente). Só falha se ainda não houver nenhuma."""
    conn = conectar()
    with registrar_etapa(conn, "referencias_ibge"):
        for nome, funcao, tabela in (("classes CNAE", carregar_cnae, "bronze.ibge_cnae_classe"),
                                     ("UFs", carregar_ufs, "bronze.ibge_uf")):
            try:
                with conn.cursor() as cur:
                    n = funcao(cur)
                conn.commit()
                print(f"IBGE: {n} {nome} carregadas.", flush=True)
            except Exception as e:
                conn.rollback()
                with conn.cursor() as cur:
                    if ja_tem_dados(cur, tabela):
                        print(f"IBGE: falha ao atualizar {nome} ({e}). Mantida a versão já carregada.", flush=True)
                        continue
                raise RuntimeError(f"API do IBGE indisponível e não há {nome} carregadas ainda: {e}") from e
    conn.close()


if __name__ == "__main__":
    main()
