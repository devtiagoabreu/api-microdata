# Estudo 07 — Jornada do título a pagar (origem → parcelas → baixa)

Levantado em **SELECTs somente leitura**. Contém apenas estrutura, fluxo (via procedures de
geração) e **contagens/agregados** — nenhum dado real sensível.

## 1. Visão geral

Complementa o Estudo 06 (estrutura do CP). Aqui o foco é **como nasce um título a pagar** e
como ele chega à `NFE_Parcelas`/`Pag_Baixas`. Três origens mapeadas:

1. **NF-e de compra / entrada** → `NF_Entradas` (`Ret_Lanca_Entradas`, `Gera_Ret_NFEntrada`, `sp_GeraNFE_de_NFS*`).
2. **Retorno de peças processadas em terceiros** (módulo `Ret_*` — tecelagem/facção) →
   `NF_Entradas` (`Gera_Ret_NFEntrada`, `Ret_Lanca_Entradas`).
3. **Produção semi-pronta / terceirização** (`Car_Retorno`) → `NF_Entradas`
   (`sp_Gerar_Pagar_SemiPronta`).

Em todos os casos o título é **parcelado** por `Condicoes_Pagto_Parcelas` → `NFE_Parcelas`,
**rateado por centro de custo** em `NFE_CCustos_*` e, ao final, **baixado** em `Pag_Baixas`.

Títulos a pagar usam as empresas `'13'` e `'14'` (mesmas do faturamento/CR).

## 2. Modelo de dados (complemento ao Estudo 06)

### Parcelamento

- `Condicoes_Pagto` — condições de pagamento (FK p/ os títulos via `Cod_Parcelas`).
- `Condicoes_Pagto_Parcelas` — parcelas de cada condição: `Codigo_Pagto_Parcelas`,
  `Incremental_Pagto_Parc`, `Tipo_Pagto_Parcelas` (`'1'`/datas?), `Dias_Pagto_Parcelas`,
  `ID_Meio_Pagamento`, `Empresa_R`.
- `Condicoes_Pagto_Grupo` — agrupamento por empresa.

### Rateio de custo do título

- `NFE_CCustos` (7 col., 0 reg.) — centro de custo do cabeçalho (em desuso?).
- `NFE_CCustos_Departamento` (12 col., **8 576**) — rateio por departamento:
  PK do título + `ItemDespRec`, `Item`, `Primeiro_nivel`, … (ex. marcador `Documento=' T1204'`
  = título de "T"…, `Serie='U'`).
- `NFE_CCustos_DespesasReceitas` (12 col., **8 591**) — rateio por conta de despesa/receita.
- `Pag_Centro_Custo` (0), `Pag_DespesasReceitas` (91), `Pag_Diario` (23 col., 4) — diário de
  pagamento/lançamento gerado pelas procs.

## 3. Procedures de geração (papel no fluxo)

| Procedure | Papel | Tabelas que move/grava |
|-----------|-------|------------------------|
| `Gera_Ret_NFEntrada` | Gera o título a pagar a partir do módulo de **retorno de terceiros** (`Ret_NFEntrada`, `Ret_Lancamentos`, `Ret_ItensNFEntrada`) e **compras** (`Cmp_Pedido`, `Cmp_PedAtend`, `Cmp_Itens_*`); parcelas via `Condicoes_Pagto_Parcelas`; também grava `Pag_Diario`. | `NF_Entradas`, `NFE_Parcelas`, `Pag_Diario` |
| `Ret_Lanca_Entradas` | Consolida o lançamento: além do CP, grava o **livro fiscal** de entradas (`Liv_Entradas`, `Liv_EntProd`, `Liv_EntNatOp`) e as versões `*_Recebimento` (`NF_Entradas_Recebimento`, `NFE_Parcelas_Recebimento`, `Liv_*_Recebimento`). | `NF_Entradas`, `NFE_Parcelas`, `NFE_CCustos`, `Liv_Entradas*` |
| `sp_Gerar_Pagar_SemiPronta` | Gera CP de **produção semi-pronta/terceirizada** a partir de `Car_Retorno`/`Car_Itens_Retorno`, com rateio `NFE_CCustos*` + `Pag_DespesasReceitas`, `Pag_CCusto_Departamento`, `Pag_Diario`. | `NF_Entradas`, `NFE_Parcelas`, `NFE_CCustos*`, `Pag_Diario` |
| `SP_Transfere_CP` | **Transfere** um título entre empresas (lê em `#tmp` e re-grava/`UPDATE` `NF_Entradas`, `NFE_Parcelas`, `NFE_CCustos*`, `Pag_Baixas` com `@EmpresaN`). | `NF_Entradas`, `NFE_Parcelas`, `NFE_CCustos*`, `Pag_Baixas` |
| `SP_Ret_LancPagEmpAux` | Lança pagamento para empresa auxiliar. | `NF_Entradas`, `NFE_Parcelas` |
| `sp_GeraNFE_de_NFS` / `_Filial` | Gera NF-e de entrada a partir de NFS (serviço). | `NFE_Parcelas`, `NF_Entradas` |
| Triggers `INSUPT_/DELUPT_Peds_PedAtend` | Mantêm `NF_Entradas`/`NFE_Parcelas` sincronizadas ao atender pedido de compra. | `NF_Entradas`, `NFE_Parcelas` |

> As `SP_Rec_GeraDoc`/`SP_Rec_GeraNota` (lado do **receber**, Estudo 05) são o espelho dessas
> gerações no lado oposto — o padrão é o mesmo (girar título a partir de transação de negócio).

## 4. CNAB/SISPAG no contas a pagar

- **Praticamente vazio no CP**: `Pag_Transacao`, `Pag_Remessa`, `Pag_Parcelas_SISPAG`,
  `Pag_SisPag_Layout/Remessa/Retorno_240/500`, `Pag_CNAB_*` — todas com **0 registros**.
- A baixa predominante é por **internet** (`Pag_Historicos '07'`, 7 554 de 8 603 baixas),
  batendo com a ausência remessas de CP: bancos são pagos pelo internet banking e lançados
  manualmente/por arquivo de retorno de outro sistema.
- O **CNAB ativo** do banco está no **receber** (`Rec_Remessa` 25 872, `Rec_RetornoOcorr` 56 539,
  `Rec_CNAB_BcAgCc` 3).
- `Pag_RetornoCNAB_TipoCampo` (14) existe para parsing de retorno 240, mas sem dados de remessa.

## 5. Observações e impacto na API

1. **Origem canônica do título em aberto (CP)** = `NFE_Parcelas` com
   `NFE_Parcelas.Valor − Σ(Pag_Baixas.Valor_Liquido) > 0`, juntando
   `NF_Entradas` (cabeçalho), `Clientes_Principal` (fornecedor via `(Tipo,Codigo)`) e
   `NFE_CCustos_*` (rateio).
2. **Não há FK** do pedido de compra (`Cmp_Pedido`/`Cmp_PedAtend`) nem do retorno (`Ret_*`)
   para o título — o vínculo é implícito (número do documento/`Referente`). Se a API precisar
   rastrear origem, será via `Documento`/`Referente` ou invocando as procedures (indesejável
   na fase read-only) — validar com o negócio.
3. CNAB do CP não deve ser priorizado na API (sem dados); o CNAB real a modelar é o do **receber**.
4. `SP_Transfere_CP` explica títulos entre `Empresa` '13'/'14' — filtrar por `Empresa` consistente.

## 6. Contagens de apoio

- `NF_Entradas`: 8 631 (2011-11-19 → 2026-09-17; Σ `Vr_Total_Parcelas` ≈ R$ 115,4 mi; `Baixado`
  'S' 8 514 / 'N' 117; Empresas '13' 8 236 / '14' 395).
- `NFE_Parcelas`: 8 736 (vencimento 2017-06-20 → 2029-02-05; Σ ≈ R$ 115,4 mi).
- `Pag_Baixas`: 8 603 (2018-06-11 → 2026-09-15; Σ `Valor_Liquido` ≈ R$ 111,1 mi).
- Rateio: `NFE_CCustos_Departamento` 8 576 · `NFE_CCustos_DespesasReceitas` 8 591.
- `Pag_Diario` 4 · `Pag_DespesasReceitas` 91 · `Pag_Centro_Custo` 0.
- Cheques emitidos: `Pag_ChequesEmi_Duplicata` 8 237.