# Estudo 21 — B.I, Power BI, Qlik e dashboards

Levantado com **SELECTs somente leitura** (catálogo, definições, contagens). Sem dados reais.

## 1. Como o BI está montado

Não há nenhuma menção literal a `"Power BI"`, `"PowerBI"` ou `"QlikView"` no código do banco.
O BI é reconhecido por **convenção de nomes de views** (`*_PBI` e `*_Qlik`) e por um banco
dedicado a dashboards, `DBProDash`. Arquitetura em camadas:

| Camada | Onde | Papel |
|--------|------|-------|
| Fonte de dados | `DBMicrodata_DGB` | ERP (tabelas de negócio) |
| Views de consumo Power BI | `DBMicrodata_DGB.dbo.*_PBI` (7) | modelagem (dimensões + fatos) para Power BI |
| Views de consumo Qlik | `DBMicrodata_DGB.dbo.*_Qlik` (5) | extrações prontas para Qlik |
| Repositório de dashboards | **`DBProDash`** (10 tabelas, 31 views, 28 procs) | dashboards de faturamento, DRE, estoque, financeiro |
| BI nativo Microdata | `copiaRpt_Dashboard_Page_Position`, `Rec_ConsGerencial_*`, `Fat_IndicadorOperacao` | designer/consulta gerencial do próprio ERP |
| Hub de integração | `DBIntegracao` (9 tabelas `Conn_*`) | licenças, endpoints, parâmetros e logs |

As views do `DBProDash` acessam o ERP por **nome de 3 partes** (`DBMicrodata_DGB.dbo.*`) — ou
seja, o BI lê a produção do ERP diretamente (não há data warehouse/cubo separado).

## 2. Views `*_PBI` (DBMicrodata_DGB)

Conjunto de **dimensões + fatos** no padrão de modelagem estrela do Power BI.

| View | Linhas | Papel | Fontes |
|------|-------:|-------|--------|
| `VW_Clientes_PBI` | 1 681 | dimensão cliente | `Clientes_Principal` + `Rec_Grupos_IntCh_Clientes`/`Rec_Grupos_IntCh` + `Clientes_Informacoes` |
| `VW_Produtos_PBI` | 64 | dimensão produto | `produtos` + `Ret_Secao`/`Ret_Grupos`/`Ret_SubGrupos` |
| `VW_Representantes_PBI` | 77 | dimensão vendedor | `Rec_Vendedores` + `Rec_Grupos_Vendedores` |
| `VW_Fat_Rel_Devolucoes_PBI` | 11 | fato devolução | `Liv_Entradas` + `Liv_EntNatOp` + `Clientes_Principal` + `VW_Fat_Devolucoes` |
| `vw_Lancamentos_Diarios_Bancos_PBI` | 10 864 | fato movimento bancário | `bco_lancamentos` + `BCO_HISTORICOS` (entrada/saída/saldo por tipo) |
| `vw_Pagar_Baixa_PBI` | 5 945 | fato baixa de CP | `NFE_Parcelas` + `Pag_Baixas` + NF-entrada + fornecedor |
| `Vw_Pagar_Saldo_PBI` | 133 | saldo CP em aberto | idem, com baixas deduzidas |

`VW_Clientes_PBI` e `VW_Produtos_PBI` são claramente **tabelas de dimensão** (descrições
normalizadas de grupo/subgrupo/seção); as demais são **fatos** já agregados no grão de nota
bancária / parcela.

## 3. Views `*_Qlik` (DBMicrodata_DGB)

Extrações prontas para consumo Qlik, uma por assunto.

| View | Linhas | Papel |
|------|-------:|-------|
| `Vw_Fat_Saida_Qlik` | 32 571 | saída fiscal item a item (nota, impostos, produto, qtde/metros/peso) |
| `Vw_Listagem_Pedidos_Qlik` | 22 765 | pedidos por unidade (`Qtde_MT`/`Qtde_KG`/`Qtde_UN`), valor por item |
| `Vw_Rec_Baixas_Qlik` | 28 425 | baixas de contas a receber (filtro `Data_Baixa >= '20190101'`) |
| `Vw_Rec_Saldo_Qlik` | 1 016 | saldo a receber por parcela (valor − baixas, dias de atraso) |
| `Vw_Saldo_Pedido_Carteira_Qlik` | 123 | saldo da carteira (Estudo 20) |

## 4. `DBProDash` — banco de dashboards

### 4.1 Tabelas (10)

| Tabela | Linhas | Papel |
|--------|-------:|-------|
| `estoqueDGB` | 6 412 | snapshot do estoque DGB por `Nro_Rolo` (só o rolo) |
| `estoqueDGBAnalitico` | 6 412 | estoque DGB analítico (`Produto`, `Cor`, `Nro_Rolo`, `Nro_Peca`, `Largura`, `Metros`, `Peso`, `SubLote`…) |
| `estoqueDIFF` | 190 | conjunto diferença (DGB × EQUAL) |
| `estoqueEQUAL` | 6 222 | conjunto coincidente |
| `estoqueMOVEN` | 6 226 | estoque do sistema externo **MOVEN** por `Nro_Rolo` |
| `dgbcomexEstoque` | 0 | estoque **COMEX/importação** p/ BI (17 col: produto/cor/saldo/custo/classfisc) |
| `dgbcomexEstoqueRetroativo` | 0 | idem, retroativo |
| `Rel_CCusto_Niveis` | 1 842 | rateio de custo por níveis de centro de custo (42 col) |
| `nova_tabela` | 91 | mesmo esquema de `Rel_CCusto_Niveis` (rascunho) |
| `tab_dup` | 6 | auxiliar (`col1`) |

Observação: **nenhum proc/função do servidor referencia** `estoqueDGB`/`estoqueEQUAL`/`estoqueDIFF`/
`estoqueMOVEN`/`dgbcomexEstoque` — são carregados **fora do banco** (ETL/manual) e servem para
**comparar o estoque do DGB com o MOVEN e o COMEX** (conciliação de rolos). `Rel_CCusto_Niveis` é
o único populado por procs (`uspRel_CCusto_Niveis*`, via TRUNCATE+INSERT).

### 4.2 Views (31) — por tema

- **Faturamento**: `vwFaturamento` (32 450), `vwFaturamento_A`/`_B` (32 868), `vwFaturamentoPorProduto_A`
  (14 679), `vwFaturamentoPorProdutoMesAtual` (9) / `_A` (81), `vwFaturamentoPorRepresentanteMesAtual` (33).
- **DRE de tecidos**: `vwDRESaldoTecidosEstoque` (102), `vwDRESaldoTecidosCarteiraFull` (123),
  `vwDRESaldoTecidosCarteiraFull_Vendedores` (123), `vwDRESaldoTecidosCarteiraProntaEntrega` (83),
  `...ProntaEntregaTotais` (42), `vwDRESaldoValorTecidosCarteiraFull_Vendedores` (513),
  `vwDRESimWebEstoque` (**quebrada**, ver §5).
- **Saldo de tecidos**: `vwSaldoTecidosEstoque` (102), `vwSaldoTecidosEstoqueDetalhado` (16 804),
  `vwSaldoTecidosCarteiraPorProduto` (177), `vwSaldoTecidosCarteiraPorRepresentante` (181) +
  `...Geral`/`...Programado`/`...ProntaEntrega` (**quebradas**).
- **Financeiro**: `vwFinanceiroContasPagar` (133), `vwFinanceiroContasReceber` (1 016),
  `vwContasPagas` (8 603), `vwContasPagasCentroCusto` (1 842), `vwContasPagasCentroCustoMensal` (1 842).
- **Peças/estoque físico**: `vwInventarioDePecas` (5 970), `vwSaidaPecas` (32 842).
- **Fiscal**: `vwListagemDeEntradasSaidasPorCFOP` (14 056), `vwListagemDeEstornos` (44).

`vwDRESaldoTecidosEstoque` ilustra o padrão: `Cte_Peca` ⟕ `CTE_Baixa` (baixadas) ⋈ `Produtos`/
`Produtos_Tecidos`/`Car_Cores`, `Empresa='13'`, agrupando metros por produto/cor/categoria —
ou seja, o **mesmo critério de "peça em aberto"** dos Estudos 09/19.

### 4.3 Procedures (28) — por tema

- **Dashboards**: `uspFaturamento`, `uspFaturamentoDia`, `uspDesconto`, `uspDescontoDetalhado`,
  `uspDevolucao`, `uspEstorno`, `uspListagemBaixasPagar`.
- **Financeiro programado**: `uspDashFinanceiroContasPagarProgramado`,
  `uspDashFinanceiroContasPagarRestanteAno`, `uspDashFinanceiroContasReceberProgramado`.
- **Custo/centro de custo** (escrevem em `Rel_CCusto_Niveis`): `uspRel_CCusto_NiveisAnual/Mensal/Semestral`,
  `uspCustoAdmArmFat`, `uspCustoAdmArmFatMensal`, `uspCustoAdministrativoArmazenagemPorFaturamento`.
- **Endereçamento/estoque**: `uspEnderecamentoParaAtenderPedido` (+`_Master`/`_Geral`),
  `uspColetaEnderecamentoParaAtenderPedido` (+`Master`), `uspLocalizarEstoquePorPedido`,
  `uspRetornaSolicitacaoCarga`, `uspSolicitacaoCargaMoven`.
- **SIM Web estoque** (pivot dinâmico por data prevista): `uspSIMWebEstoque`,
  `uspSIMWebEstoquePorProduto`, `uspColunasSIMWebEstoque`, `uspColunasSIMWebEstoquePorProduto`.

## 5. Dependências quebradas (`DBInternet_DGB` ausente)

Existem ~40 bancos no servidor (`DBMicrodata_<cliente>`, `DBCon_<cliente>`, `DBInternet_<cliente>`,
`DBProDash`, `DBIntegracao`), **mas não existe `DBInternet_DGB`**. Objetos que dependem dele estão
**quebrados** (erro `Invalid object name`):

- `DBProDash`: `vwDRESimWebEstoque` (lê `DBInternet_DGB.dbo.Vw_Etc_Estoque_Futuro`) e a cascata
  `vwSaldoTecidosEstoqueGeral`, `vwSaldoTecidosEstoqueProgramado`, `vwSaldoTecidosEstoqueProntaEntrega`
  (todas em cima de `vwDRESimWebEstoque`).
- `DBMicrodata_DGB`: `SP_CMT_Calcula_SaldoEmAberto`, `VW_Saldos_PedCompra_2`,
  `TG_INSDEL_Car_Itens_Pedido_InfoEntregaItemPedido`.

O conceito de **estoque futuro/SIM Web** (saldo disponível + previsão por `Data_Prevista_Inicial/Final`,
`Pedidos_Internet`, `Tinturaria`, `Tipo`) está modelado nessa view quebrada — é uma peça de BI que
**não pode ser reutilizada** enquanto o banco web de DGB não for restaurado.

## 6. BI nativo do ERP e indicadores

- **`copiaRpt_Dashboard_Page_Position`** (30) — designer de dashboards do relatório Microdata:
  `perfil`, `pagina`, `posicao`, `dashboard`, `tipo_grafico`, `faixa_1..3`, `cores`,
  `exibe_legenda`/`exibe_escalax`/`exibe_escalay`, `utiliza_empilhamento`, propriedades de
  análise/comparação. É o **dashboard interno do ERP**, não Power BI.
- **`Rec_ConsGerencial_Panel`** (23) + `Rec_Usuario_ConsGerencial` (0) /
  `Rec_Usuario_ConsGerencial_Panel` (0) — "Consulta Gerencial" do módulo Receber (painéis e
  permissão por usuário; hoje sem concessões).
- **`Fat_IndicadorOperacao`** (26) — catálogo de indicadores de operação.
- **`SIC_BIT`/`SIC_BIC`** (+ variantes `_AC`/`_AE`/`_Acompanhamento`/`_Causa`/`_Disposicao`/`_NC`/
  `_Retorno`, views `VW_SIC_BIC`, procs `SP_SIC_REL_BIC/BIT`) — **não é BI**: é SAC/qualidade
  (reclamação de cliente, `Qtde_Reclamada`/`Qtde_Entregue`, transportadora, responsável).
  Falso positivo do filtro por "BI".

## 7. Infraestrutura

- **Linked server `microdata-db`** (provider `SQLNCLI`, `data_source=microdata-db`) — declarado,
  mas **não usado** por nenhum módulo (nenhuma referência a `OPENQUERY`/`microdata-db`).
- `OPENROWSET` só em `SP_HUB_EnviarInvoice` e `SP_CTE_FinalizaRevisaoEmbaladora` (integração/HUB,
  não BI).
- **`DBIntegracao`** (9 tabelas `Conn_*:Clientes, Clientes_Licenca, Clientes_Sistemas, Endpoints,
  LogExceptions, Logs, Parametros, Sistemas, TabelaIBPT`) — hub de integração/licenciamento da
  Microdata; nenhuma view/proc. Não é BI, mas é infraestrutura do ecossistema.
- Não há **jobs do SQL Agent** referenciando `ProDash`/`estoqueDGB`/`PBI`/`Qlik` — a atualização
  do BI é externa.

## 8. Impacto na API (read-only)

1. O BI **já é servido por views prontas**: para expor os mesmos números, basta replicar como
   endpoints `SELECT` (não reimplementar a regra):
   - faturamento → `DBProDash.vwFaturamento*`;
   - DRE/estoque de tecidos → `vwDRESaldoTecidos*`/`vwSaldoTecidos*`;
   - financeiro → `vwFinanceiroContasPagar/Receber`, `vwContasPagas*`, `*_PBI` de pagar/receber;
   - inventário/peças → `vwInventarioDePecas`/`vwSaidaPecas`;
   - fiscal → `vwListagemDeEntradasSaidasPorCFOP`/`vwListagemDeEstornos`;
   - movimento bancário → `vw_Lancamentos_Diarios_Bancos_PBI`.
2. **Não executar** as procs que **escrevem** (`uspRel_CCusto_Niveis*` fazem TRUNCATE+INSERT em
   `Rel_CCusto_Niveis`; `uspCustoAdmArmFat*` gravam em `DBProDash`). Se a API precisar do rateio,
   ler a tabela já materializada.
3. O **pivot do SIM Web estoque** usa **SQL dinâmico** (`STUFF + FOR XML PATH` para montar colunas
   por data prevista) — deve ser reimplementado em Python, não copiado.
4. **Não expor views quebradas** (`vwDRESimWebEstoque` e a cascata, `VW_Saldos_PedCompra_2`):
   dependem de `DBInternet_DGB`, inexistente. Validar dependências antes de integrar.
5. As views `_PBI`/`_Qlik` e do `DBProDash` são o **contrato de leitura** que o negócio já consome —
   priorizá-las reduz divergência entre a API e o BI atual.

## 9. Contagens de apoio

- Dimensões PBI: `VW_Clientes_PBI` 1 681 · `VW_Produtos_PBI` 64 · `VW_Representantes_PBI` 77.
- Fatos PBI: `vw_Lancamentos_Diarios_Bancos_PBI` 10 864 · `vw_Pagar_Baixa_PBI` 5 945 ·
  `Vw_Pagar_Saldo_PBI` 133 · `VW_Fat_Rel_Devolucoes_PBI` 11.
- Qlik: `Vw_Fat_Saida_Qlik` 32 571 · `Vw_Listagem_Pedidos_Qlik` 22 765 ·
  `Vw_Rec_Baixas_Qlik` 28 425 · `Vw_Rec_Saldo_Qlik` 1 016 · `Vw_Saldo_Pedido_Carteira_Qlik` 123.
- `DBProDash`: 10 tabelas · 31 views · 28 procs · 0 funções.
  - Faturamento 32 450/32 868 · DRE carteira 123 · estoque 16 804 (detalhado) ·
    contas a receber 1 016 · contas pagas 8 603 · inventário 5 970 · saída de peças 32 842 ·
    CFOP 14 056 · estornos 44.
- Snapshots de estoque: `estoqueDGB` 6 412 · `estoqueDGBAnalitico` 6 412 · `estoqueEQUAL` 6 222 ·
  `estoqueMOVEN` 6 226 · `estoqueDIFF` 190 · `dgbcomexEstoque` 0 · `Rel_CCusto_Niveis` 1 842.
- BI nativo: `copiaRpt_Dashboard_Page_Position` 30 · `Rec_ConsGerencial_Panel` 23 ·
  `Fat_IndicadorOperacao` 26.
- Infra: 1 linked server (`microdata-db`, sem uso) · `DBIntegracao` 9 tabelas · ~40 bancos no servidor.
