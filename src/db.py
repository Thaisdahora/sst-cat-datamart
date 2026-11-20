"""Conexão com o PostgreSQL e utilitários comuns do pipeline."""
import os
import time
import contextlib
import psycopg2


def _env(nome, padrao):
    return os.environ.get(nome, padrao)


def conectar():
    return psycopg2.connect(
        host=_env("POSTGRES_HOST", "localhost"),
        port=int(_env("POSTGRES_PORT", "5432")),
        dbname=_env("POSTGRES_DB", "sst"),
        user=_env("POSTGRES_USER", "sst"),
        password=_env("POSTGRES_PASSWORD", "sst123"),
    )


def executar_arquivo_sql(conn, caminho):
    """Executa um arquivo .sql inteiro dentro de uma transação."""
    with open(caminho, encoding="utf-8") as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


@contextlib.contextmanager
def registrar_etapa(conn, etapa, detalhe=None):
    """Registra início, fim, duração e status de cada etapa em meta.log_execucao."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.log_execucao (etapa, detalhe) VALUES (%s, %s) RETURNING id",
            (etapa, detalhe),
        )
        id_exec = cur.fetchone()[0]
    conn.commit()
    inicio = time.time()
    try:
        yield
    except Exception as e:  # registra a falha e repassa o erro
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE meta.log_execucao SET fim = now(), duracao_s = %s, status = 'ERRO', "
                "mensagem = %s WHERE id = %s",
                (round(time.time() - inicio, 2), str(e)[:2000], id_exec),
            )
        conn.commit()
        raise
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE meta.log_execucao SET fim = now(), duracao_s = %s, status = 'OK' WHERE id = %s",
            (round(time.time() - inicio, 2), id_exec),
        )
    conn.commit()
