# Estudos do banco Microdata (DBMicrodata_DGB)

Documentação incremental produzida a partir de **estudos de leitura (SELECT)** no banco de
produção `DBMicrodata_DGB` (SQL Server 2019). Nesta fase **não são executadas escritas**
(INSERT/UPDATE/DELETE/DDL) no banco — apenas consultas para mapear estrutura e comportamento.

## Objetivo

Servir de base para a construção da nova **API em Python** que disponibilizará dados do ERP
Microdata (substituindo a API legada que está em `docs/legado/oraculum`).

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

## Referência (legado)

A API antiga está preservada em [`docs/legado/oraculum`](../legado/oraculum/README.md) e é
usada como fonte de informação de quais consultas o negócio consome hoje.