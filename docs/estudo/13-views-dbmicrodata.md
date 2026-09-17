# Estudo 13 — Views do `DBMicrodata_DGB` (catálogo de negócio)

Levantado em **SELECTs somente leitura**. Estrutura, origens e **contagens**; sem valores reais.
Complementa o Estudo 12 (views do `DBProDash`): aqui catalogamos as views **do próprio ERP**, que
podem ser reutilizadas diretamente pela nova API em vez de reescrever joins.

## 1. Panorama

O banco tem **530 views**; **492** com prefixo `vw_`/`VW_` (nomenclatura própria do ERP). Módulos
mais representativos:

| Módulo | Views | Módulo | Views |
|--------|------:|--------|------:|
| CTE (produção/tecelagem) | 55 | REC (a receber) | 17 |
| PCP (planejamento) | 55 | FAT (faturamento) | 16 |
| CFC (config. comercial) | 30 | CUSTO | 12 |
| TNT (tinturaria) | 26 | RET (retorno terceiros) | 12 |
| CAR (carrinho/pedidos) | 25 | CMT (comodato) | 10 |
| FIO | 22 | PAG (a pagar) | 4 |
| SIC | 20 | Outros (LIV, SALDOS, REL…) | ~250 |
| RB / SIS / GESTOR / PLM… | — | | |

> A maioria é view interna do ERP (PCP, CTE, CFC, FIO…). O valor para a API está nas views de
> **REC / PAG / CAR / FAT / LIV** e nos cadastros (`Fornecedores`, `Entidades`).

## 2. Catálogo das views relevantes

### 2.1 Contas a receber e crédito

| View | Linhas | Fonte | Papel |
|------|-------:|-------|-------|
| `VW_Rec_Duplicata_Aberto` | 1 016 | `Notas_Fiscais_Parcelas` ⋈ `Notas_Fiscais_Rec` ⟕ `Rec_Baixas` (histórico ≠ tipo `'6'`) `UNION` `Sdo_Rec_Duplicata_Aberto` | **View de cobrança/CNAB**: títulos em aberto com juros, desconto, agência/conta, `idParcela` |
| `VW_Rec_DuplicatasEmAberto` | 1 016 | `Notas_Fiscais_Parcelas ⋈ Notas_Fiscais_Rec ⟕ Rec_Baixas ⋈ Clientes_Principal` | Versão simples (sem juros/agência) |
| `VW_Rec_Duplicata_Baixadas` | 28 872 | `Notas_Fiscais_Rec/Parcelas`, `Rec_Baixas`, `Clientes_Principal` | Títulos baixados (histórico de recebimento) |
| `Vw_Rec_Atrasos` | 27 719 | `Notas_Fiscais_Parcelas/_CCD`, `Clientes_Informacoes`, `Fat_ParamEmp` | Atrasos por cliente |
| `Vw_Rec_Prazo` | 2 755 | `Notas_Fiscais_Rec/Parcelas`, `Rec_Movtos_DF` | Maior prazo concedido por cliente |
| `Vw_Rec_Cheques` | 1 681 | `Ch_Cheques`, `Ch_Comprador`, `Rec_ChProprio_Clientes` | Cheques (aberto/vencido/devolvido/próprio/terceiro) |
| `Vw_Rec_Compras` | — | `Notas_Fiscais_Rec`, `Rec_Movtos_DF` | Data/valor da última compra |
| **`Vw_Rec_Inf_Comerciais`** | 1 681 | consolida as anteriores + `Car_*`, `Fat_Pedido` | **Painel de crédito por cliente (32 colunas)**: primeira/última/maior compra, atraso, cheques, limite, títulos em aberto/baixados/atrasados, pedidos em aberto |
| `Vw_Rec_Saldo_Qlik` / `Vw_Rec_Baixas_Qlik` | — | `Notas_Fiscais_Rec`, `Rec_Historicos` / `Rec_Baixas` | Export BI (Qlik): saldo e baixas |
| `Vw_Rec_Estornos_NFDebitos` | — | `Notas_Fiscais_Rec`, `Rec_Baixas_Estornos`, `Rec_Integracao_Ch*` | Estornos/notas de débito |
| `VW_REC_Pedidos_EmAberto` | — | **`PCP_Pedido`**, `PCP_Pedido_Itens`, `Rec_Vendedores` | Pedidos em aberto do módulo **PCP** (não é `Car_Pedido`) |

> **`Sdo_Rec_Duplicata_Aberto`** (tabela) está **vazia (0 linhas)** — é o "saldo anterior" legado que
> a `VW_Rec_Duplicata_Aberto` concatena via `UNION`. Hoje todo o resultado vem da parte calculada.

### 2.2 Contas a pagar

| View | Linhas | Fonte | Papel |
|------|-------:|-------|-------|
| `VW_Pag_Titulo_Aberto` | 133 | `NFE_Parcelas ⟕ Pag_Baixas ⋈ NF_Entradas` | Parcelas com saldo > 0 (canônica) |
| `vw_Pagar_Baixa_PBI` / `Vw_Pagar_Saldo_PBI` | — | `Pag_Baixas`, `NF_Entradas`, `Fornecedores` | Export Power BI (baixa/saldo com razão social) |
| `vw_pag_CREDITO_FORNECEDOR` | — | `Pag_CreditoFornecedor`, `Clientes_Principal` | Crédito por fornecedor (entrada/saída/devo) |

### 2.3 Pedidos, romaneio e separação

| View | Linhas | Papel |
|------|-------:|-------|
| `VW_Car_Pedido` | 15 734 | Cabeçalho do pedido (80 colunas) — já usada no Estudo 04 |
| `VW_Car_Pedido_Aberto` / `VW_Car_Pedido_Aprov` | 20 712 / 33 402 | Itens de pedido com `Qtde_Saldo` (22 colunas, idênticas) |
| **`VW_CarPedidosEmAberto`** | **159** | **Itens em aberto** (`Qtde−Qtde_Romaneio−Qtde_Acerto > 0`) com descrições de produto/cor/desenho/situação/categoria, vendedor, valor em aberto (36 colunas) |
| `VW_CarPedidosEmAbertoMesmoRomaneados` | — | Igual, mas considerando itens já romaneados (`SALDO_REAL` × `SALDO`) |
| `VW_Car_Romaneio` / `VW_Car_Itens_Romaneio` | — | Romaneio e itens (59 colunas com descrições) — Estudos 03/04 |
| `VW_Car_SeparacaoPedido_CodBarras` | — | Separação por código de barras (`Car_Separacao_Itens`) |
| `Vw_Car_SaldoPedido` | — | Saldo do pedido por item (c/ linha do tecido) |
| `Vw_Car_PedRom` | — | Visão gigante Romaneio+Pedido (61 colunas) |
| `VW_Car_Distribuidos` / `VW_Car_BloqDistribuidos` | — | Distribuição/ordem de embarque por item |
| `VW_Car_ClienteInativo` | — | Análise de cliente inativo (30 colunas: datas, atrasos, vínculo de vendedor) |

### 2.4 Faturamento, fiscal e devoluções

| View | Papel |
|------|-------|
| `VW_FAT_TipoPedido` | Domínio do `Tipo_Pedido` (3 linhas) — Estudo 04 |
| `VW_FaturamentoPorProdutoEmp13` | Faturamento por item (57 colunas: tributos, comissão, cond. pagto) |
| `Vw_Fat_Saida_Qlik` | Notas de saída p/ BI (40 colunas) |
| `VW_Fat_Cond_Pagto` | Parcelas/condições do pedido faturado (30 771) |
| `VW_Fat_Rel_Transportes` | Frete/transporte/entrega por nota |
| `VW_Fat_Rel_Devolucoes` | Devoluções (cruzamento `Liv_Entradas` × saída) |
| `VW_Fat_SaldosFacionista` / `Vw_Fat_DevolucaoFaccao` | Saldo/devolução de faccionista (**vazia: 0 linhas**) |
| `VW_Fat_Itens_Pedido_ComQMP` | Itens com **118 colunas** (tributação completa + QMP) |
| `VW_LIV_SAIPROD` | Livro de saída + produto (**219 colunas**) |
| `Vw_Liv_Sai_Rel_Conferencia` | Conferência fiscal de saída (36 colunas, inclui IBS/CBS) |

### 2.5 Estoque (peças/rolos)

| View | Linhas | Papel |
|------|-------:|-------|
| **`VW_CTE_PECA_EM_ABERTO`** | **16 804** | Peças/rolos **em aberto** com descrições decodificadas (19 colunas) |
| `VW_CTE_Saldos_Tintur` | — | Saldo de tinturaria por rolo/peça |
| `VW_CTE_Rolos_Tear` | — | Rolos por tear (apontamento) |
| `VW_CTE_Situacao_Producao` | — | Situação da produção do rolo de urdume |

### 2.6 Cadastros

| View | Linhas | Papel |
|------|-------:|-------|
| **`Fornecedores`** | **659** | `Clientes_Principal ⟕ Clientes_Informacoes WHERE Tipo_Entidade <> 'C'` — **view oficial de fornecedor** |
| `Fornecedores_Situacao` / `Fornecedores_Bloqueio` | — | SPC e bloqueio de fornecedor |
| **`Entidades`** | **1 681** | `Clientes_Fornecedores ⋈ Fornecedores` — entidade unificada (78 colunas) |

> `Empresas` **não é view** — é tabela (Estudo 08). Views dos demais módulos (CTE 55, PCP 55,
> FIO 22, CFC 30…) são internas da produção e não entram no escopo da API de dashboards.

## 3. Achados principais

1. **Boa parte dos endpoints pode usar views prontas do próprio banco** — evitando reescrever joins
   e decodificações:
   - `/dados` (rolos disponíveis) ≈ **`VW_CTE_PECA_EM_ABERTO`** (já traz descrições e exclusão de baixados);
   - "pedidos em aberto" ≈ **`VW_CarPedidosEmAberto`**;
   - contas a receber ≈ **`VW_Rec_Duplicata_Aberto`** (cobrança, com juros) ou `VW_Rec_DuplicatasEmAberto`;
   - contas a pagar ≈ **`VW_Pag_Titulo_Aberto`**;
   - clientes/fornecedores ≈ **`Fornecedores`** / **`Entidades`**.
2. **Duas famílias de "título em aberto"** no receber, ambas com 1 016 linhas hoje:
   - `VW_Rec_DuplicatasEmAberto` (simples, só saldo);
   - `VW_Rec_Duplicata_Aberto` (CNAB: juros/desconto, agência/conta, `idParcela`, exclui histórico
     tipo `'6'` e concatena um saldo anterior hoje vazio).
   Escolher pela finalidade (cobrança/boleto × consulta simples).
3. **`Vw_Rec_Inf_Comerciais`** já entrega o "prontuário" de crédito do cliente (32 indicadores) —
   candidata direta a endpoint de análise de cliente.
4. **`Fornecedores` (659)** é o universo de fornecedores da view (Tipo_Entidade ≠ 'C'); difere do
   total de `Clientes_Principal` (1 681) — usar a view para não expor clientes como fornecedores.
5. Views com **0 dados** hoje: `VW_Fat_SaldosFacionista`; tabela `Sdo_Rec_Duplicata_Aberto` (saldo anterior).
6. Views muito largas (`VW_LIV_SAIPROD` 219, `VW_Fat_Itens_Pedido_ComQMP` 118) servem de referência
   fiscal, mas a API deve expor **subconjuntos** de colunas.

## 4. Uso recomendado por endpoint

| Endpoint (legado) | View do `DBMicrodata_DGB` recomendada |
|-------------------|----------------------------------------|
| `/dados` (rolos) | `VW_CTE_PECA_EM_ABERTO` |
| `/contas-receber-programado` | `VW_Rec_Duplicata_Aberto` (filtrando `Vencimento`) |
| `/contas-pagar-programado` | `VW_Pag_Titulo_Aberto` |
| pedidos em aberto (novo) | `VW_CarPedidosEmAberto` |
| cliente/fornecedor (novo) | `Fornecedores` / `Entidades` / `Vw_Rec_Inf_Comerciais` |
| faturamento/desconto/custos | **portar `vwFaturamento`** (Estudo 12 — não há view equivalente exata) |

> As views de faturamento do `DBProDash` (Estudo 12) **permanecem** como as referências de cálculo;
> as views do `DBMicrodata_DGB` acima cobrem estoque, pedidos, títulos e cadastros.

## 5. Contagens de apoio

- 530 views (492 `vw_*`); módulos: CTE 55 · PCP 55 · CFC 30 · TNT 26 · CAR 25 · FIO 22 · SIC 20 ·
  RB 19 · REC 17 · FAT 16 · CUSTO 12 · RET 12.
- `VW_Rec_Duplicata_Aberto` 1 016 · `VW_Rec_DuplicatasEmAberto` 1 016 · `VW_Rec_Duplicata_Baixadas`
  28 872 · `Vw_Rec_Atrasos` 27 719 · `Vw_Rec_Inf_Comerciais` 1 681 · `VW_Pag_Titulo_Aberto` 133.
- `VW_Car_Pedido` 15 734 · `VW_Car_Pedido_Aberto` 20 712 · `VW_Car_Pedido_Aprov` 33 402 ·
  `VW_CarPedidosEmAberto` 159 · `VW_Fat_Cond_Pagto` 30 771.
- `VW_CTE_PECA_EM_ABERTO` 16 804 · `Fornecedores` 659 · `Entidades` 1 681 · `VW_FAT_TipoPedido` 3.
- `Sdo_Rec_Duplicata_Aberto` 0 · `Rec_Historicos` 19 · `VW_Fat_SaldosFacionista` 0.
