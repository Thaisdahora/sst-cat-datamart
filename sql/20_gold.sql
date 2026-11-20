-- =====================================================================
-- 20_gold.sql  |  Camada gold: modelo dimensional (estrela)
-- Grão da fato: 1 linha = 1 CAT (comunicação de acidente de trabalho)
-- Toda dimensão tem o membro -1 'NÃO INFORMADO' para nunca perder linhas.
-- =====================================================================
DROP SCHEMA IF EXISTS gold CASCADE;
CREATE SCHEMA gold;

-- ---------------- dim_tempo ----------------
CREATE TABLE gold.dim_tempo AS
SELECT
    to_char(d, 'YYYYMMDD')::INT                    AS data_sk,
    d::DATE                                        AS data,
    EXTRACT(YEAR FROM d)::INT                      AS ano,
    EXTRACT(QUARTER FROM d)::INT                   AS trimestre,
    EXTRACT(MONTH FROM d)::INT                     AS mes,
    (ARRAY['JAN','FEV','MAR','ABR','MAI','JUN','JUL','AGO','SET','OUT','NOV','DEZ'])[EXTRACT(MONTH FROM d)::INT] AS nome_mes,
    to_char(d, 'YYYY-MM')                          AS ano_mes,
    EXTRACT(ISODOW FROM d)::INT                    AS dia_semana,
    (ARRAY['SEG','TER','QUA','QUI','SEX','SAB','DOM'])[EXTRACT(ISODOW FROM d)::INT] AS nome_dia_semana,
    EXTRACT(ISODOW FROM d) IN (6, 7)               AS fim_de_semana
FROM generate_series(
        (SELECT date_trunc('year', min(data_acidente)) FROM silver.cat),
        (SELECT max(data_acidente) FROM silver.cat),
        INTERVAL '1 day') AS d;
ALTER TABLE gold.dim_tempo ADD PRIMARY KEY (data_sk);

-- Situação da publicação de cada mês (Sprint 2). A investigação mostrou meses em que o
-- INSS publicou muito menos CATs do que o normal (ex.: set/2024 a fev/2025, nov e dez/2025).
-- Sem essa marcação, o painel sugeriria quedas de acidentes que não aconteceram.
--   COMPLETA          volume normal
--   INCOMPLETA        volume abaixo de 50% da mediana mensal, ou o último mês (ainda em aberto)
--   FORA DA COBERTURA meses anteriores ao primeiro arquivo carregado (só há acidentes comunicados com atraso)
-- A regra é recalculada a cada carga: se o INSS republicar um mês completo, ele deixa de ser marcado.
ALTER TABLE gold.dim_tempo
    ADD COLUMN situacao_publicacao TEXT,
    ADD COLUMN publicacao_incompleta BOOLEAN;

WITH m AS (
    SELECT date_trunc('month', data_acidente)::date AS mes, count(*) AS n
    FROM silver.cat GROUP BY 1
), ini AS (
    SELECT to_date(min(competencia), 'YYYYMM') AS d FROM meta.log_carga WHERE status = 'OK'
), fim AS (
    SELECT max(mes) AS d FROM m
), med AS (
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY m.n) AS v
    FROM m, ini, fim WHERE m.mes >= ini.d AND m.mes < fim.d
), sit AS (
    SELECT m.mes,
           CASE WHEN m.mes < ini.d          THEN 'FORA DA COBERTURA'
                WHEN m.mes >= fim.d         THEN 'INCOMPLETA'
                WHEN m.n < 0.5 * med.v      THEN 'INCOMPLETA'
                ELSE 'COMPLETA' END AS situacao
    FROM m, ini, fim, med
)
UPDATE gold.dim_tempo t
SET situacao_publicacao = sit.situacao
FROM sit
WHERE date_trunc('month', t.data)::date = sit.mes;

-- meses sem nenhum registro: fora da cobertura se forem anteriores ao primeiro arquivo; senão, incompletos
UPDATE gold.dim_tempo
SET situacao_publicacao = CASE
        WHEN data < (SELECT to_date(min(competencia), 'YYYYMM') FROM meta.log_carga WHERE status = 'OK')
        THEN 'FORA DA COBERTURA' ELSE 'INCOMPLETA' END
WHERE situacao_publicacao IS NULL;
UPDATE gold.dim_tempo SET publicacao_incompleta = (situacao_publicacao <> 'COMPLETA');

-- ---------------- dim_atividade (CNAE + hierarquia IBGE) ----------------
CREATE TABLE gold.dim_atividade (
    atividade_sk   SERIAL PRIMARY KEY,
    cnae_digitos   TEXT UNIQUE,
    cnae_nome      TEXT,
    classe_cod     TEXT,
    classe_desc    TEXT,
    grupo_desc     TEXT,
    divisao_cod    TEXT,
    divisao_desc   TEXT,
    secao_cod      TEXT,
    secao_desc     TEXT
);
INSERT INTO gold.dim_atividade (atividade_sk, cnae_digitos, cnae_nome, divisao_desc, secao_desc)
OVERRIDING SYSTEM VALUE VALUES (-1, NULL, 'NÃO INFORMADO', 'NÃO INFORMADO', 'NÃO INFORMADO');

WITH divisoes AS (
    SELECT DISTINCT divisao_cod, divisao_desc, secao_cod, secao_desc FROM bronze.ibge_cnae_classe
), codigos AS (
    SELECT cnae_digitos, max(cnae_nome) AS cnae_nome
    FROM silver.cat WHERE cnae_digitos IS NOT NULL GROUP BY cnae_digitos
)
INSERT INTO gold.dim_atividade (cnae_digitos, cnae_nome, classe_cod, classe_desc, grupo_desc,
                                divisao_cod, divisao_desc, secao_cod, secao_desc)
SELECT c.cnae_digitos,
       -- prefere a descrição oficial do IBGE: no arquivo do INSS ela vem cortada em 20 caracteres
       coalesce(upper(k.classe_desc), c.cnae_nome, 'SEM DESCRIÇÃO'),
       k.classe_cod, upper(k.classe_desc), upper(k.grupo_desc),
       left(c.cnae_digitos, 2),
       upper(coalesce(d.divisao_desc, 'DIVISÃO ' || left(c.cnae_digitos, 2))),
       d.secao_cod, upper(coalesce(d.secao_desc, 'NÃO IDENTIFICADA'))
FROM codigos c
-- a classe CNAE tem 5 dígitos (4 + dígito verificador); os 4 primeiros já a identificam
LEFT JOIN bronze.ibge_cnae_classe k ON length(c.cnae_digitos) >= 4 AND left(k.classe_cod, 4) = left(c.cnae_digitos, 4)
LEFT JOIN divisoes d               ON d.divisao_cod = left(c.cnae_digitos, 2);

-- ---------------- dim_ocupacao (CBO) ----------------
CREATE TABLE gold.dim_ocupacao (
    ocupacao_sk        SERIAL PRIMARY KEY,
    cbo_cod            TEXT UNIQUE,
    cbo_nome           TEXT,
    grande_grupo_cod   TEXT,
    grande_grupo_desc  TEXT
);
INSERT INTO gold.dim_ocupacao (ocupacao_sk, cbo_nome, grande_grupo_desc)
OVERRIDING SYSTEM VALUE VALUES (-1, 'NÃO INFORMADO', 'NÃO INFORMADO');
INSERT INTO gold.dim_ocupacao (cbo_cod, cbo_nome, grande_grupo_cod, grande_grupo_desc)
SELECT cbo_cod, coalesce(max(cbo_nome), 'SEM DESCRIÇÃO'), left(cbo_cod, 1),
       CASE left(cbo_cod, 1)
         WHEN '0' THEN 'MEMBROS DAS FORÇAS ARMADAS, POLICIAIS E BOMBEIROS MILITARES'
         WHEN '1' THEN 'DIRIGENTES E GERENTES'
         WHEN '2' THEN 'PROFISSIONAIS DAS CIÊNCIAS E DAS ARTES'
         WHEN '3' THEN 'TÉCNICOS DE NÍVEL MÉDIO'
         WHEN '4' THEN 'TRABALHADORES DE SERVIÇOS ADMINISTRATIVOS'
         WHEN '5' THEN 'TRABALHADORES DOS SERVIÇOS E VENDEDORES'
         WHEN '6' THEN 'TRABALHADORES AGROPECUÁRIOS, FLORESTAIS E DA PESCA'
         WHEN '7' THEN 'TRABALHADORES DA PRODUÇÃO DE BENS E SERVIÇOS INDUSTRIAIS (7)'
         WHEN '8' THEN 'TRABALHADORES DA PRODUÇÃO DE BENS E SERVIÇOS INDUSTRIAIS (8)'
         WHEN '9' THEN 'TRABALHADORES EM SERVIÇOS DE REPARAÇÃO E MANUTENÇÃO'
       END
FROM silver.cat WHERE cbo_cod IS NOT NULL GROUP BY cbo_cod;

-- ---------------- dim_lesao_cid (CID-10) ----------------
CREATE TABLE gold.dim_cid (
    cid_sk        SERIAL PRIMARY KEY,
    cid_cod       TEXT UNIQUE,
    cid_nome      TEXT,
    cid_letra     TEXT
);
INSERT INTO gold.dim_cid (cid_sk, cid_nome) OVERRIDING SYSTEM VALUE VALUES (-1, 'NÃO INFORMADO');
INSERT INTO gold.dim_cid (cid_cod, cid_nome, cid_letra)
SELECT cid_cod, coalesce(max(cid_nome), 'SEM DESCRIÇÃO'), left(cid_cod, 1)
FROM silver.cat WHERE cid_cod IS NOT NULL GROUP BY cid_cod;

-- ---------------- dimensões descritivas simples ----------------
CREATE TABLE gold.dim_agente_causador (agente_sk SERIAL PRIMARY KEY, agente_causador TEXT UNIQUE);
INSERT INTO gold.dim_agente_causador VALUES (-1, 'NÃO INFORMADO');
INSERT INTO gold.dim_agente_causador (agente_causador)
SELECT DISTINCT agente_causador FROM silver.cat WHERE agente_causador IS NOT NULL
ON CONFLICT DO NOTHING;

CREATE TABLE gold.dim_parte_corpo (parte_corpo_sk SERIAL PRIMARY KEY, parte_corpo TEXT UNIQUE);
INSERT INTO gold.dim_parte_corpo VALUES (-1, 'NÃO INFORMADO');
INSERT INTO gold.dim_parte_corpo (parte_corpo)
SELECT DISTINCT parte_corpo FROM silver.cat WHERE parte_corpo IS NOT NULL
ON CONFLICT DO NOTHING;

CREATE TABLE gold.dim_natureza_lesao (natureza_sk SERIAL PRIMARY KEY, natureza_lesao TEXT UNIQUE);
INSERT INTO gold.dim_natureza_lesao VALUES (-1, 'NÃO INFORMADO');
INSERT INTO gold.dim_natureza_lesao (natureza_lesao)
SELECT DISTINCT natureza_lesao FROM silver.cat WHERE natureza_lesao IS NOT NULL
ON CONFLICT DO NOTHING;

CREATE TABLE gold.dim_tipo_acidente (tipo_acidente_sk SERIAL PRIMARY KEY, tipo_acidente TEXT UNIQUE);
INSERT INTO gold.dim_tipo_acidente VALUES (-1, 'NÃO INFORMADO');
INSERT INTO gold.dim_tipo_acidente (tipo_acidente)
SELECT DISTINCT tipo_acidente FROM silver.cat WHERE tipo_acidente IS NOT NULL
ON CONFLICT DO NOTHING;

-- ---------------- dim_local (UF do empregador + região, via IBGE) ----------------
-- Usa a UF do empregador. Na análise dos dados reais, o campo "UF Munic. Acidente"
-- se mostrou pouco confiável (muitos "{ñ class}" e UFs incompatíveis com o município
-- do empregador). A divergência é medida em uma regra de qualidade.
CREATE TABLE gold.dim_local (
    local_sk     SERIAL PRIMARY KEY,
    uf_sigla     TEXT UNIQUE,
    uf_nome      TEXT,
    regiao_nome  TEXT
);
INSERT INTO gold.dim_local VALUES (-1, NULL, 'NÃO INFORMADO', 'NÃO INFORMADO');
INSERT INTO gold.dim_local (uf_sigla, uf_nome, regiao_nome)
SELECT sigla, upper(nome), upper(regiao_nome) FROM bronze.ibge_uf;

-- ---------------- dim_perfil (sexo x faixa etária) ----------------
CREATE TABLE gold.dim_perfil (
    perfil_sk     SERIAL PRIMARY KEY,
    sexo          TEXT,
    faixa_etaria  TEXT,
    UNIQUE (sexo, faixa_etaria)
);
INSERT INTO gold.dim_perfil (sexo, faixa_etaria)
SELECT s, f
FROM unnest(ARRAY['MASCULINO','FEMININO','NÃO INFORMADO']) s
CROSS JOIN unnest(ARRAY['ATÉ 17','18-24','25-34','35-44','45-54','55-64','65+','NÃO INFORMADO']) f;

-- ---------------- fato_cat ----------------
CREATE TABLE gold.fato_cat AS
WITH c AS (
    SELECT s.*,
           CASE WHEN s.data_nascimento IS NOT NULL
                THEN date_part('year', age(s.data_acidente, s.data_nascimento))::INT END AS idade
    FROM silver.cat s
)
SELECT
    c.id_cat,
    c.competencia,
    to_char(c.data_acidente, 'YYYYMMDD')::INT                     AS data_sk,
    coalesce(a.atividade_sk, -1)                                  AS atividade_sk,
    coalesce(o.ocupacao_sk, -1)                                   AS ocupacao_sk,
    coalesce(ci.cid_sk, -1)                                       AS cid_sk,
    coalesce(ag.agente_sk, -1)                                    AS agente_sk,
    coalesce(pc.parte_corpo_sk, -1)                               AS parte_corpo_sk,
    coalesce(nl.natureza_sk, -1)                                  AS natureza_sk,
    coalesce(ta.tipo_acidente_sk, -1)                             AS tipo_acidente_sk,
    coalesce(l.local_sk, -1)                                      AS local_sk,
    p.perfil_sk,
    1                                                             AS qtd_cat,
    CASE WHEN c.obito THEN 1 ELSE 0 END                           AS qtd_obito,
    c.idade,
    (c.data_emissao_cat - c.data_acidente)                        AS dias_ate_emissao
FROM c
LEFT JOIN gold.dim_atividade       a  ON a.cnae_digitos   = c.cnae_digitos
LEFT JOIN gold.dim_ocupacao        o  ON o.cbo_cod        = c.cbo_cod
LEFT JOIN gold.dim_cid             ci ON ci.cid_cod       = c.cid_cod
LEFT JOIN gold.dim_agente_causador ag ON ag.agente_causador = c.agente_causador
LEFT JOIN gold.dim_parte_corpo     pc ON pc.parte_corpo   = c.parte_corpo
LEFT JOIN gold.dim_natureza_lesao  nl ON nl.natureza_lesao = c.natureza_lesao
LEFT JOIN gold.dim_tipo_acidente   ta ON ta.tipo_acidente = c.tipo_acidente
LEFT JOIN gold.dim_local           l  ON c.uf_empregador_txt IN (l.uf_sigla, upper(unaccent(l.uf_nome)))
JOIN gold.dim_perfil               p  ON p.sexo = coalesce(c.sexo, 'NÃO INFORMADO')
                                     AND p.faixa_etaria = CASE
                                         WHEN c.idade IS NULL OR c.idade NOT BETWEEN 10 AND 100 THEN 'NÃO INFORMADO'
                                         WHEN c.idade < 18 THEN 'ATÉ 17'
                                         WHEN c.idade < 25 THEN '18-24'
                                         WHEN c.idade < 35 THEN '25-34'
                                         WHEN c.idade < 45 THEN '35-44'
                                         WHEN c.idade < 55 THEN '45-54'
                                         WHEN c.idade < 65 THEN '55-64'
                                         ELSE '65+' END;

ALTER TABLE gold.fato_cat ADD PRIMARY KEY (id_cat);
ALTER TABLE gold.fato_cat
    ADD FOREIGN KEY (data_sk)          REFERENCES gold.dim_tempo,
    ADD FOREIGN KEY (atividade_sk)     REFERENCES gold.dim_atividade,
    ADD FOREIGN KEY (ocupacao_sk)      REFERENCES gold.dim_ocupacao,
    ADD FOREIGN KEY (cid_sk)           REFERENCES gold.dim_cid,
    ADD FOREIGN KEY (agente_sk)        REFERENCES gold.dim_agente_causador,
    ADD FOREIGN KEY (parte_corpo_sk)   REFERENCES gold.dim_parte_corpo,
    ADD FOREIGN KEY (natureza_sk)      REFERENCES gold.dim_natureza_lesao,
    ADD FOREIGN KEY (tipo_acidente_sk) REFERENCES gold.dim_tipo_acidente,
    ADD FOREIGN KEY (local_sk)         REFERENCES gold.dim_local,
    ADD FOREIGN KEY (perfil_sk)        REFERENCES gold.dim_perfil;
CREATE INDEX ix_fato_data      ON gold.fato_cat (data_sk);
CREATE INDEX ix_fato_atividade ON gold.fato_cat (atividade_sk);
ANALYZE gold.fato_cat;

-- =====================================================================
-- Visões de consumo (para o BI e para consultas no DBeaver)
-- =====================================================================

-- Visão "larga" com todos os atributos: facilita consultas e exportações sem JOIN
CREATE VIEW gold.vw_cat_analitica AS
SELECT f.id_cat, t.data, t.ano, t.mes, t.ano_mes, t.nome_dia_semana, t.fim_de_semana,
       t.situacao_publicacao, t.publicacao_incompleta,
       a.secao_desc, a.divisao_cod, a.divisao_desc, a.cnae_digitos, a.cnae_nome,
       o.cbo_cod, o.cbo_nome, o.grande_grupo_desc,
       ci.cid_cod, ci.cid_nome,
       ag.agente_causador, pc.parte_corpo, nl.natureza_lesao, ta.tipo_acidente,
       l.uf_sigla, l.uf_nome, l.regiao_nome,
       p.sexo, p.faixa_etaria,
       f.qtd_cat, f.qtd_obito, f.idade, f.dias_ate_emissao
FROM gold.fato_cat f
JOIN gold.dim_tempo t            USING (data_sk)
JOIN gold.dim_atividade a        USING (atividade_sk)
JOIN gold.dim_ocupacao o         USING (ocupacao_sk)
JOIN gold.dim_cid ci             USING (cid_sk)
JOIN gold.dim_agente_causador ag USING (agente_sk)
JOIN gold.dim_parte_corpo pc     USING (parte_corpo_sk)
JOIN gold.dim_natureza_lesao nl  USING (natureza_sk)
JOIN gold.dim_tipo_acidente ta   USING (tipo_acidente_sk)
JOIN gold.dim_local l            USING (local_sk)
JOIN gold.dim_perfil p           USING (perfil_sk);

-- Benchmarking: quanto cada agente causador pesa no setor (divisão CNAE) vs. no Brasil.
-- indice_concentracao > 1 significa que o agente é mais frequente no setor do que na média nacional.
CREATE VIEW gold.vw_benchmark_agente AS
WITH setor AS (
    SELECT a.divisao_cod, a.divisao_desc, f.agente_sk, count(*) AS cats_setor
    FROM gold.fato_cat f JOIN gold.dim_atividade a USING (atividade_sk)
    GROUP BY 1, 2, 3
), tot_setor AS (
    SELECT divisao_cod, sum(cats_setor) AS total_setor FROM setor GROUP BY 1
), brasil AS (
    SELECT agente_sk, count(*)::NUMERIC / (SELECT count(*) FROM gold.fato_cat) AS share_brasil
    FROM gold.fato_cat GROUP BY 1
)
SELECT s.divisao_cod, s.divisao_desc, ag.agente_causador, s.cats_setor,
       round(100.0 * s.cats_setor / t.total_setor, 2)              AS pct_no_setor,
       round(100.0 * b.share_brasil, 2)                            AS pct_no_brasil,
       round((s.cats_setor::NUMERIC / t.total_setor) / NULLIF(b.share_brasil, 0), 2) AS indice_concentracao
FROM setor s
JOIN tot_setor t USING (divisao_cod)
JOIN brasil b    USING (agente_sk)
JOIN gold.dim_agente_causador ag USING (agente_sk);
