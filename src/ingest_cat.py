"""
Ingestão das Comunicações de Acidente de Trabalho (CAT) publicadas pelo INSS.

Fluxo (camadas landing -> bronze):
  1. Consulta a API CKAN do portal de dados abertos do INSS para descobrir
     os arquivos mensais disponíveis (não usamos URLs fixas, porque o INSS
     já mudou a pasta de armazenamento entre PDA_2023_2025 e PDA_2025_2027).
  2. Baixa cada ZIP mensal para data/landing/ (guarda o arquivo original).
  3. Detecta encoding e separador do CSV, normaliza o nome das colunas.
  4. Grava cada linha inteira como JSONB em bronze.cat_raw, com linhagem
     (competência, arquivo, hash) registrada em meta.log_carga.

Carga incremental: se a competência já foi carregada com o mesmo hash, pula.
Se o INSS republicar o arquivo (hash diferente), substitui a versão anterior.

Uso:
  python src/ingest_cat.py                      # tudo que estiver publicado
  python src/ingest_cat.py --desde 202401       # a partir de jan/2024
  python src/ingest_cat.py --local data/landing # sem internet: usa ZIPs já baixados
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import unicodedata
import zipfile

import requests

sys.path.insert(0, os.path.dirname(__file__))
from db import conectar, registrar_etapa  # noqa: E402
from http_util import get_com_retry  # noqa: E402

CKAN_BASE = os.environ.get("CKAN_BASE", "https://dadosabertos.inss.gov.br")
DATASET_ID = os.environ.get(
    "CKAN_DATASET_ID",
    "comunicacoes-de-acidente-de-trabalho-cat-plano-de-dados-abertos-jun-2023-a-jun-2025",
)
LANDING = os.path.join(os.path.dirname(__file__), "..", "data", "landing")
# Versão da lógica de leitura. Se ela mudar, os meses já carregados são relidos
# automaticamente na próxima execução (mesmo que o arquivo do INSS seja o mesmo).
VERSAO_LEITOR = "2"
RE_COMPETENCIA = re.compile(r"(20\d{2})(0[1-9]|1[0-2])\.(zip|csv)$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Descoberta dos arquivos (API CKAN)
# ---------------------------------------------------------------------------
def listar_recursos_ckan():
    """Retorna [(competencia, url)] a partir do package_show da API CKAN."""
    url = f"{CKAN_BASE}/api/3/action/package_show"
    corpo = get_com_retry(url, params={"id": DATASET_ID}, timeout=60).json()
    if not corpo.get("success"):
        raise RuntimeError(f"API CKAN retornou erro: {corpo.get('error')}")
    recursos = []
    for r in corpo["result"].get("resources", []):
        link = (r.get("url") or "").strip()
        m = RE_COMPETENCIA.search(link.split("?")[0])
        if m:
            recursos.append((m.group(1) + m.group(2), link))
    # remove duplicados mantendo o último publicado para cada competência
    por_comp = {}
    for comp, link in recursos:
        por_comp[comp] = link
    return sorted(por_comp.items())


def listar_arquivos_locais(pasta):
    saida = []
    for nome in sorted(os.listdir(pasta)):
        m = RE_COMPETENCIA.search(nome)
        if m:
            saida.append((m.group(1) + m.group(2), os.path.join(pasta, nome)))
    return saida


# ---------------------------------------------------------------------------
# Leitura do arquivo
# ---------------------------------------------------------------------------
def baixar(url, destino):
    """Baixa para um arquivo temporário e só renomeia no fim, para nunca deixar
    um ZIP pela metade na landing se a conexão cair."""
    temporario = destino + ".parcial"
    try:
        with get_com_retry(url, stream=True, timeout=300) as r:
            with open(temporario, "wb") as f:
                for bloco in r.iter_content(chunk_size=1 << 20):
                    f.write(bloco)
        os.replace(temporario, destino)
    finally:
        if os.path.exists(temporario):
            os.remove(temporario)


def sha256_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def extrair_csv_bytes(caminho):
    """Aceita .zip ou .csv direto.

    O ZIP do INSS traz o mesmo conteúdo em três formatos (.csv, .json e .xml).
    Lemos o .csv, que é o mais compacto. Se não houver .csv, tenta .txt."""
    if caminho.lower().endswith(".zip"):
        with zipfile.ZipFile(caminho) as z:
            arquivos = [i for i in z.infolist() if not i.is_dir()]
            for extensao in (".csv", ".txt"):
                candidatos = [i for i in arquivos if i.filename.lower().endswith(extensao)]
                if candidatos:
                    escolhido = max(candidatos, key=lambda i: i.file_size)
                    return z.read(escolhido), escolhido.filename
            nomes = ", ".join(i.filename for i in arquivos) or "nenhum"
            raise ValueError(f"Nenhum arquivo .csv ou .txt dentro do ZIP {caminho}. Conteúdo: {nomes}")
    with open(caminho, "rb") as f:
        return f.read(), os.path.basename(caminho)


def decodificar(conteudo):
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return conteudo.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise ValueError("Não foi possível decodificar o arquivo")


def detectar_separador(texto):
    amostra = "\n".join(texto.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(amostra, delimiters=";,\t|").delimiter
    except csv.Error:
        return ";"


def normalizar_coluna(nome):
    """'UF  Munic. Acidente' -> 'uf_munic_acidente'"""
    s = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_").lower()
    return s or "coluna_sem_nome"


def ler_linhas(texto, sep):
    leitor = csv.reader(io.StringIO(texto), delimiter=sep)
    cabecalho = next(leitor)
    colunas, vistos = [], {}
    for c in cabecalho:  # garante nomes únicos
        n = normalizar_coluna(c)
        vistos[n] = vistos.get(n, 0) + 1
        colunas.append(n if vistos[n] == 1 else f"{n}_{vistos[n]}")
    linhas = []
    for linha in leitor:
        if not any(v.strip() for v in linha):
            continue  # ignora linhas vazias
        linha = (linha + [""] * len(colunas))[: len(colunas)]
        linhas.append({c: (v.strip() or None) for c, v in zip(colunas, linha)})
    return colunas, linhas


# ---------------------------------------------------------------------------
# Gravação na bronze
# ---------------------------------------------------------------------------
def ja_carregado(cur, competencia):
    cur.execute(
        "SELECT id, sha256, versao_leitor FROM meta.log_carga WHERE competencia = %s AND status = 'OK'",
        (competencia,),
    )
    return cur.fetchone()


def gravar_bronze(conn, competencia, origem, arquivo, sha, enc, sep, colunas, linhas):
    with conn.cursor() as cur:
        anterior = ja_carregado(cur, competencia)
        if anterior and anterior[1] == sha and anterior[2] == VERSAO_LEITOR:
            return "PULADO"
        if anterior:  # republicação pelo INSS ou nova versão do leitor: substitui a anterior
            cur.execute("DELETE FROM bronze.cat_raw WHERE carga_id = %s", (anterior[0],))
            cur.execute("UPDATE meta.log_carga SET status = 'SUBSTITUIDO' WHERE id = %s", (anterior[0],))
        cur.execute(
            """INSERT INTO meta.log_carga
               (competencia, url_origem, arquivo, sha256, linhas, colunas, encoding, separador, versao_leitor, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'OK') RETURNING id""",
            (competencia, origem, arquivo, sha, len(linhas), colunas, enc, sep, VERSAO_LEITOR),
        )
        carga_id = cur.fetchone()[0]
        buffer = io.StringIO()
        escritor = csv.writer(buffer)
        for i, linha in enumerate(linhas, start=1):
            escritor.writerow([carga_id, competencia, i, json.dumps(linha, ensure_ascii=False)])
        buffer.seek(0)
        cur.copy_expert(
            "COPY bronze.cat_raw (carga_id, competencia, linha, dados) FROM STDIN WITH (FORMAT csv)",
            buffer,
        )
    conn.commit()
    return "CARREGADO"


def registrar_falha(conn, competencia, origem, erro):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.log_falha (competencia, url_origem, erro) VALUES (%s, %s, %s)",
            (competencia, origem, f"{type(erro).__name__}: {erro}"[:2000]),
        )
    conn.commit()


def main():
    ap = argparse.ArgumentParser(description="Ingestão da CAT (INSS) para a camada bronze")
    ap.add_argument("--desde", help="competência inicial AAAAMM (opcional)")
    ap.add_argument("--ate", help="competência final AAAAMM (opcional)")
    ap.add_argument("--local", help="pasta com ZIPs já baixados (modo sem internet)")
    args = ap.parse_args()

    os.makedirs(LANDING, exist_ok=True)
    conn = conectar()
    with registrar_etapa(conn, "ingestao_cat", f"desde={args.desde} ate={args.ate} local={args.local}"):
        fontes = listar_arquivos_locais(args.local) if args.local else listar_recursos_ckan()
        fontes = [
            (c, u) for c, u in fontes
            if (not args.desde or c >= args.desde) and (not args.ate or c <= args.ate)
        ]
        print(f"{len(fontes)} arquivo(s) mensal(is) encontrado(s).")
        resumo = {"CARREGADO": 0, "PULADO": 0, "FALHA": 0}
        for competencia, origem in fontes:
            # Cada mês é tratado de forma independente: uma falha (ex.: erro 403 no
            # servidor do INSS) é registrada e o pipeline segue para o próximo mês.
            # O agendador tentará de novo no próximo ciclo.
            try:
                if args.local:
                    caminho = origem
                else:
                    caminho = os.path.join(LANDING, os.path.basename(origem.split("?")[0]))
                    if not os.path.exists(caminho):
                        print(f"  baixando {competencia} ...", flush=True)
                        baixar(origem, caminho)
                sha = sha256_arquivo(caminho)
                conteudo, nome_interno = extrair_csv_bytes(caminho)
                texto, enc = decodificar(conteudo)
                sep = detectar_separador(texto)
                colunas, linhas = ler_linhas(texto, sep)
                status = gravar_bronze(conn, competencia, origem, nome_interno, sha, enc, sep, colunas, linhas)
                resumo[status] += 1
                print(f"  {competencia}: {status} ({len(linhas)} linhas, {len(colunas)} colunas, "
                      f"{nome_interno}, {enc}, sep='{sep}')", flush=True)
            except Exception as e:
                conn.rollback()
                resumo["FALHA"] += 1
                registrar_falha(conn, competencia, origem, e)
                print(f"  {competencia}: FALHA ({type(e).__name__}: {str(e)[:150]})", flush=True)
        print(f"Resumo: {resumo}")
        if resumo["FALHA"] and not (resumo["CARREGADO"] or resumo["PULADO"]):
            raise RuntimeError("Nenhum mês pôde ser carregado. Verifique a conexão e a API do INSS.")
    conn.close()


if __name__ == "__main__":
    main()
