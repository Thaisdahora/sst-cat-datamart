# Relatório de qualidade de dados

Executado em 31/10/2026 03:54.

| Regra | Dimensão | Camada | Resultado | Limite | Status |
|---|---|---|---|---|---|
| CNAE do empregador ausente | completude | silver | 2.23 % | <= 5 | OK |
| CBO do acidentado ausente | completude | silver | 0 % | <= 10 | OK |
| Agente causador ausente | completude | silver | 1.59 % | <= 10 | OK |
| Parte do corpo ausente | completude | silver | 0 % | <= 10 | OK |
| UF do empregador ausente | completude | silver | 0 % | <= 5 | OK |
| UF do acidente diferente da UF do empregador | consistencia | silver | 98.68 % | <= 30 | ALERTA |
| Data do acidente inválida (rejeitada) | validade | bronze->silver | 0 % | <= 1 | OK |
| Acidente com data no futuro | validade | silver | 0 registros | <= 0 | OK |
| Acidente posterior à emissão da CAT | consistencia | silver | 0 % | <= 1 | OK |
| Idade fora de 14 a 90 anos | validade | silver | 0 % | <= 2 | OK |
| Duplicados entre arquivos (sobreposição da fonte) | unicidade | bronze->silver | 13.05 % | <= 15 | OK |
| Duplicados dentro do mesmo arquivo | unicidade | bronze->silver | 0.06 % | <= 1 | OK |
| Meses com volume de acidentes abaixo de 50% da mediana | completude | silver | 12 meses | <= 0 | ALERTA |
| CNAE sem correspondência no IBGE | integridade | gold | 0.83 % | <= 5 | OK |
| Fato sem UF identificada | integridade | gold | 2.62 % | <= 5 | OK |
| Fato sem atividade identificada | integridade | gold | 2.23 % | <= 5 | OK |
| Reconciliação bronze = silver + rejeitados | consistencia | bronze->silver | 0 registros | <= 0 | OK |
| Reconciliação silver = fato | consistencia | silver->gold | 0 registros | <= 0 | OK |
