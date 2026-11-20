-- =====================================================================
-- 50_consultas_evidencias.sql | Consultas para tirar os prints do relatório
-- Abra este arquivo no DBeaver (conexão "sst"), clique na consulta desejada
-- e pressione Ctrl+Enter para executar só ela.
-- =====================================================================

-- ---------------------------------------------------------------------
-- SPRINT 1
-- ---------------------------------------------------------------------

-- R3: arquivos mensais descobertos pela API e carregados (linhagem)
SELECT competencia, linhas, status, url_origem, carregado_em
FROM meta.log_carga
ORDER BY competencia;

-- R3: histórico de execuções do pipeline/agendador (mostra a atualização automática)
SELECT id, etapa, inicio, duracao_s, status, mensagem
FROM meta.log_execucao
ORDER BY id DESC
LIMIT 30;

-- R3: total de registros na camada bronze, por mês
SELECT competencia, count(*) AS registros
FROM bronze.cat_raw
GROUP BY competencia
ORDER BY competencia;

-- R3: como um registro bruto é guardado (JSON original do INSS)
SELECT competencia, linha, dados
FROM bronze.cat_raw
LIMIT 5;

-- ---------------------------------------------------------------------
-- SPRINT 2
-- ---------------------------------------------------------------------

-- R4: o mesmo registro antes (bronze) e depois (silver)
SELECT 'bronze' AS camada, r.dados::TEXT AS conteudo
FROM bronze.cat_raw r
WHERE (r.carga_id, r.linha) = (SELECT carga_id, linha FROM silver.cat ORDER BY id_cat LIMIT 1)
UNION ALL
SELECT 'silver', row_to_json(s)::TEXT
FROM (SELECT * FROM silver.cat ORDER BY id_cat LIMIT 1) s;

-- R4: registros rejeitados, por motivo
SELECT motivo, count(*) AS registros
FROM silver.cat_rejeitada
GROUP BY motivo;

-- R4: reconciliação entre camadas (bronze = silver + rejeitados)
SELECT (SELECT count(*) FROM bronze.cat_raw)       AS bronze,
       (SELECT count(*) FROM silver.cat)           AS silver,
       (SELECT count(*) FROM silver.cat_rejeitada) AS rejeitados,
       (SELECT count(*) FROM gold.fato_cat)        AS gold_fato;

-- R4: setores enriquecidos com a hierarquia da CNAE (API do IBGE)
SELECT cnae_digitos, cnae_nome, classe_desc, divisao_cod, divisao_desc, secao_desc
FROM gold.dim_atividade
ORDER BY cnae_digitos
LIMIT 20;

-- R4: tabelas do modelo estrela e quantidade de linhas
SELECT relname AS tabela, n_live_tup AS linhas
FROM pg_stat_user_tables
WHERE schemaname = 'gold'
ORDER BY relname;

-- R5: resultado da última execução das regras de qualidade
SELECT regra, dimensao, camada, valor, unidade, limite, status
FROM meta.qualidade_resultado
WHERE executado_em = (SELECT max(executado_em) FROM meta.qualidade_resultado)
ORDER BY id;

-- ---------------------------------------------------------------------
-- SPRINT 3 (exploração para montar o painel - R6)
-- ---------------------------------------------------------------------

-- Opcional: totais por ano (permite comparar com o Radar SIT)
SELECT t.ano, count(*) AS cats, sum(f.qtd_obito) AS obitos
FROM gold.fato_cat f
JOIN gold.dim_tempo t USING (data_sk)
GROUP BY t.ano
ORDER BY t.ano;

-- Exploração: 10 setores (divisões CNAE) com mais CATs
SELECT a.divisao_cod, a.divisao_desc, count(*) AS cats
FROM gold.fato_cat f
JOIN gold.dim_atividade a USING (atividade_sk)
GROUP BY a.divisao_cod, a.divisao_desc
ORDER BY cats DESC
LIMIT 10;

-- Exploração: benchmarking de um setor (troque '41' pela divisão desejada)
SELECT agente_causador, pct_no_setor, pct_no_brasil, indice_concentracao
FROM gold.vw_benchmark_agente
WHERE divisao_cod = '41'
ORDER BY pct_no_setor DESC
LIMIT 10;

-- ---------------------------------------------------------------------
-- SPRINT 2 (investigação)
-- ---------------------------------------------------------------------

-- Meses com volume de acidentes abaixo de 50% da mediana (detalhe da regra de qualidade)
WITH m AS (
    SELECT date_trunc('month', data_acidente)::date AS mes, count(*) AS cats
    FROM silver.cat
    WHERE data_acidente >= (SELECT to_date(min(competencia), 'YYYYMM') FROM meta.log_carga WHERE status = 'OK')
    GROUP BY 1
), f AS (
    SELECT * FROM m WHERE mes < (SELECT max(mes) FROM m)
), med AS (
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY cats)::numeric AS mediana FROM f
)
SELECT to_char(f.mes, 'YYYY-MM') AS mes_do_acidente, f.cats,
       round(med.mediana) AS mediana,
       round(100.0 * f.cats / med.mediana, 1) AS pct_da_mediana,
       f.cats < 0.5 * med.mediana AS abaixo_do_normal
FROM f, med
ORDER BY f.mes;
