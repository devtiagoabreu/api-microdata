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

## Referência (legado)

A API antiga está preservada em [`docs/legado/oraculum`](../legado/oraculum/README.md) e é
usada como fonte de informação de quais consultas o negócio consome hoje.