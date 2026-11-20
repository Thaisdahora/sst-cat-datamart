# Perfil dos dados brutos (bronze)

Gerado em 18/10/2026 19:59. Total de linhas: **2.008.113**

## Volumetria por arquivo mensal

| Competência | Linhas | Colunas | Encoding | Separador |
|---|---|---|---|---|
| 202306 | 52.831 | 24 | cp1252 | `;` |
| 202307 | 56.281 | 24 | cp1252 | `;` |
| 202308 | 59.606 | 24 | cp1252 | `;` |
| 202309 | 57.024 | 24 | cp1252 | `;` |
| 202310 | 57.455 | 24 | cp1252 | `;` |
| 202311 | 49.952 | 27 | cp1252 | `;` |
| 202312 | 46.045 | 27 | cp1252 | `;` |
| 202401 | 44.261 | 27 | cp1252 | `;` |
| 202402 | 52.394 | 27 | cp1252 | `;` |
| 202403 | 55.226 | 27 | cp1252 | `;` |
| 202404 | 118.987 | 27 | cp1252 | `;` |
| 202405 | 57.990 | 27 | cp1252 | `;` |
| 202406 | 52.023 | 27 | cp1252 | `;` |
| 202407 | 63.969 | 27 | cp1252 | `;` |
| 202408 | 36.464 | 27 | cp1252 | `;` |
| 202409 | 3.379 | 27 | cp1252 | `;` |
| 202410 | 7.459 | 27 | cp1252 | `;` |
| 202411 | 8.088 | 27 | cp1252 | `;` |
| 202412 | 9.731 | 27 | cp1252 | `;` |
| 202501 | 7.276 | 27 | cp1252 | `;` |
| 202502 | 8.913 | 27 | cp1252 | `;` |
| 202503 | 16.825 | 27 | cp1252 | `;` |
| 202504 | 18.271 | 27 | cp1252 | `;` |
| 202505 | 20.562 | 27 | cp1252 | `;` |
| 202506 | 214.745 | 27 | cp1252 | `;` |
| 202507 | 66.528 | 27 | cp1252 | `;` |
| 202508 | 72.885 | 27 | cp1252 | `;` |
| 202509 | 71.483 | 27 | cp1252 | `;` |
| 202510 | 81.904 | 27 | cp1252 | `;` |
| 202511 | 205 | 27 | cp1252 | `;` |
| 202512 | 126 | 27 | cp1252 | `;` |
| 202601 | 53.595 | 27 | cp1252 | `;` |
| 202602 | 65.622 | 27 | cp1252 | `;` |
| 202603 | 72.021 | 27 | cp1252 | `;` |
| 202604 | 74.363 | 27 | cp1252 | `;` |
| 202606 | 140.513 | 27 | cp1252 | `;` |
| 202607 | 65.528 | 27 | cp1252 | `;` |
| 202608 | 67.583 | 27 | cp1252 | `;` |

## Mudanças de layout entre meses

- **202311**: entraram ['cnpj_cei_empregador', 'data_despacho_beneficio', 'data_emissao_cat', 'tipo_de_empregador']; saíram ['data_acidente_3']

## Completude e exemplos por coluna (amostra de até 300 mil linhas)

| Coluna | % vazio | Exemplos |
|---|---|---|
| `agente_causador_acidente` | 0.00 | Edificio - Edificio; Barril, Barrica, Bar; Torre, Poste - Edifi; Painel de Controle, |
| `cbo` | 0.00 | 354130; 773325; 232130; 722330 |
| `cbo_2` | 0.00 | 333105-Inst. de Auto; 324205-Tec. em Patol; 141415-Ger. Loja e S; 371410-Recreador |
| `cid_10` | 0.00 | T261; V031; S258; S799 |
| `cid_10_2` | 0.00 | T20.2 Queim de 2.Gra; B34.2 Infecc p/Coron; T01.8 Ferim Envolv O; F43.2 Transt de Adap |
| `cnae2_0_empregador` | 0.00 | 4753; 3102; 4330; 4632 |
| `cnae2_0_empregador_2` | 0.00 | Confeccao de Pecas d; Captacao, Tratamento; Atividades de Public; Servicos Especializa |
| `cnpj_cei_empregador` | 0.00 | 35683023000122; 46319000000745; 03094629003585; 55344337000108 |
| `data_acidente` | 0.00 | 01/03/2024; 06/03/2024; 19/04/2024; 12/04/2024 |
| `data_acidente_2` | 0.00 | 06/03/2024; 19/04/2024; 19/05/2024; 23/04/2024 |
| `data_afastamento` | 0.00 | 12/04/2024; 30/03/2024; 03/05/2024; 07/05/2024 |
| `data_despacho_beneficio` | 0.00 | 00/00/0000 |
| `data_emissao_cat` | 0.00 | 24/05/2024; 25/05/2024; 20/05/2024; 23/05/2024 |
| `data_nascimento` | 0.00 | 10/05/1966; 16/03/1986; 15/07/2002; 19/03/1998 |
| `emitente_cat` | 0.00 | Segurado/Dependente; Sindicato; Autoridade Pública; Empregador |
| `especie_do_beneficio` | 0.00 | Pa |
| `filiacao_segurado` | 0.00 | Trabalhador Avulso; Empregado |
| `indica_obito_acidente` | 0.00 | Sim; Não |
| `munic_empr` | 0.00 | 352400-Itupeva; 432000-Sapucaia do S; 520840-Goianápolis; 354850-Santos |
| `natureza_da_lesao` | 0.00 | Lesoes Multiplas; Envenenamento Sistem; Queimadura Quimica (; Queimadura ou Escald |
| `origem_de_cadastramento_cat` | 0.00 | Internet |
| `parte_corpo_atingida` | 0.00 | Perna (Do Tornozelo,; Tronco, Parte Multip; Localizacao da Lesao; Pe (Exceto Artelhos) |
| `sexo` | 0.00 | Masculino; Feminino |
| `tipo_de_empregador` | 0.00 | Cnpj/Cgc; {ñ class} |
| `tipo_do_acidente` | 0.00 | Trajeto; Doença; Típico |
| `uf_munic_acidente` | 0.00 | Alagoas; Rondônia; Amazonas; Rio Grande Norte |
| `uf_munic_empregador` | 0.00 | Santa Catarina; Rio Grande do Sul; Mato Grosso; Distrito Federal |
