# Estudo 19 — Estoque de peças (Cte_Peca) em detalhe

Levantado com **SELECTs somente leitura** (catálogo, colunas, contagens e agregados). Sem dados reais.

## 1. Panorama das tabelas

| Tabela | Linhas | Papel |
|--------|-------:|-------|
| **`Cte_Peca`** | 297 044 | cadastro/estoque da peça (rolo+peça) |
| **`CTE_Baixa`** | 280 240 | baixa da peça (saída) |
| `CTE_Saldos` | 5 577 | saldo consolidado por produto/cor/desenho/categoria |
| `Car_Romaneio` | 14 596 | romaneio de venda (cabeçalho) |
| `Car_Itens_Romaneio` | 274 402 | itens do romaneio (peças efetivamente romaneadas) |
| `CTE_RomTransf` | 4 266 | romaneio de **transferência** (cabeçalho) |
| `CTE_Itens_RomTransf` | 130 622 | itens da transferência |
| `Cte_Peca_Gaveta_Log` | 107 921 | log de gaveta |
| `CTE_PalmGav_Log` | 213 527 | log de coletor (palm) |
| `CTE_Obs_Peca` | 3 794 | observações por peça |
| `Cte_Gaveta` (741) / `Cte_GrupoGaveta` (9) | — | endereçamento/gavetas |
| `CTE_Mesclagem` (293) | — | mesclagem de peças |
| `CTE_Operador` (16) | — | operadores |

`Car_Romaneio` cobre **2018-08-01 → 2026-09-17** (em uso hoje).

## 2. `Cte_Peca` (101 colunas)

Chave natural: **`Empresa` + `Situacao` + `Nro_Rolo` + `Nro_Peca`**. Hoje todas as peças têm
`Situacao='001'` (= **TINTO**, `Car_Situacoes`, 3 situações cadastradas).

Dimensões/identificação: `Metros` (todos > 0), `Peso`, `Peso_Bruto`, `Largura`, `Metros_Quadrados`,
`Fator_Quebra`, `Custo_Unitario`; produto `EmpProd`/`Produto`/`Categoria`/`Cor`/`Desenho`/`Variante`;
`Tear`, `Operador`, `Revisadeira`, `Turma`, `Tecelao`; lote/coluna `SubLote`, `Nuance`, `Gaveta`,
`Carrolao`.

Origem/terceiros: `Terceiros`, `Tipo_Fornec`, `Fornecedor`, `Documento`, `Serie`, `Empresa_Remessa`,
`Nro_Rolo_Remessa`/`Nro_Peca_Remessa`, `Nro_RoloImp`/`Nro_PecaImp`, `Nro_Rolo_Cliente`/`Nro_Lote_Cliente`,
`Empresa_Tinto`/`Romaneio_Tinto`.

Vínculos de produção/faturamento: `Pedido`, `Empresa_Pedido`, `Ordem_Producao`, `Ordem_Servico`,
`Ficha_Tecnica`, `Ficha_Transfer`, `Kit`/`Seq_Kit`, `Id_SC`, `Encomenda` (`Enc_Urd`/`Enc_Tram`),
`Aviso`/`Item_Aviso`.

Controle: `Data_Entrada`, `Alt_*` (alterações), `Bloqueado`, `Restricao`, `Turno`, `RepesagemEfetuada`,
`Devolucao`/`Peca_Devolucao`, `Rolo_Devolucao`, `Data_Corte`, `Liberacao_Operador`, flags de integração
(`AguardandoPesagem`, `carroCargaProducao`, `operadorLiberarDifTolSemiPronta`).

Agregado: **20 393 258 m** de tecido (média 68,65 m/peça; 0,8–1 931,3 m).

## 3. `CTE_Baixa` (11 colunas)

`Empresa`, `Situacao`, `Nro_Rolo`, `Nro_Peca` (mesma chave da peça), `Data_Saida`, `Romaneio`,
**`Tipo`**, `Corte_Altera`, `Observacao`, `Bloqueado`, `Nr_Lancamento_CFC`.

Distribuição de `Tipo`: **`'V'` = 274 402** (venda — casa exatamente com `Car_Itens_Romaneio`) e
**`NULL` = 5 838** (baixas sem romaneio, ajuste/consumo). Total **280 240**.

## 4. Regra de "peça em aberto" (`VW_CTE_PECA_EM_ABERTO`)

A view (Estudo 13, 16 804 linhas) é exatamente:

```sql
SELECT A.*, descrições de Produto/Situação/Cor/Desenho/Categoria/Variante
FROM CTE_PECA A
  JOIN Produtos      C ON C.Empresa=A.EmpProd AND C.Codigo=A.Produto
  JOIN Car_Situacoes G ON G.Codigo=A.Situacao
  JOIN Car_Cores     D ON D.Codigo=A.Cor
  JOIN Car_Desenhos  E ON E.Codigo=A.Desenho
  JOIN Car_Categorias F ON F.Codigo=A.Categoria
  LEFT JOIN Car_Variante V ON V.Codigo=A.Variante
WHERE NOT EXISTS (SELECT 1 FROM CTE_Baixa B
                  WHERE B.Empresa=A.Empresa AND B.Nro_Rolo=A.Nro_Rolo AND B.Nro_Peca=A.Nro_Peca)
```

Confere: **297 044 − 280 240 = 16 804** peças em aberto. Os joins usam os cadastros `Car_*`
(situações/cores/desenhos/categorias/variantes) e `Produtos`.

## 5. Romaneios

- **Venda** — `Car_Romaneio` (42 col: `Empresa`, `Romaneio`, `Tipo`, `Pedido`, `Cliente`, `Data_Rom`,
  `Nota_Fiscal`, `Status`, `Situacao_Ret`, `Tipo_Comercializacao`, `Bloqueado`, `eh_Proprio`…) e
  `Car_Itens_Romaneio` (55 col: chave `Empresa+Romaneio+Tipo+Incremento`; `Nro_Peca`, `Nro_Item_Pedido`,
  `Rolos`, `Mts_Rolo`, `Vr_Unitario`, `Comissao`, `Codigo_Produto_Concat`, `Fardo`).
  Todos os itens atuais têm `Tipo='V'`.
- **Transferência** — `CTE_RomTransf` (`Empresa`, `Romaneio`, `Tipo`, `Data_Rom`, `Destino`,
  `Empresa_NF`, `Pedido_NF`, `Tipo_Comercializacao`) e `CTE_Itens_RomTransf`
  (`Nro_Rolo`/`Nro_Peca`, `Codigo_Caixa`, `Entrada_Caixa`, e par de retorno `Romaneio_RetFac`).

## 6. Saldos, gavetas e logs

- **`CTE_Saldos`** (5 577; 21 produtos; 1 empresa; **1 224 596,74 m**): `Empresa`, `Situacao`, `EmpProd`,
  `Produto`, `Cor`, `Desenho`, `Categoria`, `Variante`, `Data` → `Metros`, `Peso`, `Qtde`, `ID_Saldo`.
  É o saldo materializado por combinação de atributos (não por peça).
- **`Cte_Gaveta`** (741) / `Cte_GrupoGaveta` (9): endereçamento; `Cte_Peca_Gaveta_Log` (107 921) e
  `CTE_PalmGav_Log` (213 527) registram movimentação de gaveta/coletor.
- `CTE_Obs_Peca` (3 794) — observações; `CTE_Mesclagem` (293) — junção de peças.

## 7. Impacto na API (read-only)

1. **Endpoint de estoque de peças** = `VW_CTE_PECA_EM_ABERTO` (16 804) ou `CTE_PECA`
   menos `CTE_Baixa` (297 044/280 240). Filtrar por `Produto`, `Cor`, `Desenho`, `Categoria`,
   `Variante`, `Situacao`, `Gaveta`.
2. **Todo `SELECT` em `Cte_Peca` deve usar a chave completa** `Empresa+Situacao+Nro_Rolo+Nro_Peca`
   (peça é identificada por rolo+peça; `Situacao` hoje é '001').
3. **Saldos consolidados** → `CTE_Saldos` (21 produtos) — mais barato que agregar 297k peças.
4. **Romaneios**: venda (`Car_Romaneio`/`Car_Itens_Romaneio`) e transferência (`CTE_RomTransf`).
   A baixa (`CTE_Baixa.Tipo='V'`) liga a peça ao romaneio de venda.
5. **Performance**: as tabelas de log (`CTE_PalmGav_Log` 213k, `CTE_Itens_RomTransf` 130k,
   `Cte_Peca_Gaveta_Log` 107k) devem ficar **fora** dos endpoints de leitura comuns.
6. `CTE_Itens_RomTransf` revela o par entrada/saída (`Codigo_Caixa`/`Entrada_Caixa`) para transferência
   de caixas de fios.

## 8. Contagens de apoio

- `Cte_Peca` 297 044 · `CTE_Baixa` 280 240 (`V` 274 402 / `NULL` 5 838) → em aberto **16 804**.
- `Car_Romaneio` 14 596 (2018-08-01 → 2026-09-17) · `Car_Itens_Romaneio` 274 402 (100% `Tipo='V'`).
- `CTE_RomTransf` 4 266 · `CTE_Itens_RomTransf` 130 622.
- `CTE_Saldos` 5 577 linhas / 21 produtos / 1 224 596,74 m.
- Logs: `CTE_PalmGav_Log` 213 527 · `Cte_Peca_Gaveta_Log` 107 921.
- `Car_Situacoes` 3 (só '001'=TINTO em uso).
- Metros: total 20 393 258,276 m; média 68,654 m; mín 0,8 m; máx 1 931,3 m.
