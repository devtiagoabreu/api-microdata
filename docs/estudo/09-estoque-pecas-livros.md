# Estudo 09 — Estoque de peças/tecidos e livros de estoque

Levantado em **SELECTs somente leitura**. Complementa o Estudo 02 (disponibilidade de rolos)
com os demais elos do estoque: **saldo, baixa, transferência, armazenagem e livro fiscal**.
Sem valores reais sensíveis — apenas estrutura e contagens.

## 1. Conceito geral

Neste ERP **não existe um módulo genérico `Est_*`** para o tecido acabado: o estoque físico de
peças/rolos é `Cte_Peca`, o resumo é `CTE_Saldos`, a saída é `CTE_Baixa`, e o espelho fiscal/
de valorização são os livros `Liv_Entradas`/`Liv_Saidas` + `Liv_Inventario`/`Liv_Kardex_EmpTerc`.

```
TEAR/URDUME  →  Cte_Peca (rolo/peça, endereçado em Gaveta)
                   │ CTE_Baixa.Tipo='V'  ⇔  Car_Itens_Romaneio (romaneio de venda)
                   │ CTE_Baixa.Tipo=NULL ⇔  baixa manual/transferência (CTE_Destino)
                   ▼
              CTE_Saldos (resumo mensal por produto/cor/desenho/categoria)
                   │
                   ▼
              Liv_Saidas/Liv_SaiProd (livro fiscal — faturamento) / Liv_Entradas (compras/retorno)
              Liv_Inventario/Liv_Itens_Inventario (inventário, metodo Liv_Tipo_Inventario)
              Liv_Kardex_EmpTerc (terceirizados)
```

## 2. Modelo de dados

### `CTE_Saldos` — resumo de saldo (5 577 · 13 colunas)

- Chave: `(Empresa, Situacao, EmpProd, Produto, Cor, Desenho, Categoria, Variante, Data)`
  com `Metros`, `Peso`, `Qtde`.
- Observado: apenas `Empresa '13'`; período `2018-07-01` → `2026-09-01`; total `Metros`
  ≈ 1 224 597, `Peso` ≈ 307 343 kg. Padrão de **snapshot mensal** (uma linha pela combinação
  produto/cor/data) — `Qtde` em linha não é o total de peças cadastradas.

### `CTE_Baixa` — baixa de peça (280 240)

- Chave de negócio: `(Empresa, Situacao, Nro_Rolo, Nro_Peca)` + `Data_Saida`.
- Tipos observados:
  - **`'V'`** — **274 402** baixas = mesmas 274 402 linhas de `Car_Itens_Romaneio`
    (sale romaneio, Estudo 04): romaneado p/ venda ⇒ peça sai do estoque disponível.
  - **`NULL`** — **5 838** baixas (2019-07-18 → 2026-06-12): transferências de armazém,
    consumo interno/manual. `Tipo` também aceita demais códigos de fluxo definidos no sistema.
- Colunas de fluxo: `Romaneio`, `Tipo`, `Corte_Altera`, `Observacao`, `Bloqueado`,
  `Nr_Lancamento_CFC` (vínculo contábil), `Data_Hora`.

### `CTE_Destino` (8) — destinos de transferência

`001` TECELAGEM · `002` MOVEN ESTOQUE · `003` ARMAZÉM PRÓPRIO · `004 S` · `005 W` ·
`006 WS` · `007 ST` · `008 K`. Flags por destino: `Transferencia`, `Confirma_Baixa`,
`Emitir_NF`, `Retorno_Facionista`. (Atende romaneios de transferência e baixa.)

### `CTE_RomTransf` / `CTE_Itens_RomTransf` — transferência de peças (4 266 / 130 622)

- `CTE_RomTransf`: `(Empresa, Romaneio, Tipo, Data_Rom)` + `Destino` (CTE_Destino),
  `Selecionado`, `Empresa_NF`/`Pedido_NF` (guia de remessa opcional),
  `Empresa_Consiste`/`Id_Consiste`, `Tipo_Comercializacao`.
- `CTE_Itens_RomTransf`: `(Empresa, Romaneio, ID_RomTransf)`, `Nro_Rolo`/`Nro_Peca`,
  `Codigo_Caixa`/`Entrada_Caixa`, `Empresa_RetFac`/`Romaneio_RetFac`/`ID_RomTransf_RetFac`
  (nível **retorno de faccionista** — bate com o `Car_Retorno`/`sp_Gerar_Pagar_SemiPronta`
  do Estudo 07).

### Armazenagem / endereçamento

- `CTE_Gaveta` (741) — gavetas (posições físicas); `CTE_GrupoGaveta` (9).
- Logs de movimentação de gaveta: `CTE_Peca_Gaveta_Log` (107 921) e coletor
  `CTE_PalmGav_Log` (213 527) e `Cte_Peca_Gaveta_Log` — trilha de cada peça armazenada.
- A peça carrega a localização real em `Cte_Peca.Gaveta`/`SubLote` (Estudo 02).

### Livros fiscais de estoque (valorização)

- `Liv_Entradas` (1 957) / `Liv_EntProd` (22 522) — entradas de compra/retorno (Estudo 07).
- `Liv_Saidas` (12 098) / `Liv_SaiProd` (34 043) — saídas por faturamento.
- `Liv_Inventario` (71) — cabeçalho de inventário por período:
  `(Empresa, Descricao, Cod_Liv_Inventario, Data, Bloqueado)`.
- `Liv_Itens_Inventario` (5 311) — items: `(Empresa, Cod_Liv_Inventario, Chave)`,
  `Produto`, `Produto_Concat`, `Unidade`, `Qtde`, `Vr_Unitario`, `Vr_Total`,
  `Conta_Contabil`, `ClassFisc`, `CNPJ` (terceiro), `Bloqueado`.
- `Liv_Tipo_Inventario` (5) — critério de valorização: `01` Preço Médio · `02` Preço Última
  Compra · `03` Maior Preço de Venda · `04` PEPS · `05` PEPS/MP/UC.
- `Liv_Kardex_EmpTerc` (2 283) — kardex de empresa terceirizada (tinturaria/facção).

## 3. Regra de disponibilidade (resumo Estudo 02 + baixa)

> Peça **em estoque** = `Cte_Peca` sem registro em `CTE_Baixa` (e `Nro_Rolo_Origem IS NULL`).
> Romaneio de venda (Tipo `'V'`) baixa 1:1 a linha de `Car_Itens_Romaneio`. Transferências
> (Tipo `NULL` + `RomTransf`) movem peça entre destinos sem faturamento.

```sql
-- Peças disponíveis por produto/cor (equivalente set-based à procedure)
SELECT CP.Produto, CP.Cor, COUNT(*) Pecas, SUM(CP.Metros) Metros
FROM Cte_Peca CP
LEFT JOIN CTE_Baixa CB
       ON CB.Empresa=CP.Empresa AND CB.Situacao=CP.Situacao
      AND CB.Nro_Rolo=CP.Nro_Rolo AND CB.Nro_Peca=CP.Nro_Peca
WHERE CP.Empresa='13'
  AND CP.Nro_Rolo_Origem IS NULL
  AND CB.Empresa IS NULL
GROUP BY CP.Produto, CP.Cor;
```

## 4. Observações e impacto na API

1. `CTE_Baixa.Tipo='V'` (274 402) tem **1:1 com `Car_Itens_Romaneio`** — dá para derivar
   disponibilidade diretamente das peças não romaneadas, sem a procedure.
2. `CTE_Saldos` é **resumo mensal agregado**, não transacional — para saldo "agora"
   prefira `Cte_Peca` × `CTE_Baixa`.
3. Transferência e retorno de faccionista passam por `CTE_RomTransf`/`CTE_Itens_RomTransf`
   e são a ponte para o CP (Estudo 07) — o estoque tece/beneficia em terceiros.
4. Valorização fiscal do estoque: `Liv_Itens_Inventario` + `Liv_Tipo_Inventario`
   (critério por inventário) e kardex de terceiros.

## 5. Contagens de apoio

- `Cte_Peca` 297 044 · `CTE_Baixa` 280 240 (`'V'` 274 402 / `NULL` 5 838).
- `CTE_Saldos` 5 577 · `CTE_RomTransf` 4 266 · `CTE_Itens_RomTransf` 130 622.
- `CTE_Gaveta` 741 · `CTE_Peca_Gaveta_Log` 107 921 · `CTE_PalmGav_Log` 213 527.
- `Liv_Entradas` 1 957 / `Liv_EntProd` 22 522 · `Liv_Saidas` 12 098 / `Liv_SaiProd` 34 043.
- `Liv_Inventario` 71 / `Liv_Itens_Inventario` 5 311 · `Liv_Kardex_EmpTerc` 2 283.