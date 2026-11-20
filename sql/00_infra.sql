-- =====================================================================
-- 00_infra.sql  |  Camadas (schemas) e tabelas de controle do pipeline
-- Arquitetura medalhão: landing (arquivos) -> bronze -> silver -> gold
-- =====================================================================
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE SCHEMA IF NOT EXISTS meta;    -- metadados, linhagem, logs e qualidade
CREATE SCHEMA IF NOT EXISTS bronze;  -- dado bruto, como veio da fonte
CREATE SCHEMA IF NOT EXISTS silver;  -- dado limpo e padronizado
CREATE SCHEMA IF NOT EXISTS gold;    -- modelo dimensional para consumo

-- Log de cada etapa executada
CREATE TABLE IF NOT EXISTS meta.log_execucao (
    id          BIGSERIAL PRIMARY KEY,
    etapa       TEXT NOT NULL,
    detalhe     TEXT,
    inicio      TIMESTAMPTZ NOT NULL DEFAULT now(),
    fim         TIMESTAMPTZ,
    duracao_s   NUMERIC,
    status      TEXT NOT NULL DEFAULT 'EM_EXECUCAO',
    mensagem    TEXT
);

-- Controle de carga incremental: um registro por arquivo mensal carregado
CREATE TABLE IF NOT EXISTS meta.log_carga (
    id              BIGSERIAL PRIMARY KEY,
    competencia     CHAR(6) NOT NULL,          -- AAAAMM do arquivo
    url_origem      TEXT NOT NULL,
    arquivo         TEXT NOT NULL,
    sha256          TEXT NOT NULL,
    linhas          INTEGER,
    colunas         TEXT[],                    -- colunas encontradas (detecta mudança de layout)
    encoding        TEXT,
    separador       TEXT,
    carregado_em    TIMESTAMPTZ NOT NULL DEFAULT now(),
    status          TEXT NOT NULL              -- OK | SUBSTITUIDO
);
CREATE INDEX IF NOT EXISTS ix_log_carga_comp ON meta.log_carga (competencia, status);
-- versão da lógica de leitura usada na carga (permite reprocessar quando o leitor muda)
ALTER TABLE meta.log_carga ADD COLUMN IF NOT EXISTS versao_leitor TEXT;

-- Falhas de download ou leitura de um mês (ex.: erro 403 no servidor do INSS).
-- O mês não entra na bronze e é tentado de novo no próximo ciclo do agendador.
CREATE TABLE IF NOT EXISTS meta.log_falha (
    id           BIGSERIAL PRIMARY KEY,
    competencia  CHAR(6) NOT NULL,
    url_origem   TEXT,
    erro         TEXT,
    ocorrido_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Resultado das regras de qualidade de dados
CREATE TABLE IF NOT EXISTS meta.qualidade_resultado (
    id            BIGSERIAL PRIMARY KEY,
    executado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
    regra         TEXT NOT NULL,
    dimensao      TEXT NOT NULL,     -- completude, validade, unicidade, integridade, consistencia
    camada        TEXT NOT NULL,
    valor         NUMERIC,
    limite        NUMERIC,
    unidade       TEXT,
    status        TEXT NOT NULL      -- OK | ALERTA
);

-- Bronze: cada linha do CSV é guardada inteira em JSONB.
-- Assim, se o INSS mudar o layout (colunas novas ou renomeadas), a carga não quebra.
CREATE TABLE IF NOT EXISTS bronze.cat_raw (
    carga_id     BIGINT NOT NULL REFERENCES meta.log_carga(id),
    competencia  CHAR(6) NOT NULL,
    linha        INTEGER NOT NULL,
    dados        JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_cat_raw_comp ON bronze.cat_raw (competencia);

-- Referências externas (API do IBGE)
CREATE TABLE IF NOT EXISTS bronze.ibge_cnae_classe (
    classe_cod     TEXT PRIMARY KEY,   -- 5 dígitos
    classe_desc    TEXT,
    grupo_cod      TEXT,
    grupo_desc     TEXT,
    divisao_cod    TEXT,
    divisao_desc   TEXT,
    secao_cod      TEXT,
    secao_desc     TEXT,
    carregado_em   TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS bronze.ibge_uf (
    uf_cod        INTEGER PRIMARY KEY,
    sigla         TEXT,
    nome          TEXT,
    regiao_sigla  TEXT,
    regiao_nome   TEXT,
    carregado_em  TIMESTAMPTZ DEFAULT now()
);
