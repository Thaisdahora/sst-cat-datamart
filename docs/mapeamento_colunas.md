# Mapeamento de colunas: CSV da CAT -> campos canônicos

Gerado automaticamente por `src/build_canonical.py`.

| Campo canônico | Descrição | Coluna(s) de origem no CSV |
|---|---|---|
| `agente_causador` | Agente causador do acidente | `agente_causador_acidente` |
| `data_acidente` | Data do acidente | `data_acidente`, `data_acidente_2`, `data_acidente_3` |
| `cbo_codigo` | CBO do acidentado (código ou código-nome) | `cbo` |
| `cbo_nome` | CBO do acidentado (nome) | `cbo_2` |
| `cid_codigo` | CID-10 da lesão (código ou código-nome) | `cid_10` |
| `cid_nome` | CID-10 da lesão (nome) | `cid_10_2` |
| `cnae_codigo` | CNAE 2.0 do empregador (código ou código-nome) | `cnae2_0_empregador` |
| `cnae_nome` | CNAE 2.0 do empregador (nome) | `cnae2_0_empregador_2` |
| `emitente_cat` | Quem emitiu a CAT | `emitente_cat` |
| `especie_beneficio` | Espécie de benefício | `especie_do_beneficio` |
| `filiacao_segurado` | Filiação do segurado | `filiacao_segurado` |
| `indica_obito` | Indica óbito do acidentado | `indica_obito_acidente` |
| `municipio_empregador` | Município do empregador | `munic_empr` |
| `natureza_lesao` | Natureza da lesão | `natureza_da_lesao` |
| `origem_cadastramento` | Origem do cadastramento da CAT | `origem_de_cadastramento_cat` |
| `parte_corpo` | Parte do corpo atingida | `parte_corpo_atingida` |
| `sexo` | Sexo do acidentado | `sexo` |
| `tipo_acidente` | Tipo de acidente (típico, trajeto, doença) | `tipo_do_acidente` |
| `uf_acidente` | UF do município do acidente | `uf_munic_acidente` |
| `uf_empregador` | UF do município do empregador | `uf_munic_empregador` |
| `data_afastamento` | Data do afastamento | `data_afastamento` |
| `data_despacho_beneficio` | Data do despacho do benefício | `data_despacho_beneficio` |
| `data_nascimento` | Data de nascimento do acidentado | `data_nascimento` |
| `data_emissao_cat` | Data de emissão da CAT | `data_emissao_cat` |

## Colunas do CSV sem mapeamento

- `cnpj_cei_empregador`
- `tipo_de_empregador`

## SQL gerado

```sql
CREATE OR REPLACE VIEW bronze.vw_cat_canonica AS
SELECT
    carga_id, competencia, linha,
    dados->>'agente_causador_acidente' AS agente_causador,
    COALESCE(dados->>'data_acidente', dados->>'data_acidente_2', dados->>'data_acidente_3') AS data_acidente,
    dados->>'cbo' AS cbo_codigo,
    dados->>'cbo_2' AS cbo_nome,
    dados->>'cid_10' AS cid_codigo,
    dados->>'cid_10_2' AS cid_nome,
    dados->>'cnae2_0_empregador' AS cnae_codigo,
    dados->>'cnae2_0_empregador_2' AS cnae_nome,
    dados->>'emitente_cat' AS emitente_cat,
    dados->>'especie_do_beneficio' AS especie_beneficio,
    dados->>'filiacao_segurado' AS filiacao_segurado,
    dados->>'indica_obito_acidente' AS indica_obito,
    dados->>'munic_empr' AS municipio_empregador,
    dados->>'natureza_da_lesao' AS natureza_lesao,
    dados->>'origem_de_cadastramento_cat' AS origem_cadastramento,
    dados->>'parte_corpo_atingida' AS parte_corpo,
    dados->>'sexo' AS sexo,
    dados->>'tipo_do_acidente' AS tipo_acidente,
    dados->>'uf_munic_acidente' AS uf_acidente,
    dados->>'uf_munic_empregador' AS uf_empregador,
    dados->>'data_afastamento' AS data_afastamento,
    dados->>'data_despacho_beneficio' AS data_despacho_beneficio,
    dados->>'data_nascimento' AS data_nascimento,
    dados->>'data_emissao_cat' AS data_emissao_cat
FROM bronze.cat_raw;
```
