# Estudo 40 — Painel de Relatórios e Dashboards (RPT / `rpt_*`, `SRPT_*`, `Rel_*`)

> **Data:** 19/set/2026
> **Escopo:** Módulo **SIMRPT / Painel** — motor de dashboards e relatórios do desktop EXE (config metadata + procedures `SRPT_*`); relatórios de inventário `Rel_*` (pertencentes ao módulo Estoque).
> **Restrições:** apenas leitura; sem objetos novos em produção.
> **Relações:** Estudos 06 (Faturamento/NF), 08 (Vendas/PCP), 11 (Financeiro), 16 (Estoque), 36 (Custos/MCG), 39 (Compras).

---

## 1. Identidade

O prefixo `rpt_*` contém o **framework genérico de dashboards do painel de relatórios** (ex-executável Java/.NET da Microdata). 52 tabelas, 28 procs `SRPT_*` (report SQL) e 5 procs `Rel_*` de inventário.

- **Módulo efetivamente parado** desde **07/2020** — todos os `rpt_dashboard_data.ultima_atualizacao` congelados em `2020-05-06 21:0x`; log de erros (`rpt_log`) encerra em `2020-05-06 21:15:00` (236.827 erros, 100% `NullPointerException` Java).
- As **procedures `SRPT_*`** permanecem ativas no banco e contêm as **definições de cálculo dos indicadores** de Faturamento, Vendas, Financeiro, Bonificação, Previsão, Fluxo Futuro, Custo Fixo etc. → **referência para a nova API**.

---

## 2. Componentes

### 2.1 Filtros (`rpt_filtros`, 86) — áreas de análise

Cada "página" de relatório tem um **filtro** com tipo: **FAT** (54, faturamento), **VEN** (18, vendas), **FIN** (9, financeiro), **PRO** (5, produção).

Exemplos de filtros ativos:

| id | Descrição | Tipo |
|----|-----------|------|
| 3 | Geral | FAT |
| 4 | Geral por Quantidade | FAT |
| 6 | Por Produto | FAT |
| 11 | Por Representante | FAT |
| 14 | Posição Final | FIN |
| 15 | Resumo Pagar/Receber | FIN |
| 25 | Posição de Saldo | FIN |
| 31 | Faturamento Anual | FAT |
| 36 | Por Representante - Vendas | VEN |
| 43 | Gestão de Clientes | FAT |
| 60 | Inadimplência Receber | FIN |
| 75/76 | Curva ABC Cliente/Produto | FAT |
| 82 | Inadimplência Receber (detalhe) | FIN |
| 15003 | Fluxo Futuro | FAT |
| 15008 | Custo Fixo Comparativo Anual | FAT |
| 15012 | Relatório Devolução Anual | FAT |
| 15013 | Prazo Médio de Faturamento | FAT |

### 2.2 Procedimentos (`rpt_procedimentos`, 26)

Registra as procedures SQL que produzem o result-set de cada relatório. Colunas: `id_procedimento, descricao, procedimento (nomedb), tipo_filtro, ativo, execucao (string de execução original EXE), deleted`.

| id | Descrição | Procedimento |Tipo|deleted|
|----|-----------|-------------|----|-------|
| 2 | Faturamento | SRPT_RELFAT | FAT|0|
| 3 | Faturamento - Produto | SRPT_RELFAT_PROD | FAT|0|
| 4 | Financeiro - Posição Final | SRPT_MOV_FINAN | FIN|0|
| 7 | Financeiro - Vencidos | SRPT_MOV_VENCIDOS | FIN|0|
| 8 | Relatório NFs | SRPT_REL_NFLISTA | FAT|0|
| 9 | Financeiro - Saldo Bancário | SRPT_BAN_SALDO | FIN|0|
| 10 | Financeiro - A Vencer | SRPT_MOV_VENCER | FIN|0|
| 11 | Financeiro - Baixas | SRPT_BAIXAS | FIN|0|
| 12 | Fatura Compra | SRPT_FATCOMP | FIN|0|
| 13 | NF - Cabeçalho | SRPT_REL_NFDETAIL | FAT|0|
| 14 | NF - CFOP | SRPT_REL_NFDETAIL_CFOP | FAT|0|
| 15 | NF - Itens | SRPT_REL_NFDETAIL_ITENS | FAT|0|
| 16 | Vendas | SRPT_RELVENDAS | VEN|0|
| 17 | Relatório Produtivo | SRPT_RELPRODUTIVO | PRO|0|
| 15001 | PagarReceber | SRPT_PAGAR_RECEBER | FIN|0|
| 15002 | PontualidadeEntrega | SRPT_PONTUALIDADEENTREGA | FAT|0|
| 15005 | Fluxo Futuro | SRPT_FLUXO_FUTURO | FAT|0|
| 15007 | Custo Fixo Comparativo | SRPT_CUSTO_FIXO | FIN|0|
| 15008 | Bonificação Anual | SRPT_RELBONIFICACAO | FAT|0|
| 15009 | Previsão Faturamento | SRPT_PREVISAOFATURAMENTO | FAT|0|
| 15010 | Devoluções | SRPT_RELDEVOLUCAO | FAT|0|
| 15011 | Prazo Médio | SRPT_REL_PRAZOMEDIO_FAT | FAT|0|

Procedures `deleted=1` (legadas, mas mantidas no catálogo): `SRPT_RELFAT_AUX`, `SRPT_RELFAT_MES`, `SRPT_RELFAT_SERV`, `SRPT_RELFAT_TOTAL`, `SRPT_RELFATCUSTO_PROD`, `SRPT_VENDAS`, `SRPT_REL_NFDETAIL_PARCELAS`.

### 2.3 Parâmetros (`rpt_procedimento_parametros`, 237)

Mapeamento de entrada de cada `SRPT_*`. Ex.: `SRPT_RELFAT` recebe 10 parâmetros: `Emp` (lista de empresas), `DataI`, `DataF` (período), `Ordena` (coluna ordenação), `Campo` (filtro), `Cod` (código), `Tipo` (T=Todos), `Serv2`, `Graf` (gerar gráfico?), `Comp` (natureza de operação).还有 `DataIC`/`DataFC` (comparação), `CurvaA/B/C`, `QMP` (unidade medida).

### 2.4 Dashboards (`rpt_dashboard`, 54) — painéis home

Widgets da tela home do EXE. Colunas-chave: `filtro` (→ rpt_filtros.id_filtro), `filtro_procedimento` (→ rpt_filtro_procedimentos.id_filtro_procedimento), `topico` (nome do elemento HTML), `tipo_periodo_analise` (3=mês atual), `periodo_atualizacao` (5 min).

Amostra:

| id | Descrição | Topico | Tipo_filtro |
|----|-----------|--------|-------------|
| 8 | Qtde Faturada Mês Atual | home_dash_box_qtde_fat | FAT |
| 10 | Total Faturado Mês Atual | home_dash_box_valor_fat | FAT |
| 11 | Produtos mais Faturados | home_dash_graf_prod | FAT |
| 12 | Faturamento Anual | home_dash_graf_mensal | FAT |
| 14 | Qtde Clientes Atendidos | home_dash_box_clientes | FAT |
| 16 | Índice Vendas | home_dash_indice_vendas | VEN |
| 17 | Indicador Faturamento | home_dash_indice_fat | FAT |
| 21 | Estoque Peças Aberto | home_dash_pecas_prod | PRO |
| 34 | Resumo Carteira Aberto | home_dash_resumo_vendas | VEN |
| 53 | Inadimplência Receber | home_dash_box_inadimplencia | FIN |

Grupos de exibição (`rpt_grupos_exibicao`, 7): "Indicador de Faturamento", "Indicador de Vendas", "Gestão de Clientes", "Resumo Carteira", "Resumo Faturamento Líquido Qtde/R$".

Layout: `rpt_page_configuration` (4 páginas) → `_dashboard` (16 slots com tipo_grafico: bar, doughnut, gauge, Display, line) → `_usuario` (16, override por perfil) → `rpt_dashboard_page_position` (30 — perfis 1–2 home, página, posição, dashboard_id, tipo_grafico).

### 2.5 Definição de medidas (`rpt_filtro_propriedades`, 602)

Campos de resultado de cada `SRPT_*`. Ex.: para `SRPT_RELFAT` (procedimento 2):

| Coluna | Descrição |
|--------|-----------|
| `[QTDE]` | Quantidade vendida |
| `[TOTAL_VENDIDO]` | Total vendido em R$ |
| `[PRECO_MEDIO]` | Preço médio (= total/quantidade) |
| `[QTDE_C]` | Qtde comparada (período anterior) |
| `[TOTAL_VENDIDO_C]` | Total vendido comparado |
| `[PRECO_MEDIO_C]` | Preço médio comparado |

Tipo `M` = money (formatação monetária); `calculo=S` = coluna calculada.

### 2.6 Níveis hierárquicos (`rpt_filtro_niveis`, 223)

Análise drill-down (empresa → filial → período → cliente → produto). Cada nível define: `propriedade` (DATA DE EMISSÃO, CLIENTE, PRODUTO, REPRESENTANTE, etc.), `nivel` (ordem hierárquica 5..15), `procedimento_nivel` (FK p/ `rpt_filtro_procedimentos` que carrega a lista de valores do nível).

### 2.7 Cache e log

- `rpt_dashboard_data` (147) = resultados JSON das últimas execuções dos dashboards. `conteudo` = `{"valor":" 0,00","utilizaValorOriginal":true,"niveis":{}}` — **todos zeros** desde 2020-05-06 (última atualização).
- `rpt_dashboard_eixox/eixoy` (59/29) = mapeamento de eixos de gráficos (propriedade X/Y).
- `rpt_dashboard_tipos_grafico` (63) = tipos de gráficos suportados por dashboard (bar, doughnut, gauge, line, horizontalBar, Display).
- **`rpt_log` (236.827)** = **100% erros** tipo `ERROR`/`NullPointerException` Java, período 06/2019–05/2020. A API Java do painel parou de funcionar em maio/2020 e o EXE não foi mais executado.

---

## 3. Configuração

| Tabela | Linhas | Conteúdo |
|--------|--------|----------|
| `rpt_dashboard_cfg` | 1 | `id_dashboard_cfg=1`, `codigo_natureza_operacao='01'` (NO de recebimento) |
| `rpt_dashboard_cfg_empresas` | 1 | Empresas habilitadas: empresa `01` (matriz) |
| `rpt_dashboard_cfg_grupo_empresas` | 0 | Grupos (vazio) |
| `rpt_dashboard_override_*` | 0 | Overrides por perfil/empresa |
| `rpt_page_configuration` | 4 | Containers de layout (350px altura, 4 páginas: home, filtros, etc.) |
| `rpt_page_configuration_usuario` | 16 | Posição dos dashboards na home por perfil |
| `rpt_page_configuration_grupo` | 4 | Config de grupo |
| `rpt_grupos_exibicao` | 7 | Grupos temáticos (header→body→footer→detalhe) |
| `rpt_meta_*` / `rpt_gerador*` / `rpt_redirecionamento*` | 0 | Metas/gerador/redirect — desativados |

---

## 4. Relatórios impressos `Rel_*` (5 procs)

Procedures de relatório de inventário — **não são do módulo RPT**, são relatórios do módulo **Estoque** salvos com prefixo `Rel_` pelo desenvolvedor:

| Proc | Tamanho | Descrição |
|------|---------|-----------|
| `Rel_RegInventario` | 79 KB | Relatório de Inventário Geral |
| `Rel_RegInventarioTerceiros` | 58 KB | Inventário de Mercadoria de Terceiros |
| `Rel_RegInventariodeTerceiros` | 33 KB | Inventário (versão complementar) |
| `Rel_RegInvComparativo` | 9 KB | Comparativo de Inventário |
| `Rel_RegInventario_Misto` | 2 KB | Inventário misto |
| `Rel_RegInventario_SEM_Valores_Comparativo` | 25 KB | Inventário sem valores (comparativo) |

Recebem parâmetros `@DataI`, `@DataF`, `@Empresas`, `@IdProcesso`, `@TipoRelatorio`, `@CFOP`, `@Moeda`. Produce relatório via `#TMP`/`@TBRESULTADO`.

---

## 5. Observações para a nova API

1. **As procedures `SRPT_*` são a referência de cálculo** para indicadores do novo sistema. Não replicar a arquitetura de configuração (`rpt_*`); chamar ou reimplementar os SELECTs das procs conforme necessário.
2. **Procedures mais relevantes para a API web:**
   - `SRPT_RELFAT` / `SRPT_RELFAT_PROD` — faturamento (Estudo 06 já mapeado).
   - `SRPT_RELVENDAS` / `SRPT_VENDAS` — vendas (Estudo 08).
   - `SRPT_MOV_FINAN` / `SRPT_MOV_VENCIDOS` / `SRPT_MOV_VENCER` / `SRPT_BAIXAS` / `SRPT_BAN_SALDO` / `SRPT_PAGAR_RECEBER` — financeiro (Estudos 11/12).
   - `SRPT_PONTUALIDADEENTREGA` — KPI de pontualidade de entrega (cálculo relevante para cross-selling/produção).
   - `SRPT_PREVISAOFATURAMENTO` — previsão de faturamento.
   - `SRPT_FLUXO_FUTURO` — fluxo de caixa projetado.
   - `SRPT_RELDEVOLUCAO` — devoluções.
   - `SRPT_REL_PRAZOMEDIO_FAT` — prazo médio de faturamento.
3. **Tabelas de configuração (`rpt_*`) não são necessárias na API web** — são metadados internos do painel Java. Pode descartar para o contrato da API. Se precisar de um "CRUD de dashboards", avaliar requisitos novos.
4. **`rpt_log` não tem valor** — é só log de erros Java de 2020. Não manter na API.
5. **`Rel_*`** (inventário): considerar se o legado `oraculum` usa — provavelmente não (main.py não tem endpoint de inventário); validar e documentar como funcionalidade futura da API se houver demanda.
6. **O módulo efetivamente parou em 05/2020** — o desktop EXE que consumia esses dashboards não era mais usado (ou apontava para outro banco). Manter como referência de indicadores, não como implementação.

---

## 6. Próximos passos

- Analisar as procedures `SRPT_*` mais críticas (já listadas) e extrair definições de indicadores (Ex.: Faturamento Líquido = Bruto - Bonificação - Devolução - Comissão).
- Próximo estudo da fila: **Usua** (módulo `Usua_*/Seguranca` de acessos/perfis/usuários).
- Depois: **Infra** (Etc_Parametros, parâmetros gerais, integração/replicação/Neon).

---

_Fontes: pesquisa direta em `sys.tables`, `sys.procedures`, `INFORMATION_SCHEMA.COLUMNS` + amostragem das tabelas `rpt_*` e `SRPT_*`._