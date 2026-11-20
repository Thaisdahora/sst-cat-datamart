-- =====================================================================
-- 10_silver.sql  |  Camada silver: dado limpo, tipado e sem duplicidades
-- Entrada: bronze.vw_cat_canonica (gerada por src/build_canonical.py)
-- Saída:   silver.cat  e  silver.cat_rejeitada
-- =====================================================================

-- ---------- Funções utilitárias de limpeza ----------
CREATE OR REPLACE FUNCTION silver.fn_texto(v TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$
    -- tira espaços extras e transforma marcadores de "não classificado" em NULL
    SELECT CASE
        WHEN v IS NULL THEN NULL
        WHEN btrim(v) = '' THEN NULL
        WHEN btrim(v) ~* '^\{?\s*ñ' THEN NULL                                   -- ex.: {ñ class}
        WHEN btrim(v) ~* '^(nao informado|não informado|ignorado|null|-+|0+)$' THEN NULL
        ELSE regexp_replace(btrim(v), '\s+', ' ', 'g')
    END
$$;

CREATE OR REPLACE FUNCTION silver.fn_data(v TEXT) RETURNS DATE
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    s TEXT := btrim(coalesce(v, ''));
    d DATE;
BEGIN
    IF s = '' THEN RETURN NULL; END IF;
    s := split_part(s, ' ', 1);                         -- descarta hora, se houver
    -- Dia ou mês "00" (ex.: 00/00/0000, usado pelo INSS para "sem data") não é uma data.
    -- Sem essa checagem, o PostgreSQL converteria 00/00/0000 para o ano 1 a.C.
    -- e 00/05/2024 para 01/05/2024, sem dar erro.
    IF s ~ '^(00/|\d{2}/00/)' OR s ~ '^\d{4}-(00-|\d{2}-00$)' THEN RETURN NULL; END IF;
    IF s ~ '^\d{2}/\d{2}/\d{4}$' THEN d := to_date(s, 'DD/MM/YYYY');
    ELSIF s ~ '^\d{4}-\d{2}-\d{2}$' THEN d := to_date(s, 'YYYY-MM-DD');
    ELSIF s ~ '^\d{8}$' THEN d := to_date(s, 'YYYYMMDD');
    ELSIF s ~ '^\d{2}/\d{4}$' THEN d := to_date('01/' || s, 'DD/MM/YYYY');
    ELSE RETURN NULL;
    END IF;
    -- datas fora de um intervalo plausível também viram NULL (medidas nas regras de qualidade)
    IF d < DATE '1900-01-01' OR d > DATE '2100-12-31' THEN RETURN NULL; END IF;
    RETURN d;
EXCEPTION WHEN others THEN
    RETURN NULL;                                        -- data impossível (ex.: 31/02) vira NULL
END
$$;

-- separa "717020-Servente de obras" e devolve só o nome
CREATE OR REPLACE FUNCTION silver.fn_nome_apos_codigo(v TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$
    SELECT NULLIF(btrim(regexp_replace(silver.fn_texto(v),
        '^\s*[A-Za-z]?[0-9][0-9./-]*\s*[-–:]?\s*', '')), '')
$$;

-- ---------- Tabela silver ----------
DROP TABLE IF EXISTS silver.cat CASCADE;
DROP TABLE IF EXISTS silver.cat_rejeitada CASCADE;

CREATE TABLE silver.cat AS
WITH base AS (
    SELECT
        c.carga_id,
        c.competencia,
        c.linha,
        silver.fn_data(c.data_acidente)                         AS data_acidente,
        silver.fn_data(c.data_emissao_cat)                      AS data_emissao_cat,
        silver.fn_data(c.data_afastamento)                      AS data_afastamento,
        silver.fn_data(c.data_despacho_beneficio)               AS data_despacho_beneficio,
        silver.fn_data(c.data_nascimento)                       AS data_nascimento,
        -- CNAE: guarda só os dígitos (ex.: 4120-4/00 -> 4120400)
        NULLIF(NULLIF(regexp_replace(coalesce(c.cnae_codigo, ''), '\D', '', 'g'), ''), repeat('0', 7)) AS cnae_digitos_raw,
        upper(coalesce(silver.fn_nome_apos_codigo(c.cnae_nome), silver.fn_nome_apos_codigo(c.cnae_codigo))) AS cnae_nome,
        -- CBO: 6 dígitos
        NULLIF(left(regexp_replace(coalesce(c.cbo_codigo, ''), '\D', '', 'g'), 6), '')          AS cbo_cod_raw,
        upper(coalesce(silver.fn_nome_apos_codigo(c.cbo_nome), silver.fn_nome_apos_codigo(c.cbo_codigo)))   AS cbo_nome,
        -- CID-10: letra + números (ex.: S62.5 -> S625)
        upper(NULLIF(regexp_replace(substring(coalesce(c.cid_codigo, '') from '[A-Za-z][0-9]{2}[.]?[0-9]?'), '[^0-9A-Za-z]', '', 'g'), '')) AS cid_cod,
        upper(coalesce(silver.fn_nome_apos_codigo(c.cid_nome), silver.fn_nome_apos_codigo(c.cid_codigo)))   AS cid_nome,
        upper(silver.fn_texto(c.agente_causador))               AS agente_causador,
        upper(silver.fn_texto(c.parte_corpo))                   AS parte_corpo,
        upper(silver.fn_texto(c.natureza_lesao))                AS natureza_lesao,
        upper(silver.fn_texto(c.tipo_acidente))                 AS tipo_acidente,
        upper(silver.fn_texto(c.emitente_cat))                  AS emitente_cat,
        upper(silver.fn_texto(c.especie_beneficio))             AS especie_beneficio,
        upper(silver.fn_texto(c.filiacao_segurado))             AS filiacao_segurado,
        upper(silver.fn_texto(c.origem_cadastramento))          AS origem_cadastramento,
        upper(silver.fn_texto(c.municipio_empregador))          AS municipio_empregador,
        upper(unaccent(silver.fn_texto(c.uf_acidente)))         AS uf_acidente_txt,
        upper(unaccent(silver.fn_texto(c.uf_empregador)))       AS uf_empregador_txt,
        CASE upper(left(silver.fn_texto(c.sexo), 1))
             WHEN 'M' THEN 'MASCULINO' WHEN 'F' THEN 'FEMININO' END AS sexo,
        CASE WHEN upper(left(btrim(c.indica_obito), 1)) = 'S' THEN TRUE
             WHEN upper(left(btrim(c.indica_obito), 1)) = 'N' THEN FALSE END AS obito
    FROM bronze.vw_cat_canonica c
),
limpo AS (
    -- códigos só com zeros (ex.: 000000) significam "não classificado"
    SELECT b.*,
           CASE WHEN cnae_digitos_raw ~ '^0+$' THEN NULL ELSE cnae_digitos_raw END AS cnae_digitos,
           CASE WHEN cbo_cod_raw      ~ '^0+$' THEN NULL ELSE cbo_cod_raw      END AS cbo_cod
    FROM base b
),
marcado AS (
    SELECT b.*,
           -- impressão digital do registro (todas as colunas de negócio) para achar duplicatas
           md5(concat_ws('|', data_acidente, data_emissao_cat, data_nascimento, cnae_digitos, cbo_cod,
                         cid_cod, agente_causador, parte_corpo, natureza_lesao, tipo_acidente,
                         sexo, uf_acidente_txt, municipio_empregador, obito)) AS hash_registro,
           row_number() OVER (
               PARTITION BY md5(concat_ws('|', data_acidente, data_emissao_cat, data_nascimento, cnae_digitos,
                         cbo_cod, cid_cod, agente_causador, parte_corpo, natureza_lesao, tipo_acidente,
                         sexo, uf_acidente_txt, municipio_empregador, obito))
               ORDER BY competencia, linha) AS ordem_dup
    FROM limpo b
)
SELECT * FROM marcado;

-- Registros rejeitados: duplicados ou sem data do acidente válida
CREATE TABLE silver.cat_rejeitada AS
SELECT *, CASE WHEN ordem_dup > 1 THEN 'DUPLICADO' ELSE 'DATA_ACIDENTE_INVALIDA' END AS motivo
FROM silver.cat
WHERE ordem_dup > 1 OR data_acidente IS NULL;

DELETE FROM silver.cat WHERE ordem_dup > 1 OR data_acidente IS NULL;
ALTER TABLE silver.cat DROP COLUMN ordem_dup, DROP COLUMN cnae_digitos_raw, DROP COLUMN cbo_cod_raw;
ALTER TABLE silver.cat ADD COLUMN id_cat BIGSERIAL PRIMARY KEY;

CREATE INDEX ix_silver_cat_data  ON silver.cat (data_acidente);
CREATE INDEX ix_silver_cat_cnae  ON silver.cat (cnae_digitos);
ANALYZE silver.cat;
