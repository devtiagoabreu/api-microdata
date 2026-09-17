# Estudo 01 — Visão geral do banco `DBMicrodata_DGB`

> Banco de produção do ERP Microdata. Levantamento feito **somente com leitura** em 17/09/2026.

## Servidor

| Propriedade | Valor |
|---|---|
| Nome lógico do servidor | `microdata-db` (endereço acessado via configuração local `.env`, ver `.env.exemple` do legado) |
| Versão | Microsoft SQL Server 2019 (RTM-CU25) — 15.0.4355.3, Standard Edition (Linux) |
| Banco | `DBMicrodata_DGB` |

## Dimensão do catálogo

| Tipo de objeto | Quantidade |
|---|---|
| Tabelas | 5.003 |
| Views | 530 |
| Procedures | 2.352 |
| Funções (TVF/scalares) | 194 |

## Módulos identificados (prefixos de nomenclatura)

O ERP organiza objetos por módulos, identificados pelo prefixo no nome:

| Prefixo | Módulo | Exemplos |
|---|---|---|
| `Car_*` | Comercial / Carteira de pedidos | `Car_Pedido`, `Car_Itens_Pedido`, `Car_Romaneio` |
| `Cfc_*` | Confecção / Ficha Técnica / faccionistas | `Cfc_Ficha_Tecnica`, `Cfc_Fase`, `Cfc_Faccionista` (via tabelas `Cfc_*`) |
| `Tnt_*` | Tinturaria | `Tnt_*` (processos, receitas, corantes) |
| `Cte_*` | **Controle de tecidos / estoque de peças e rolos** | `Cte_Peca`, `CTE_Baixa` |
| `Rec_*`, `SP_Rec_*` | Recebimento / contas a receber | `SP_Rec_*`, `SP_Recau_*` |
| `Bco_*` | Banco / financeiro | `Bco_Lancamentos`, `Bco_ConciliacaoBancaria` |
| `CCD_*` | Contas a pagar / cheques / duplicatas | `CCD_Remessa`, `CCD_Transacao` |
| `SP_*` | Procedures legadas do ERP (genéricas) | `SP_Rel*`, `SP_Relatorio*`, `SP_Tnt_*` |
| `Adg_*`, `Age_*`, `Alu_*`, `Bib_*`, `Ces_*` | Módulos auxiliares (agenda, escola, biblioteca etc.) | — |

## Objetos usados pela API legada

A API antiga (`docs/legado/oraculum/src/main.py`) consome dois bancos: `DBMicrodata_DGB`
(dados de produção) e `DBProDash` (procedure de faturamento/dashboard). Os objetos de
`DBMicrodata_DGB` usados hoje são a porta de entrada para o domínio da nova API:

| Objeto | Tipo | Uso na API legada |
|---|---|---|
| `Cte_Peca` | tabela | `GET /dados` (estoque de peças/rolos) |
| `CTE_Baixa` | tabela | join anti-rolos-baixados em `GET /dados` e na procedure |
| `Produtos_Tecidos` | tabela | join de linha/produto em `GET /dados` |
| `Vw_Car_Itens_Pedido` | view | base da procedure de sugestão de rolos por pedido |
| `uspEnderecamentoParaAtenderPedidoGeral` | procedure | `GET /sugestao-rolos/{pedido}` e `GET /pdf/sugestao-rolos/{pedido}` |

## Observações

- O catálogo contém também tabelas de sistema/backup (`BKP_*`, `..._Bkp_*`) e temporárias
  (`*_Temp`, `_Log`) que normalmente **não** devem ser expostas por uma API.
- A maioria das colunas é `char` fixo (padrão do ERP, ex.: `char(6)` para produto, `char(10)`
  para rolo). A nova API deve tratar *padding* e valores derivados (ex.: chave composta
  `Nro_Rolo + Situacao + Cor + Desenho`, usada no legado).
- Próximo passo natural: [Estudo 02 — domínio de estoque de peças](./02-dominio-estoque-pecas.md).