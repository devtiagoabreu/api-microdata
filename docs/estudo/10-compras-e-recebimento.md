# Estudo 10 — Compras e recebimento (o que realmente existe no banco)

Levantado em **SELECTs somente leitura**. Estrutura + contagens; **sem valores reais**.

## 1. Achado principal

O módulo de **pedido de compra do ERP (`Cmp_*`) está praticamente sem uso neste banco**:
`Cmp_Pedido`, `Cmp_Itens_Pedido`, `Cmp_PedAtend`, `Cmp_Necessidade`, `Cmp_Cotacao`,
`Cmp_Ini_PedAtend`, `Cmp_Itens_Entrega`, parcelas e rateios `Cmp_*_CCustos*` — **todos com 0
registros**. Só há cadastro/util: `Cmp_Comprador` (7 compradores) e `Cmp_Parametros` (1).

O que de fato alimenta as compras/entradas e o contas a pagar:

```
NF do fornecedor (nacional/serviço/importação) 
   └──► NF_Entradas (título a pagar) ──► NFE_Parcelas ──► Pag_Baixas        (Estudo 06/07)
▓▓▓
NF-e em XML importada
   └──► Liv_XML (+Emit/Item/DocRef/FormaPagto) ──► Liv_Entradas/Liv_EntProd  (fiscal/estoque)
▓▓▓
Retorno de terceiros (tecelagem) — módulo Ret_* em desuso (resíduo)
   └──► Ret_Aviso_Recebimento (218) / Ret_NFEntrada (1)
```

Ou seja: **não existe pedido de compra para consultar** — a entrada real é registrada
diretamente pela nota do fornecedor, e o título a pagar é gerado a partir dela.

## 2. Modelo de dados

### `NF_Entradas` — a "compra" efetiva (8 631 · Estudo 06)

Distribuição por **Série** (chave do tipo de fornecimento):

| Série | Qtde | Σ Vr_Total_Parcelas | Leitura provável |
|-------|-----:|--------------------:|------------------|
| `U` | 8 369 | ≈ R$ 114,6 mi | **Importação/internacional** (matéria-prima — fios/MP, fornecedores China etc.) |
| `UNICA` | 127 | ≈ R$ 175,6 mil | Série única (nacional, modelos variados) |
| `NFS` | 113 | ≈ R$ 318,7 mil | Serviço (NFS-e) |
| `NF` | 9 | ≈ R$ 31,4 mil | NF convencional |
| `''`, `0`, `INICA`, `19069`, `,` | 13 | ≈ R$ 249,2 mil | **Séries inconsistentes/livres** (digitação sem máscara) |

> `Serie` do `NF_Entradas` é **char(5) de digitação livre**, não há cadastro de séries de
> entrada (como no faturamento). A série `U` domina (97%) e precisa de confirmação do negócio
> para a API (importação de fios/insumos).

### `Liv_XML` — NF-e de entrada importadas via XML (1 690 · 71 colunas)

- Modelo `55` (1 690), `E_S='E'` (entrada); `Status_DFe` `'100'` (autorizada) 1 689 / `'150'` 1.
- Campos: `Chave_Acesso` (44), `Documento`/`Serie` (da NFe), `dhEmissao`, `NaturezaOperacao`,
  `tpOper`, `FinalidadeDFe`, totais (`Vr_Prod`, `Vr_ICMS`, `Vr_PIS`, `Vr_COFINS`, `Vr_Documento`,
  `Vr_TotTrib`, IBS/CBS — reforma tributária), `cRegTrib`, `Version`.
- Satélites com dados:
  - `Liv_XML_Emit` (1 690) — emitente (origem da nota; chave p/ fornecedor).
  - `Liv_XML_Item` (20 109) — itens da NFe.
  - `Liv_XML_DocRef` (817) — notas referenciadas (entradas por transferência/retorno fisc).
  - `Liv_XML_FormaPagto` (167) — forma de pagamento.
  - `Liv_XML_Cob` (66) — cobrança/duplicatas da NFe.
  - `Liv_XML_InfCPL` (1 318) — informações complementares.
- **Ponte com `NF_Entradas`:** NÃO há casamento por `(Documento, Serie)` (0 matches) — a NF-e
  importada alimenta o livro fiscal/estoque (`Liv_Entradas`/`Liv_EntProd`), e o título a pagar
  é lançado à parte (ou por outra chave). Validar com o negócio antes de montar consulta única.

### `Liv_Entradas` / `Liv_EntProd` — livro fiscal das entradas (1 957 / 22 522)

- Séries fiscais próprias (`'1'` 1 157, `'2'` 499, `'1 55'` 279, ...) — não confundir com a
  série de `NF_Entradas`. `Liv_EntProd` tem os itens (unidade, quant., valores, NCM/CFOP).
- É o destino da importação XML e das notas de entrada (Estudos 07 e 09).

### Módulo `Cmp_*` (composição completa, para referência)

| Grupo | Tabelas (todas 0 exceto indicadas) |
|-------|-------------------------------------|
| Pedido de compra | `Cmp_Pedido`, `Cmp_Itens_Pedido`, `Cmp_PedAtend`, `Cmp_Itens_PedAtend`, `Cmp_Peds_PedAtend`, `Cmp_Pedidos_Cancelados`, `Cmp_PedCompra_Vecto`, `Cmp_Pedido_Vencto`, `Cmp_Parcela_PedCompra`, `Cmp_Ped_CCustos_*`, `CMP_ProrrogacaoPedido` |
| Necessidade/cotação | `Cmp_Necessidade`, `Cmp_Itens_Necessidade`, `Cmp_Necessidade_Cotacao`, `Cmp_Cotacao`, `Cmp_Itens_Cotacao`, `Cmp_Prod_Cotacao*`, `Cmp_CotaComprador`, `Cmp_CotaMes`, `Cmp_CotaSaldo`, `Cmp_Tipo_Cotacao*`, `Cmp_Temp_Cotacao_Fornecedores` |
| Apoio | `Cmp_Comprador` (7 ✔), `Cmp_Parametros` (1 ✔), `Cmp_ParamEmp*`, `Cmp_Tipo_AvisoReceb`, `Cmp_Concorrentes*`, `Cmp_TempPedCompra`, `Cmp_Ini_PedAtend`, `Cmp_Itens_Entrega`, `Cmp_Itens_Obs`, `Cmp_Fornec_Desc_Cotacao`, `CMP_Divergencia*` |

### Módulo `Ret_*` — retorno de terceiros/tecelagem (resíduo)

- `Ret_Aviso_Recebimento` (218) + `Ret_Aviso_Itens_*` (2 083) — avisos de recebimento de
  matéria-prima.
- `Ret_NFEntrada` (1), `Ret_Lancamentos` (1), `Ret_ItensNFEntrada` (1) — quase vazio.
- Cadastros pequenos: `Ret_Grupos` (5), `Ret_SubGrupos` (5), `Ret_Secao` (4), `Ret_Unidades`
  (5), `Ret_Tributacoes` (11), `Ret_Historicos` (9), `Ret_Encargos` (3), `Ret_Moedas` (2),
  `Ret_ParamEmp` (4), `Ret_Tabelas` (1). Demais tabelas 0.

## 3. Como o CP nasce (consolidação Estudo 07, com dados reais)

1. Nota de fornecedor lançada no contas a pagar → `NF_Entradas` (série `U`/`UNICA`/`NFS`/`NF`).
2. Parcelamento → `NFE_Parcelas` (condições de pagto).
3. Baixa → `Pag_Baixas` (predominância histórico `'07'` — internet banking).
4. Paralelamente, a NF-e (XML) importada alimenta `Liv_XML` → `Liv_Entradas`/`Liv_EntProd`
   (fiscal/estoque) e a produção (tecelagem) consome via `CTE_*`/`Ret_*`.

## 4. Impacto na API

1. **Não implementar endpoints sobre `Cmp_Pedido`/`Cmp_Cotacao`** (sem dados). 
2. "Compras" na API = **notas de entrada** (`NF_Entradas` + `Liv_Entradas`) e **NF-e XML**
   (`Liv_XML`), além do CP já mapeado.
3. Tratar a **série livre** de `NF_Entradas`: whitespace/RTRIM + excluir/agrupar os 13 registros
   inconsistentes (`''`, `'0'`, `'INICA'`, `'19069'`, `','`) em consultas agregadas.
4. Confirmar com o negócio o significado da série `U` (importação) antes de expor como filtro.

## 5. Contagens de apoio

- `NF_Entradas` 8 631 · `NFE_Parcelas` 8 736 · `Pag_Baixas` 8 603 (Estudo 06).
- `Liv_XML` 1 690 · `Liv_XML_Item` 20 109 · `Liv_XML_Emit` 1 690 · `Liv_XML_DocRef` 817 ·
  `Liv_XML_FormaPagto` 167 · `Liv_XML_Cob` 66 · `Liv_XML_InfCPL` 1 318.
- `Liv_Entradas` 1 957 · `Liv_EntProd` 22 522 · `Liv_Saidas` 12 098 · `Liv_SaiProd` 34 043.
- `Cmp_Comprador` 7 · módulo `Cmp_` demais 0 · `Ret_Aviso_Recebimento` 218 / itens 2 083.