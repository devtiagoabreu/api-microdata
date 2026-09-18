# Estudos do banco Microdata (DBMicrodata_DGB)

Documentação incremental produzida a partir de **estudos de leitura (SELECT)** no banco de
produção `DBMicrodata_DGB` (SQL Server 2019). Nesta fase **não são executadas escritas**
(INSERT/UPDATE/DELETE/DDL) no banco — apenas consultas para mapear estrutura e comportamento.

## Objetivo

Servir de base para a construção da nova **API em Python** que disponibilizará dados do ERP
Microdata (substituindo a API legada que está em `docs/legado/oraculum`).

## Bancos (arquitetura)

- **`DBMicrodata_DGB`** — banco do **fornecedor (Microdata)**, de produção. **Não aceita objetos
  novos** (views/tabelas/procs): é a **fonte somente leitura** do estudo e da nova API.
- **`DBProDash`** — **camada própria de BI/dashboards** criada internamente porque não se pode
  criar nada no ERP. Suas views fazem `SELECT` em `DBMicrodata_DGB` (nome de 3 partes) e é o banco
  onde **se pode criar/manter** views, snapshots e tabelas materializadas. Ver
  [Estudo 21](./21-bi-power-bi.md).
- **`DBIntegracao`** — hub de integração/licenciamento da Microdata (tabelas `Conn_*`).
- **Neon (PostgreSQL, externo)** — **destino futuro** dos dados. Não tem acesso ao `DBMicrodata_DGB`,
  então **a API em Python** extrai do ERP e **carrega no Neon**; o `DBProDash` é o **protótipo** a ser
  portado. Ver [Estudo 22](./22-arquitetura-neon-etl.md).
- **`dgbcomex` (Next.js + Vercel, repositório separado)** — camada de produto (dashboards, BI, CRM)
  que **lê o Neon diretamente** (Prisma/Drizzle); logo o schema do Neon é o **contrato** entre a API
  (ETL) e o front. Ver [Estudo 22](./22-arquitetura-neon-etl.md).

## Regras do estudo

1. **Somente leitura**: apenas `SELECT`, `sp_help`, `INFORMATION_SCHEMA`, catálogos do `sys`.
2. **Nada de credenciais no repositório**: cadeias de conexão, usuários e senhas ficam apenas
   em arquivos `.env` locais (todos cobertos pelo `.gitignore`).
3. **Nada de dados reais sensíveis**: a documentação contém *estrutura* (nomes de tabelas,
   colunas, tipos, relações, parâmetros de procedures), nunca valores de produção.
4. **Commits pequenos e incrementais**: cada estudo é um incremento commitado e enviado com push.

## Índice de estudos

| # | Documento | Domínio | Status |
|---|-----------|---------|--------|
| 01 | [Visão geral do banco](./01-visao-geral-do-banco.md) | Catálogo e módulos do ERP | ✔ |
| 02 | [Estoque de peças/rolos de tecido](./02-dominio-estoque-pecas.md) | `Cte_Peca`, `CTE_Baixa`, `Produtos_Tecidos`, `Vw_Car_Itens_Pedido` e `uspEnderecamentoParaAtenderPedidoGeral` | ✔ |
| 03 | [Pedidos e itens de venda](./03-dominio-pedidos-vendas.md) | `Car_Pedido`, `Car_Itens_Pedido`, `Car_Vend_Pedido`, `Clientes_Principal`, `Rec_Vendedores` | ✔ |
| 04 | [Status dos pedidos e jornada até a NF](./04-status-pedidos-e-fluxo-nf.md) | Decodificação de `Status`/`Status_Ped`/`Status_Item`/`Tipo_Pedido` e fluxo `Car_Romaneio` → `Fat_Pedido` | ✔ |
| 05 | [Faturamento e contas a receber](./05-faturamento-contas-a-receber.md) | `Notas_Fiscais_Rec`, `Notas_Fiscais_Parcelas`, `Rec_Baixas`, view `Rec_EmAberto` | ✔ |
| 06 | [Contas a pagar](./06-contas-a-pagar.md) | `NF_Entradas`, `NFE_Parcelas`, `Pag_Baixas`, `Pag_ChequesEmi_Duplicata`, `Pag_Historicos`, `Pag_Tipos_Fornecedores` | ✔ |
| 07 | [Jornada do título a pagar](./07-jornada-conta-a-pagar.md) | Geração do CP (`Gera_Ret_NFEntrada`, `Ret_Lanca_Entradas`, `sp_Gerar_Pagar_SemiPronta`, `SP_Transfere_CP`), rateio `NFE_CCustos_*`, CNAB/SISPAG no CP | ✔ |
| 08 | [Cadastros base](./08-cadastros-base.md) | `Clientes_Principal` (cliente+fornecedor), `Produtos`/`Produtos_Tecidos`, `Rec_Vendedores`, `Empresas` | ✔ |
| 09 | [Estoque de peças e livros](./09-estoque-pecas-livros.md) | `CTE_Saldos`, `CTE_Baixa` (Tipo `'V'` ⇔ `Car_Itens_Romaneio`), `CTE_RomTransf`, `CTE_Gaveta`, `Liv_Inventario`/`Liv_Kardex_EmpTerc` | ✔ |
| 10 | [Compras e recebimento](./10-compras-e-recebimento.md) | `Cmp_*` sem uso; compras reais = `NF_Entradas` (série `U` importação/`NFS` serviço) + importação NF-e (`Liv_XML`) | ✔ |
| 11 | [Procedures, views e funções](./11-procedures-e-views.md) | Superfície de acesso: 2 352 procs / 530 views; os 15 endpoints do legado; segundo banco `DBProDash` e as views `vwFaturamento`, `VW_Rec_DuplicatasEmAberto`, `VW_Pag_Titulo_Aberto` | ✔ |
| 12 | [Views do DBProDash](./12-views-dbprodash.md) | Regra de negócio de `vwFaturamento`/`vwContasPagas`/`vwListagemDe*`, contrato das 10 procs de dashboard, escrita escondida no centro de custo (`Rel_CCusto_Niveis`) e recomendação de porte | ✔ |
| 13 | [Views do DBMicrodata_DGB](./13-views-dbmicrodata.md) | Catálogo das 530 views por módulo; views de negócio reutilizáveis (`VW_CTE_PECA_EM_ABERTO`, `VW_CarPedidosEmAberto`, `VW_Rec_Duplicata(*)`, `VW_Pag_Titulo_Aberto`, `Fornecedores`, `Entidades`) e uso por endpoint | ✔ |
| 14 | [Módulos de produção e mapa de módulos](./14-modulos-producao-e-mapa.md) | Views `VW_CTE_*`/`VW_PCP_*`/`VW_Cfc_*` e o achado de que produção/PCP/CFC/FIO/TNT/loja/custo estão **vazios** — mapa de tabelas × linhas por módulo | ✔ |
| 15 | [Functions](./15-functions.md) | Catálogo das 194 funções (141 escalares/40 TVF/13 inline, 81 órfãs): parâmetros por empresa, datas úteis, fiscal (EFD/FCI), receber, preço, medidas — e as referenciadas por views | ✔ |
| 16 | [Triggers](./16-triggers.md) | Catálogo das 672 triggers (285 tabelas; 10 off): trava de fechamento mensal, campos derivados, fan-out de `Produtos`, auditoria — e o que a API read-only deve respeitar | ✔ |
| 17 | [Cadastros comerciais](./17-cadastros-comerciais.md) | Tabelas de preço (`CAR_TABELA_PRECO*`), condições de pagamento, comissões/vendedores, transportadoras, bancos/cheques/CNAB — e a cadeia de resolução de preço | ✔ |
| 18 | [Fiscal (Liv_*/EFD/SPED)](./18-fiscal-liv-efd.md) | Livro fiscal de saídas/entradas, importação de NF-e XML, figura fiscal (`Fig_*`), parâmetros (`SIS_Parametros*`) e SPED/EFD | ✔ |
| 19 | [Estoque de peças (Cte_Peca)](./19-estoque-pecas-cte-peca.md) | `Cte_Peca`/`CTE_Baixa`/`CTE_Saldos`, romaneios de venda e transferência e a regra de "peça em aberto" (`VW_CTE_PECA_EM_ABERTO`) | ✔ |
| 20 | [Importação/COMEX, previsão de compra e SIM Carteira](./20-importacao-comex-sim-carteira.md) | `Ret_Aviso_*` (aviso/previsão × pedido), DI (`Fat_Itens_Pedido_DI`/`Liv_EntProd_DI`), saldo de carteira (`Vw_Saldo_Pedido_Carteira_Qlik`) e SIM/Smartsales (`pedido_web`, `*_SPED_Microdata`) | ✔ |
| 21 | [B.I, Power BI, Qlik e dashboards](./21-bi-power-bi.md) | Views `*_PBI`/`*_Qlik`, banco `DBProDash` (faturamento/DRE/estoque/financeiro), BI nativo Microdata, snapshots de estoque (DGB×MOVEN×COMEX) e a dependência quebrada `DBInternet_DGB` | ✔ |
| 22 | [Arquitetura de destino (DBProDash → Neon) e carga pela API](./22-arquitetura-neon-etl.md) | Plano de dados/ETL: `DBMicrodata_DGB` (read-only) → API → **Neon/Postgres**; mapa de PKs/watermarks das 40 tabelas-fonte, carga incremental, porte SQL Server→Postgres e convenções | ✔ |
| 23 | [Financeiro, fluxo de caixa, contábil, fiscal e custo médio](./23-financeiro-contabil-custo.md) | Banco (`Bco_Lancamentos`/cheques), fluxo de caixa (`Fluxo_Caixa` + `SP_Fluxo_GerarFluxoPorEmpresa`), contábil e apuração fiscal **vazios** e custo médio **on-the-fly** (`SP_MCG_Custo_Medio_DGB` sobre `Liv_Entradas/Saidas`) | ✔ |
| 24 | [Endereçamento de peças (“gavetas”), WMS e COMEX/packing list](./24-enderecamento-gavetas-wms-comex.md) | `Cte_Gaveta`/`Cte_GrupoGaveta` e movimentos (`Cte_Peca_Gaveta_Log`, `CTE_PalmGav_Log`), picking (`uspEnderecamentoParaAtenderPedidoGeral`), volumes/fardos (`retVolumes*`/`Cte_Fardo`), COMEX (`Ret_Aviso_*`, `Fat_XML_DI(_embalagem)`, `CMT_LocalDesembaraco`) e o duplo sentido de “packing list” | ✔ |
| 25 | [Expedição/armazém: distribuição, separação, coleta, romaneio e despacho](./25-expedicao-despacho-separacao.md) | Módulo `SP_GESTOR_*`/`Car_Efetiva_Distri`, ordem de separação `CAR_SEPARACAO*` (status 0–4), romaneio `Car_Romaneio`/`Car_Itens_Romaneio`, minuta de despacho `Fat_Minuta_Despacho(_Notas)` e transporte em `Fat_Pedido` | ✔ |
| 26 | [Mapa de módulos da Microdata e relação no banco](./26-mapa-modulos-microdata.md) | 5 003 tabelas em 253 prefixos; módulos core, verticais (têxtil, loja, pneus, varejo…), infra (`SIS/MIC/RPT/LOG`) e as regras de identificação/porte | ✔ |
| 27 | [Cadastros base (detalhado)](./27-cadastros-base-profundo.md) | Entidade única `Clientes_Principal` (+ satélites, views `Entidades`/`Fornecedores`, `Fnn_Participante`), `Produtos`/`Produtos_Tecidos|Fios|Servicos`, classificação (`Ret_*`), `Empresas`, geografia e auxiliares (transportadora, vendedor, cond. pagto, bancos); row-level security do schema `microdata` | ✔ |
| 28 | [Carteira/Pedidos (`Car_*`)](./28-carteira-pedidos.md) | Pedido de venda em profundidade: `Car_Pedido`/`Car_Itens_Pedido`/`Car_Vend_Pedido` (PK/FK/índices/status/tipo), satélites (auditoria, cancelamento, previsão, peças), tabela de preço, views da carteira (`VW_Car_Pedido`, `Vw_Car_Itens_Pedido`, `VW_CarPedidosEmAberto`, `Vw_Saldo_Pedido_Carteira_Qlik`) e a ponte `Liv_Diario` empresa de venda ↔ produto | ✔ |
| 29 | [Faturamento/Nota Fiscal (`Fat_*`, `Notas_Fiscais_*`, `Rec_*`)](./29-faturamento-nf.md) | Jornada pedido→NF: consistência (`Fat_Consiste*`), faturamento (`Fat_Pedido`/`Fat_Itens_Pedido`, `Base_Calc`/QMP, `Fat_Nat_Pedido`, `Fat_Pedido_Dados_NFE`, `Fat_Vend_Pedido`, `Fat_Parc_Pedido`), livro fiscal (`Liv_Saidas`/`Liv_SaiProd`), AR (`Notas_Fiscais_Rec`/`_Parcelas` + `Rec_Baixas`/`Rec_Historicos`), NF-e (histórico/fila/eventos/canceladas), devolução/crédito e o contrato das views (`Vw_Fat_Saida_Qlik`, `VW_Fat_Itens_Pedido_ComQMP`, `VW_Rec_Duplicata_Aberto`) | ✔ |
| 30 | [Contas a Receber (`Rec_*`, `Notas_Fiscais_*`)](./30-contas-a-receber-rec.md) | Título/parcelas (`Notas_Fiscais_Rec`/`_Parcelas`/`_Log`), baixas (`Rec_Baixas` + históricos `Rec_Historicos`), comissão (`Rec_Vendedores`/`Rec_Comissoes`), CNAB (`Rec_Remessa`/`Rec_RetornoOcorr`/`Rec_Ocorrencia`/`Rec_Transacao`), crédito (`Rec_Grupos_IntCh`), parâmetros (`Rec_Parametros`/`Rec_ParamEmp`), a função `FN_Rec_DuplicatasEmAberto` e as views de aberto/atraso/prazo; fórmula do `Valor_Liquido` e a empresa auxiliar 14 | ✔ |

## Referência (legado)

A API antiga está preservada em [`docs/legado/oraculum`](../legado/oraculum/README.md) e é
usada como fonte de informação de quais consultas o negócio consome hoje.