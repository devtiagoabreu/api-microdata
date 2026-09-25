# Contratos da API (mapeamento legado `oraculum` → Postgres local + Neon)

> **Data:** 19/set/2026 (atualizado 25/set/2026)
> **Escopo:** catálogo das rotas da API legada `docs/legado/oraculum/src/main.py` (+
> `main_funcional_01.py` e `database.py`), com a fonte no legado, a tabela/view do ERP/BI e o
> **mart (warehouse local)** que a substitui. O **Postgres local** (`dgbcomex_warehouse`) é a
> fonte de verdade dos endpoints; **somente agregados pequenos de dashboard** são sincronizados
> on-demand para o **Neon** (ver [Doc 43](./43-arquitetura-alvo-api.md)). Todo endpoint do alvo lê
> o warehouse local, **nunca** o ERP.
> **Fonte dos dados:** recon executado em 19/set/2026 sobre `DBProDash` (defs de `sys.sql_modules`)
> e o SQL preservado em `docs/legado/oraculum`.

---

## 1. Visão geral das rotas

`main.py` expõe **17 rotas**:

| Grupo | Rotas | Qtd |
|-------|-------|-----|
| Negócio (dados de estoque) | `/dados`, `/sugestao-rolos/{pedido}`, `/pdf/sugestao-rolos/{pedido}` | 3 |
| Negócio (KPIs/dashboard) | `/faturamento/{data}`, `/faturamento-dia/{data}`, `/contas-pagas/{data}`, `/custos-administrativos-anual`, `/custos-administrativos-mensal`, `/descontos/{data}`, `/devolucoes/{data}`, `/estornos/{data}`, `/contas-receber-programado`, `/contas-pagar-programado`, `/dashboard-completo/{data}` | 11 |
| Infra/dev | `/health`, `/procedures`, `/test-procedure/{procedure_name}` | 3 |

Das 17: **14 ficam no alvo** (re-exposição lendo o **warehouse local**), `/health` é redefinido
(sonda Postgres local + status ETL) e **`/test-procedure` e `/procedures` são eliminados**
(pass-through de `EXEC` e inventário interno).

Conexão atual (`database.py`): pyodbc → `DB_SERVER/DB_DATABASE` (SQL Server), uma conexão por
request; datas no padrão `DDMMYYYY` convertidas para `DD/MM/YYYY` (`formatar_data_para_sql`).

---

## 2. Contratos de negócio (endpoint a endpoint)

> Legenda: **Fonte ERP** = tabelas/views que alimentam o dado; **Mart (warehouse local)** = objeto
> no Postgres local `dgbcomex_warehouse` (schemas `core`/`marts`). `?` = contrato a confirmar com o negócio.

### 2.1 Estoque de peças / endereçamento (lê `DBMicrodata_DGB`)

| # | Rota | Fonte no legado | Fonte ERP | Mart (warehouse local) | Contrato JSON (alvo) | Notas |
|---|------|-----------------|-----------|-----------|----------------------|-------|
| 1 | `GET /dados` | Query inline (`main.py:35`) — `Cte_Peca` ⨝ `CTE_Baixa` (antijoin) ⨝ `Produtos_Tecidos`, `WHERE Nro_Rolo_Origem IS NULL AND CB.Empresa IS NULL` (peças em aberto) | `Cte_Peca`, `CTE_Baixa`, `Produtos_Tecidos` (Estudos 19/34) | `core.estoque_pecas_em_aberto` (grão peça: `Empresa/Situacao/Nro_Rolo/Nro_Peca` + `Linha` de `Produtos_Tecidos`) | array de `{Lote_Interno, Aviso, Gaveta, SubLote, Situacao, Nro_Rolo, Nro_Peca, Produto, Categoria, Categoria_Tinto, Cor, Desenho, Variante, Largura, Metros, Peso, Rolo_Packlist, Data_Entrada, Chave, Num_Etq_Aux, Linha}` | **Sem paginação no legado** (~300k peças `fetchall`); alvo com **cursor** + filtros opcionais (produto/cor/situação). `Chave = Nro_Rolo+Situacao+Cor+Desenho` (concatenação ambígua) → derivar com separador. Campos `char` com padding → `trim` |
| 2 | `GET /sugestao-rolos/{pedido}` | `EXEC DBMicrodata_DGB.dbo.uspEnderecamentoParaAtenderPedidoGeral @Pedido char(8)` — para cada item do pedido, acumula rolos em aberto até `Qtde_Saldo` (janela por `Gaveta/Tear DESC/Nro_Rolo DESC`) | `Vw_Car_Itens_Pedido`, `Cte_Peca`, `CTE_Baixa` (Estudos 28/34) | `core.sugestao_rolos` — **reimplementação em Python** da lógica (window `SUM(Metros) OVER`); fonte = mart de peças em aberto + pedido) | array de `{Produto, Cor, Qtde_Item, Qtde_Saldo, Sublote, Gavetas, Rolos, Qtde_Pecas, Total_Metros}` | Parâmetro `char(8)`; legado com `CURSOR` + `FOR XML PATH` (não portar). Gd: tolerância `ABS(Soma-Saldo)<0.01`. Opção on-demand read-only do ERP como fallback |
| 3 | `GET /pdf/sugestao-rolos/{pedido}` | Mesmo `EXEC` + reportlab (A4 paisagem, 3 cards/linha) | idem #2 | idem #2 (mesmo cálculo) | PDF `Content-Disposition: inline`; 404 se vazio | Card mostra Produto, Cor, Qtde Item, Qtde Saldo, Sublote, Gavetas, Qtde Peças, Rolos, Total Metros — manter em server-side |

### 2.2 KPIs do dashboard (lê `DBProDash` — BI a portar)

| # | Rota | Proc legado (DBProDash) | Regra (fonte atual) | Fonte ERP (via view) | Mart (warehouse local) | Contrato JSON (alvo) | Notas |
|---|------|--------------------------|----------------------|----------------------|----------|----------------------|-------|
| 4 | `GET /faturamento/{data}` | `uspFaturamento` | `SUM(Vr_Total)+SUM(Acres_Desc) AS Faturamento` por **mês** da `Data_Nota` (`EOMONTH`) | `vwFaturamento` → `Fat_Pedido`, `Fat_Itens_Pedido`, `Fat_Nat_Pedido`, `Produtos_Tecidos`, `Clientes_Principal` (Estudo 29) | `marts.faturamento_diario` (`data_emissao`, `vr_total`, `acres_desc`, `metros` QMP, `vr_nota`) | `{"Faturamento": number}` | Janela de mês calculada na carga; parâmetro passa a **ISO** |
| 5 | `GET /faturamento-dia/{data}` | `uspFaturamentoDia` | idem por **dia** (`Data_Nota = data`), `ISNULL(...,0)` | idem | `marts.faturamento_diario` | `{"Faturamento": number}` | |
| 6 | `GET /contas-pagas/{data}` | `uspListagemBaixasPagar` | `SELECT ... FROM vwContasPagas WHERE Data_Baixa` no mês, Empresa `'13'`, Tipo_Entidade A/F — **atualmente com `SELECT` comentado → retorna `{}`** | `vwContasPagas` → `Pag_Baixas`, `NF_Entradas`, `NFE_Parcelas`, `Pag_Historicos`, `Pag_Operacoes`, `Bancos`, `Clientes_Principal` (Estudos 06/31) | `marts.contas_pagas_diario` (`data_baixa`, `fornecedor`, `valor_pago`, `historico`, `operacao`, `banco`) | **reabrir contrato**: resumo `{ValorPago, QtdeBaixas}` do mês (e lista paginada quando preciso) | Endpoint vivo mas sem dado hoje — alinhar com o negócio |
| 7 | `GET /custos-administrativos-anual` | `uspRel_CCusto_NiveisAnual` (**`TRUNCATE+INSERT` em `Rel_CCusto_Niveis`**) + `uspCustoAdmArmFat` | janela 12 meses; retorna `@faturamento`, `@Administrativo`, `0 Armazenagem`, `Porc_Administrativo=admin/fat` | `Rel_CCusto_Niveis` (carga por `sp_PagRel_CCusto_Niveis`), `vwContasPagasCentroCusto` (cod. despesa/departamento), `vwFaturamento` (Estudo 12) | `marts.custos_por_departamento_mensal` (`mes`, `codigo_despesa`, `codigo_departamento`, `valor_baixado`) + `marts.faturamento_diario` | `{"Faturamento", "Administrativo", "Armazenagem", "Porc_Administrativo", "Porc_Armazenagem"}` — **sem variantes `*_Replace`** | "Anual" = janela de 12 meses. `Armazenagem=0` no legado. Procs que escrevem **não portar** |
| 8 | `GET /custos-administrativos-mensal` | `uspRel_CCusto_NiveisMensal` + `uspCustoAdmArmFatMensal` | janela do mês corrente | `vwContasPagasCentroCustoMensal` | idem | idem | |
| 9 | `GET /descontos/{data}` | `uspDesconto` | `SUM(Acres_Desc) AS Desconto` por mês (`vwFaturamento`) | idem #4 | `marts.faturamento_diario` (agregado `acres_desc`) | `{"Desconto": number}` | |
| 10 | `GET /devolucoes/{data}` | `uspDevolucao` | `SUM(Vr_Contabil) AS Devolucao` por mês com `Nova_CFOP IN ('1.201-1','1.201-2','1.202-1','2.202-1')` | `vwListagemDeEntradasSaidasPorCFOP` (CFOP de venda/entrada — Estudo 35) | `marts.devolucoes_diario` (`data`, `cfop`, `vr_contabil`) | `{"Devolucao": number}` | Lista de CFOPs de devolução a validar (podem crescer) |
| 11 | `GET /estornos/{data}` | `uspEstorno` | `SUM(Vr_Nota) AS Estorno` por mês (`Data_Emissao`) | `vwListagemDeEstornos` | `marts.estornos_diario` (`data`, `vr_nota`) | `{"Estorno": number}` | |
| 12 | `GET /contas-receber-programado` | `uspDashFinanceiroContasReceberProgramado` | `COUNT(QtdeDoc), SUM(ValorTotal)` com `Vencimento > fim do mês anterior` (até `2050-12-31`) | `vwFinanceiroContasReceber` (Estudo 30) | `core.financeiro_receber_programado` (vencimento > corte) | `{"QtdeDoc": int, "ValorTotal": number}` | Janela "a vencer" definida na carga (vence hoje fim mês) |
| 13 | `GET /contas-pagar-programado` | `uspDashFinanceiroContasPagarProgramado` | idem com `COUNT(DISTINCT QtdeDoc)` | `vwFinanceiroContasPagar` (Estudo 31) | `core.financeiro_pagar_programado` | `{"QtdeDoc": int, "ValorTotal": number}` | `DISTINCT` no count — manter semântica |
| 14 | `GET /dashboard-completo/{data}` | Orquestração: chama #4,#5,#6,#7,#8,#9,#10,#11,#12,#13 (10 procs por request) | agrega em um dict | — | leitura única dos marts #4–#13 (uma query por KPI ou cache) | `{data_consulta, faturamento, faturamento_dia, contas_pagas, custos_administrativos_anual, custos_administrativos_mensal, descontos, devolucoes, estornos, contas_receber_programado, contas_pagar_programado}` | Legado = 10 `EXEC` sequenciais por request → alvo = leitura leve/cache |

### 2.3 Infraeste (redefinido) e descartados

| # | Rota | Legado | Alvo |
|---|------|--------|------|
| 15 | `GET /health` | `SELECT 1` no SQL Server | Sonda **Postgres local** (`SELECT 1`) + latência + status `etl.watermark` (última execução por tabela, atraso) |
| 16 | `GET /test-procedure/{name}` | `EXEC DBProDash.dbo.{name}` genérico | **Eliminar** (porta de fuga/execução arbitrária) |
| 17 | `GET /procedures` | lista estática de procs | **Eliminar** (inventário interno) |

---

## 3. Contrato global de resposta (regras que valem para todos)

1. **Parâmetros de data**: alvo aceita **ISO `YYYY-MM-DD`**; manter aceite de `DDMMYYYY` apenas
   em janela de transição (deprecado).
2. **Tipos**: valores monetários/quantidade sempre `numeric` — **removidas** as variantes
   `*_Replace` (string pt-BR). Formatação é responsabilidade do front.
3. **`trim` de chaves `char`** (Produto, Cor, Nro_Rolo, Códigos, Empresa) via validators Pydantic.
4. **Erros padronizados**: `400` (param inválido), `401/403` (auth), `404` (sem dados), `5xx`
   `{erro, detalhe}`. Legado usava `500 {erro, detalhes}` e `404 {erro}` mistos.
5. **Listagens grandes** (`/dados`, e listas de baixas quando reabertas): **paginação por cursor**.
6. **Multiempresa**: código `'13'` vira **parâmetro implícito por token** (não hard-coded no SQL);
   chave usa `Codigo_Empresas` (`char(2)`) por compatibilidade — [Estudo 42 §7](../estudo/42-infra-topologia-infraestrutura.md).

---

## 4. Catálogo de marts no Postgres local resultante

| Mart (schema) | Grão | Alimenta endpoints | Sync p/ Neon |
|---------------|------|--------------------|--------------|
| `core.estoque_pecas_em_aberto` | peça (`Empresa,Situacao,Nro_Rolo,Nro_Peca`) | 1, 2, 3 | não (volume pesado) |
| `core.sugestao_rolos` | pedido×produto×cor (computado) | 2, 3 | não |
| `marts.faturamento_diario` | dia (`data_emissao`) | 4, 5, 9, 14 | sim (KPI agregado) |
| `marts.contas_pagas_diario` | dia (`data_baixa`) | 6, 14 | sim (resumo) |
| `marts.custos_por_departamento_mensal` | mês×despesa×departamento | 7, 8, 14 | sim (resumo) |
| `marts.devolucoes_diario` | dia×cfop | 10, 14 | sim (KPI agregado) |
| `marts.estornos_diario` | dia | 11, 14 | sim (KPI agregado) |
| `core.financeiro_receber_programado` / `core.financeiro_pagar_programado` | título a vencer | 12, 13, 14 | sim (resumo) |

Camadas (no Postgres local): `raw` (fontes), `core` (regras), `marts` (consumo) e `etl` (controle).
No **Neon** só sobem os agregados marcados como "sim", em objetos próprios da API (nunca em
`public`). Detalhes e convenções no [Doc 43](./43-arquitetura-alvo-api.md) e no
[Estudo 22](../estudo/22-arquitetura-neon-etl.md).

---

## 5. Validação do contrato (cutover)

1. Para cada KPI (#4–#13), comparar valor **legado on-prem** × **mart do Postgres local** para os
   mesmos períodos (amostras: mês corrente + 12 meses) — divergência aceitável < 0.01.
2. Para #1/#2/#3, comparar conjunto de rolos sugeridos para 10 pedidos reais.
3. Só então publicar os agregados sincronizados no **Neon** (objetos da API) e descomissionar `DBProDash`.

---

_Base: `docs/legado/oraculum/src/main.py`, `database.py`, `main_funcional_01.py`,
`database/uspEnderecamentoParaAtenderPedidoGera.sql`; defs de `DBProDash` (`sys.sql_modules`).