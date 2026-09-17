# Estudo 14 — Views dos módulos de produção (CTE/PCP/CFC) e mapa de módulos ativos

Levantado em **SELECTs somente leitura**. Definições, contagens de views e **contagens de linhas**
das tabelas-base. Sem valores reais.

Objetivo: aprofundar as views de produção (`VW_CTE_*`, `VW_PCP_*`, `VW_Cfc_*`) e descobrir **quais
módulos realmente têm dados** neste banco.

## 1. Achado principal

Os módulos de **produção, PCP, CFC, FIO, TNT (tinturaria), loja, orçamento, PDV e custo existem no
schema mas estão VAZIOS** em `DBMicrodata_DGB`. As suas tabelas-base têm 0 linhas e, por
consequência, **todas as views correspondentes retornam 0**:

| Verificado | Resultado |
|-----------|-----------|
| `Cte_Romaneio`, `Cte_Itens_Romaneio`, `CTE_Ordem_Producao`, `CTE_Rolada`, `CTE_OP_Rolada` | 0 |
| `CTE_Saldos_Tintur`, `CTE_Mov_Fios`, `CTE_Apontamento`, `CTE_Urd_Rolos`, `CTE_RU_Rolada` | 0 |
| `CTE_Ficha_Tecnica`, `CTE_Itens_FT`, `CTE_Romaneio_Urdume` | 0 |
| `PCP_Pedido`, `PCP_Pedido_Itens`, `PCP_Romaneio(_Itens)`, `PCP_Estoque(_Saldo)`, `PCP_OrdemProd`, `PCP_Prod_Material`, `PCP_Grade_Produto`, `PCP_NFEntrada` | 0 |
| `CFC_Pedido`, `Cfc_Itens_Pedido`, `CFC_Romaneio`, `cfc_estoqueParte`, `Cfc_Produtos`, `Cfc_Ordem_Producao`, `Cfc_NFEntrada` | 0 |
| `FIO_PCP_Ordem`, `FIO_PCP_Pedido`, `Ret_CxsFios` | 0 |
| Views `VW_CTE_Saldos_Tintur`, `VW_CTE_Situacao_Producao`, `Vw_Cte_Romaneio`, `VW_Cte_Ordem_Producao_Saldo`, `VW_CTE_ConsumoFios`, `VW_PCP_Pedido*`, `VW_CFC_*`, `VW_FIO_PCP_*` | 0 |

> **Exceção — views CTE baseadas em `Cte_Peca`:** estas devolvem a **base inteira de peças**
> (**297 044** linhas), pois são um catálogo de peças/rolos, não controle de produção:
> `VW_CTE_Campos_Layout_Embaladora`, `Vw_Cte_PontuacaoABNT`, `Vw_Cte_ProducaoMalhaTear`,
> `VW_CTE_PECA_EM_ABERTO` (16 804 — só as em aberto).
> Já as views de **defeito/produção** (`Vw_Cte_Pecas_Defeitos`, `vw_Cte_Producao_Malha_Operador`,
> `VW_CTE_VariantesFT`, `Vw_Cte_SetorAtualRolete`) retornam 0.

Isto confirma que este banco é de uma operação **comercial / de conversão** (compra MP, estoque de
peças, venda, faturamento, financeiro, fiscal) — **sem controle de produção/PCP/confecção**.

## 2. Mapa de módulos (tabelas × linhas)

Tabelas agrupadas pelo prefixo, somando linhas (`sys.partitions`):

### Populados (alvo da API)

| Módulo | Tabelas | Linhas | Leitura |
|--------|--------:|-------:|---------|
| `cte` (peças/baixa/transf.) | 395 | 1 047 070 | estoque de peças/rolos (**não** produção) |
| `Rec` | 132 | 590 037 | contas a receber |
| `Fat` | 302 | 544 796 | faturamento |
| `Car` | 189 | 451 861 | pedidos/romaneio |
| `rpt` | 52 | 239 053 | relatórios |
| `Liv` | 231 | 205 057 | livros fiscais |
| `Log` | 12 | 95 388 | auditoria |
| `Notas` | 13 | 71 686 | notas |
| `Fig` | 39 | 58 229 | figura fiscal |
| `NFE` | 5 | 29 894 | NF-e |
| `Pag` | 62 | 18 348 | contas a pagar |
| `Clientes` | 56 | 15 403 | cadastros |
| `FOL` | 274 | 10 758 | folha (interna) |
| `Cheques` | 3 | 10 135 | cheques |
| `Cmt` | 36 | 5 270 | comodato |
| `NF` | 3 | 8 631 | notas de entrada |

### Vazios / residuais (fora do escopo)

| Módulo | Tabelas | Linhas |
|--------|--------:|-------:|
| `PCP` | 353 | 123 |
| `CFC`/`Cfc` | 302 | 69 |
| `Fio`/`FIO` | 78 | 33 |
| `Tnt`/`TNT` (tinturaria) | 252 | 17 |
| `SCT` | 18 | 17 |
| `Loj` (loja) | 111 | 39 |
| `PLM` | 24 | 40 |
| `Orc` (orçamento) | 42 | 9 |
| `PDV` | 22 | 19 |
| `SIC` | 76 | 1 |
| `Custo` | 63 | 1 |
| `FNN` | 11 | 0 |

## 3. Catálogo das views de produção (154 catalogadas)

Levantadas 154 views nos grupos `VW_CTE%` (57), `VW_PCP%` (55), `VW_Cfc%/CFC` (~35) e `VW_FIO_PCP%`
(7). Resumo por grupo (as que têm dados estão marcadas):

- **`VW_CTE_*`** — produção/tinturaria/ordem (todas 0): `VW_CTE_SimulacaoCusto*`, `VW_CTE_Rolos_*`,
  `VW_CTE_ConsumoFios*`, `VW_CTE_OP_*`, `VW_CTE_Saldos_Tintur*`, `Vw_Cte_Romaneio`,
  `Vw_Cte_SaldoFacionista`, `VW_CTE_Mov_Fios_Saldo`, `Vw_Cte_SemiPronta`, `VW_CTE_RelEnvioRetorno`.
  - **Com dados (catálogo de peça):** `VW_CTE_Campos_Layout_Embaladora` (49 col, 297 044),
    `Vw_Cte_PontuacaoABNT` (8 col, 297 044), `Vw_Cte_ProducaoMalhaTear` (18 col, 297 044),
    `VW_CTE_PECA_EM_ABERTO` (19 col, 16 804).
- **`VW_PCP_*`** — planejamento/pedido/estoque (todas 0, exceto 2):
  `VW_PCP_Pedido`, `VW_PCP_Pedido_Itens`, `VW_PCP_Estoque*`, `VW_PCP_PedRom`, `VW_PCP_Grade_Produto`,
  `VW_PCP_NFEntrada*`, `VW_PCP_ListOrcamento`, `VW_PCP_Rel_ProdutosMovOP`, `VW_PCP_Pedidos_*`.
  - **Com dados:** `VW_PCP_Produtos_Estoque` (17 col, 364: estoque dos produtos do PCP),
    `vw_PCP_Produtos` (12 col, 364: catálogo de produtos PCP).
  - `VW_PCP_Produto_Fabrica` (89 col, 1 linha) — praticamente vazia.
- **`VW_Cfc_*`/`VW_CFC_*`** — confecção/coleção/grade/promoção (todas 0), ex.: `VW_CFC_PEDIDO` (75 col),
  `Vw_Cfc_PedRom` (44), `Vw_Cfc_Produtos_Vendidos` (24), `VW_CFC_ROMANEIO`, `Vw_CFC_Promo_*`.
- **`VW_FIO_PCP_*`** — fios (todas 0), ex.: `VW_FIO_PCP_Pedidos` (28), `VW_FIO_PCP_Ordem` (23).

## 4. Views quebradas encontradas

- **`VW_CTE_RelEnvioRetorno`** — erro `Ambiguous column name 'Data_Retorno'` (coluna ambígua no
  SELECT): a view **não executa** hoje.
- **`VW_Cte_Romaneio_GeraFatAuto`** — erro `Invalid object name` (referência a objeto inexistente,
  provável `cross-database`).
- `VW_PCP_Produtos_RevBloqueado` referencia `PCP_Produtos_Revisoes` — conferir existência se for usar.

## 5. Impacto na API

1. **Confirmar o escopo:** a API cobre **comercial + financeiro + fiscal + estoque de peças +
   cadastros + compras**. Endpoints de **PCP, produção/ordem, tinturaria, CFC/coleção, loja,
   orçamento, PDV e custo não têm dados** — não implementar (ou responder vazio explicitamente).
2. As views de **produção não devem ser portadas** (referenciam tabelas vazias).
3. Manter como candidatas a uso apenas as views CTE **de peça** já apontadas no Estudo 13
   (`VW_CTE_PECA_EM_ABERTO` etc.).
4. O estoque de **fios** (`FIO_*`) e **caixas de fios** (`Ret_CxsFios`) está vazio — o controle de
   fios não é usado.

## 6. Contagens de apoio

- Catei **154 views** de produção (CTE 57 / PCP 55 / CFC ~35 / FIO-PCP 7).
- Views com dados: `VW_CTE_Campos_Layout_Embaladora` / `Vw_Cte_PontuacaoABNT` /
  `Vw_Cte_ProducaoMalhaTear` = 297 044 · `VW_CTE_PECA_EM_ABERTO` = 16 804 ·
  `VW_PCP_Produtos_Estoque` / `vw_PCP_Produtos` = 364 · `VW_PCP_Produto_Fabrica` = 1.
- Tabelas-base de produção (CTE ordem/rolada/tinturaria, PCP, CFC, FIO): **0 linhas**.
- Módulos vazios: PCP 123 · CFC 69 · Fio 33 · Tnt 17 · SCT 17 · Loj 39 · PLM 40 · Orc 9 · PDV 19 ·
  SIC 1 · Custo 1 (linhas somadas).
