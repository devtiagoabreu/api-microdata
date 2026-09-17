# Estudo 11 — Procedures, views e funções (superfície de acesso)

Levantado em **SELECTs somente leitura** sobre catálogos (`sys.procedures`, `sys.sql_modules`,
`sys.views`, `sys.objects`). Sem executar procedures de escrita. **Sem valores reais** — apenas
nomes, parâmetros, tabelas de origem e contagens.

## 1. Objetivo

Mapear a superfície de código do banco para separar **o que a API legada realmente consome** do
universo de 2 352 procedures do ERP (a maior parte é do próprio sistema Microdata, não é alvo da
nova API).

## 2. Inventário do `DBMicrodata_DGB`

| Objeto | Qtde |
|--------|-----:|
| Tabelas | 5 003 |
| Stored procedures | 2 352 |
| Views | 530 |
| Triggers | 673 |
| Funções (`FN`/`IF`/`TF`) | 194 |

Prefixo dominante: **`SP_*` (2 141)** — núcleo do ERP. Outros blocos: `Ret_*` (41), `dt_*`
(30 — Data Transformation/EFD), `SRPT*` (28 — relatórios), `Cfc_*` (22), `Gera_*` (16).

> **Conclusão:** as 2 352 procedures são, quase todas, **lógica interna do ERP** (relatórios,
> geração, EFD, PCP, folha). A nova API **não** deve reimplementá-las; deve expor apenas as
> consultas de negócio que o front consome (Seção 3).

## 3. A superfície que a API legada consome

A API antiga (`docs/legado/oraculum/src/main.py`) expõe **15 endpoints**, apoiados em
**2 bancos** — este é o requisito real a substituir:

| Endpoint legado | Banco | Objeto chamado | Retorno |
|-----------------|-------|----------------|---------|
| `GET /dados` | `DBMicrodata_DGB` | SQL inline `Cte_Peca ⋈ CTE_Baixa ⋈ Produtos_Tecidos` | lista de rolos disponíveis |
| `GET /sugestao-rolos/{pedido}` | `DBMicrodata_DGB` | `EXEC uspEnderecamentoParaAtenderPedidoGeral @pedido` | sugestão de separação (Estudo 02) |
| `GET /pdf/sugestao-rolos/{pedido}` | `DBMicrodata_DGB` | idem + PDF (reportlab) | PDF de cartões |
| `GET /faturamento/{data}` | `DBProDash` | `uspFaturamento @data` | `{Faturamento}` |
| `GET /faturamento-dia/{data}` | `DBProDash` | `uspFaturamentoDia @data` | `{Faturamento}` |
| `GET /contas-pagas/{data}` | `DBProDash` | `uspListagemBaixasPagar @data` | `{ContasPagas}` |
| `GET /descontos/{data}` | `DBProDash` | `uspDesconto @data` | `{Desconto}` |
| `GET /devolucoes/{data}` | `DBProDash` | `uspDevolucao @data` | `{Devolucao}` |
| `GET /estornos/{data}` | `DBProDash` | `uspEstorno @data` | `{Estorno}` |
| `GET /custos-administrativos-anual` | `DBProDash` | `uspRel_CCusto_NiveisAnual` + `uspCustoAdmArmFat` | `{...}` |
| `GET /custos-administrativos-mensal` | `DBProDash` | `uspRel_CCusto_NiveisMensal` + `uspCustoAdmArmFatMensal` | `{...}` |
| `GET /contas-receber-programado` | `DBProDash` | `uspDashFinanceiroContasReceberProgramado` | `{QtdeDoc, ValorTotal}` |
| `GET /contas-pagar-programado` | `DBProDash` | `uspDashFinanceiroContasPagarProgramado` | `{QtdeDoc, ValorTotal}` |
| `GET /dashboard-completo/{data}` | ambos | agrega todos os anteriores | JSON do dashboard |
| `GET /health`, `/procedures`, `/test-procedure/{name}` | — | utilidades | — |

Formato de data legado: `DDMMAAAA` (`25122024`) → convertido para `DD/MM/AAAA` antes do `EXEC`.

> Observação: o `DBProDash` **também** possui uma `uspEnderecamentoParaAtenderPedidoGeral`
> (versão espelho). O endpoint legado de sugestão chama a de `DBMicrodata_DGB`.

## 4. Achado: existe um segundo banco em produção — `DBProDash`

A API antiga **depende majoritariamente de `DBProDash`** (dashboards). Ele está no mesmo servidor
e acessível com as mesmas credenciais read-only. Inventário:

- **28 procedures**, **31 views**, **10 tabelas**.
- As procedures de dashboard são **finas**: quase só filtram por data e agregam uma view.
- São as **views do `DBProDash`** (que por sua vez leem as tabelas de `DBMicrodata_DGB`) que
  contêm a regra de negócio.

### 4.1 Tabelas do `DBProDash`

| Tabela | Linhas | Papel |
|--------|-------:|-------|
| `Rel_CCusto_Niveis` | 1 842 | centro de custo por níveis (materializada por `uspRel_CCusto_Niveis*`) |
| `estoqueDGB` / `estoqueDGBAnalitico` | 6 412 | snapshot de estoque |
| `estoqueMOVEN` | 6 226 | estoque de sistema externo (MOVEN) |
| `estoqueEQUAL` | 6 222 | interseção DGB × MOVEN |
| `estoqueDIFF` | 190 | divergências |
| `nova_tabela` | 91 · `tab_dup` | 6 · apoio |
| `dgbcomexEstoque` / `dgbcomexEstoqueRetroativo` | 0 | não usadas |

### 4.2 Procedures do `DBProDash` → views de origem

| Procedure | Parâmetro | View de origem |
|-----------|-----------|----------------|
| `uspFaturamento` | `@dataInicial` | `vwFaturamento` |
| `uspFaturamentoDia` | `@dataInicial` | `vwFaturamento` |
| `uspDesconto` / `uspDescontoDetalhado` | `@dataInicial` / — | `vwFaturamento` |
| `uspListagemBaixasPagar` | `@dataInicial` | `vwContasPagas` |
| `uspDevolucao` | `@dataInicial` | `vwListagemDeEntradasSaidasPorCFOP` |
| `uspEstorno` | `@dataInicial` | `vwListagemDeEstornos` |
| `uspDashFinanceiroContasReceberProgramado` | — | `vwFinanceiroContasReceber` |
| `uspDashFinanceiroContasPagarProgramado` / `...RestanteAno` | — | `vwFinanceiroContasPagar` |
| `uspRel_CCusto_NiveisAnual` / `Mensal` / `Semestral` | — | `sp_PagRel_CCusto_Niveis` (via `Rel_CCusto_Niveis`) |
| `uspCustoAdmArmFat` / `Mensal` | — | `vwFaturamento` + `vwContasPagasCentroCusto` |
| `uspCustoAdministrativoArmazenagemPorFaturamento` | — | `vwFaturamento` + `Rel_CCusto_Niveis` |

### 4.3 Regra contida nas views (o que reimplementar)

- **`vwFaturamento`** — base do faturamento. Junta `Fat_Pedido ⋈ Fat_Itens_Pedido ⋈
  Clientes_Principal ⋈ Fat_Nat_Pedido`, com `LEFT JOIN` agregado de `Produtos_Tecidos`.
  Filtros: `Flag_Emitido=1`, `Tipo_Pedido='1'`, `Empresa IN ('13','14')`, `Base_Calc<>'-'`
  e uma **whitelist longa de `(NatOp, Seq)`** (CFOPs de venda/entrada válidos). Coluna `Metros`
  = `CASE Base_Calc`: `'P'`/`'M'` → `Metros`, senão `Qtde`. Saída: `Empresa, Pedido, Cliente,
  Nosso_Pedido, Cod_Produto, Nr_Nota, Data_Nota, Vr_Nota, Metros, Vr_Unitario, Vr_Total,
  Empresa_Auxiliar, Peso, Acres_Desc, Nome_Cliente, Item`.
- **`vwContasPagas`** — `Pag_Baixas ⋈ NFE_Parcelas ⋈ Clientes_Principal ⋈ Bancos ⋈
  Pag_Historicos ⋈ Pag_Operacoes` (baixas do CP com nome do banco/histórico/operação).
- **`vwFinanceiroContasReceber`** → espelha `DBMicrodata_DGB.VW_Rec_DuplicatasEmAberto`.
- **`vwFinanceiroContasPagar`** → espelha `DBMicrodata_DGB.VW_Pag_Titulo_Aberto`.
- **`vwListagemDeEstornos`** — `Fat_Pedido ⋈ Fat_Itens_Pedido ⋈ Fat_Nat_Pedido ⋈ Fat_Vend_Pedido
  ⋈ Rec_Vendedores ⋈ Car_Cores ⋈ Car_Situacoes` (notas estornadas/canceladas).
- **`vwListagemDeEntradasSaidasPorCFOP`** — livro fiscal: `Liv_Entradas/Liv_EntProd/
  Liv_EntNatOp` + `Liv_SaidAS/Liv_SaiProd/Liv_SaiNatOp` + `Liv_Natureza/Liv_Parametros`
  (Entradas × Saídas por CFOP, com `Nova_CFOP`).

### 4.4 Views canônicas no `DBMicrodata_DGB`

Duas views usadas como fonte das de contas a receber/pagar (e que já são a base dos Estudos 05/06):

- **`VW_Rec_DuplicatasEmAberto`** — `Notas_Fiscais_Parcelas ⋈ Notas_Fiscais_Rec ⋈
  Clientes_Principal`, saldo = `SUM(Valor_Parcelas) − SUM(Rec_Baixas.Valor_Liquido)`.
  Saída: `Empresa, idDocumento, CNPJ_CPF, Cliente, Nota_Fiscal, Serie, Desdobro, Emissao,
  Vencimento, Banco, Operacao`.
- **`VW_Pag_Titulo_Aberto`** — `NFE_Parcelas ⋈ NF_Entradas LEFT JOIN Pag_Baixas`. Saída: `Empresa,
  Documento, Parcela, Serie, Emissao, Vencimento, Fornecedor, Tipo_Fornec, Total_Doc,
  Valor_Parcela, Valor_Baixas, Valor_Saldo, Dias (=DateDiff(vcto, hoje)), CodigoBarra, Id_SisPag,
  Referente`.

## 5. Impacto na API

1. **Escopo real é pequeno**: 15 endpoints, apoiados em ~13 procedures + 2 views canônicas. O
   restante das 2 352 procedures é interno ao ERP.
2. **A nova API deve ler as tabelas base diretamente** (ou portar as views), evitando depender de
   `DBProDash` — que hoje só existe para materializar dashboards. Reproduzir `vwFaturamento` e as
   duas `VW_*`/`vw*` é o núcleo da regra.
3. **Decisão pendente de arquitetura:** a nova API terá acesso somente-leitura também ao
   `DBProDash`, ou portaremos `vwFaturamento`/`Rel_CCusto_Niveis` para consultas próprias contra
   `DBMicrodata_DGB`? (precisa de validação do negócio e das permissões).
4. **Autenticação autorizada** deve cobrir os dois bancos se `DBProDash` permanecer no escopo.
5. **CFOP whitelist** da `vwFaturamento` (≈100 pares `NatOp,Seq`) é regra de negócio sensível —
   deve ser extraída para configuração/constante, não embutida.

## 6. Contagens de apoio

- `DBMicrodata_DGB`: 5 003 tabelas · 2 352 procs · 530 views · 673 triggers · 194 funções.
- `DBProDash`: 28 procs · 31 views · 10 tabelas.
- Procedures consumidas pelo legado: 13 (`DBProDash`) + 1 (`DBMicrodata_DGB`); endpoints: 15.
