# Estudo 16 — Catálogo de triggers (672)

Levantado com **SELECTs de catálogo** (`sys.triggers`, `sys.sql_expression_dependencies`,
`OBJECT_DEFINITION`) e leitura de corpos. Apenas estrutura/efeitos; sem dados reais.

## 1. Inventário

| Métrica | Valor |
|--------|------:|
| Triggers DML (parent_class=1) | **672** |
| Tabelas com trigger | 285 |
| Desabilitados | 10 |
| `NOT FOR REPLICATION` | 180 |
| Eventos: INSERT / UPDATE / DELETE | 279 / 319 / 307 (um trigger pode cobrir vários) |

**Nenhuma trigger `INSTEAD OF`** nas tabelas-chave — todas `AFTER` (exceto
`Produtos_Fornecedores` com 1 `INSTEAD OF DELETE`).

### Prefixos de nome

`TG_` 518 · `DEL_` 42 · `UPT_` 34 · `INS_` 20 · `INSUPT_` 17 · `DELUPT_` 16 · `TD_` 6 · `TI_` 3 ·
`TIUD_` 3 · `TR_` 2 · `TA_` 2 (+ poucos avulsos). Nomenclatura reflete o evento coberto
(`INS`/`UPT`/`DEL`/`INSUPT`/`DELUPT`/`TIUD`).

### Tabelas com mais triggers

`CTE_Peca` 38 · `Fat_Pedido` 16 · `Car_Itens_Romaneio` 16 · `Ret_Lancamentos` 13 ·
`Car_Itens_Pedido` 10 · `CTE_Saldos_Tintur` 9 · `Ret_ItensNFEntrada` 9 · **`Produtos` 8** ·
**`NF_Entradas` 8** · `Liv_EntProd` 8 · `Fat_Itens_Pedido` 8 · `CTE_Baixa` 8 · **`Car_Pedido` 7** ·
`Car_Romaneio` 7 · `Pag_Baixas` 6 · `Notas_Fiscais_Parcelas` 5 · `Rec_Baixas` 5.

## 2. Famílias de triggers

### 2.1 Trava de fechamento mensal (`*_Fech_Ins/Upd/Del`)

Presentes nas tabelas financeiras/fiscais (`Rec_Baixas`, `Pag_Baixas`, `NF_Entradas`,
`Notas_Fiscais_Rec`, `NFE_Parcelas`, `Pag_Titulo_Lancamentos`, `Notas_Fiscais_CCD`, etc.).
Corpo ~6–8k chars com lógica idêntica:

- Conta linhas de `Inserted`/`Deleted` com `Bloqueado='N'` e data `>` **maior mês fechado**;
- Consulta a tabela `*_Fechamento_Mensal` (`Empresa`, `Mes`, `Data_Hora`, `Usuario`);
- Se tentar alterar um mês fechado → **`RAISERROR('Já foi realizado o fechamento deste mês, o valor
  não pode ser alterado. Referência: Rec_Baixas',11,1)` + `ROLLBACK`**;
- Exceção: campos listados em **`Rec_Fechamento_Campos_Alterados`** (`Tabela`, `Campo`; 67 linhas)
  podem mudar mesmo no mês fechado (ex.: flag `Baixado` durante a baixa).

> **Estado atual: nenhum mês está fechado.** Todas as tabelas `*_Fechamento_Mensal` têm **0 linhas**
> (`Rec_`, `Pag_`, `Fat_`, `Car_`, `CTE_`, `Bco_`, `CCD_`, `Ret_`, etc.), exceto as de SPED Livro 3
> (`Lv3_SdoEst_Fechamento` 4 807, `Lv3EstoqueFechamentoEntregue` 3 512). As travas existem mas estão
> inertes hoje.

### 2.2 Campos derivados / denormalizados por trigger

| Trigger (tabela) | Efeito |
|------------------|--------|
| `TIUD_BaixasRec` (`Rec_Baixas`) | atualiza **`Notas_Fiscais_Rec`** |
| `TIUD_Baixas` (`Pag_Baixas`) | atualiza **`NF_Entradas`** |
| `TG_REC_Id_Parcela` (`Notas_Fiscais_Parcelas`) | gera/atribui id da parcela |
| `TG_INS_Rec_Baixas_DtLanc` (`Rec_Baixas`) | carimba data de lançamento |
| `Tg_*_DtLanc` (Rec_Integracao, Pag_Integracao, Notas_Fiscais_Rec) | carimba data |
| `TG_CarOrc_Itens_Pedido`, `tgi`/`upt` de itens | sincroniza itens |

> **Consequência para a API read-only:** campos como `Baixado`/valores em `Notas_Fiscais_*` podem ser
> **derivados** — ler o valor materializado, **não recalcular**.

### 2.3 Fan-out de cadastro (`Produtos`)

- **`TGI_PRODUTOS`** (~24k chars) → replica produto para **11 tabelas**: `Produtos_CodBarras`,
  `Produtos_Fornecedores`, `Produtos_ItensRelac`, `Produtos_Montagens`, `Produtos_Precos`,
  `Produto_Desmembra`, `Ret_ItensNFEntrada`, `Ret_Lancamentos`, `Ret_Precos`, `Ret_Promocao`,
  `Ret_Zebra`.
- `TG_Cfc_Gera_Produto_Fiscal` e `TG_UPT_Produtos_Concat_EFD` → **`Produtos_Cod_Concat_EFD`**
  (código concatenado fiscal usado pelas funções do Estudo 15).
- `TG_UPT_INS_ProdutosCodBarra`, `Tg_Produtos_Gera_Concat_6_Dig`, `Tg_Produtos_Inventario_Del`,
  `TG_UPT_Produtos_Concat_EFD`.

> **Preços de produto** ficam em `Produtos_Precos`/`Ret_Precos` (mantidas por `TGI_PRODUTOS`) — origem
> natural da tabela de preço (ver Estudo 17).

### 2.4 Auditoria / log

- `Log_Sistema` é destino de **6+ triggers** (maioria `Tg_Liv_*_Param_LV3`).
- `TG_DELINSUPT_Cte_Peca_Log`, `TG_DELINSUPT_Cte_Peca_Gaveta_Log`,
  `TG_DelUpt_Car_Pedido_Log`, `TG_DelUpt_Car_Itens_Pedido_Log`, `TG_DELINSUPT_Car_Itens_Romaneio`.
- Há a tabela `Log` com 12 objetos / 95 388 linhas (Estudo 14).

### 2.5 Faturamento / pedido

- `TG_UPT_Fat_Pedido_NFe`, `TG_Fat_SetFacionista` (`Fat_Pedido` → `Fat_Pedido`), `TG_UPT_RomTransf_FatRet`
  (5.454 chars; liga romaneio↔faturamento), `UPT_FatPedido`, `TG_Fat_Del_Liberar_Romaneio_Carteira`.
- `TG_InsUpdDel_Car_Itens_Pedido_Status` (`Car_Itens_Pedido` → `Car_Pedido`, já visto no Estudo 04),
  `TG_Car_Pedido_Reserva`, `TG_Car_Itens_Pedido_Cancelado_Reserva`.

### 2.6 Comissão / FOL / SPED

- `Tg_Pag_UptObsRecibo_Ins` (`Pag_Baixas`) → **`Notas_Fiscais_Obs_PagtoComissao`**.
- `TG_Del_FOL_DeletaContasaPagar` (`NF_Entradas`) → `FOL_ContasPagar.Status='N'`.
- `Tg_Liv_SaiProd_Param_LV3` / `Tg_Liv_EntProd_Param_LV3` / `Tg_Liv_Mov_Modelo3_Param_LV3` /
  `Tg_Liv_Ordem_ProdFiscal_Param_LV3` → gravam em `Log_Sistema` (parametrização do SPED Livro 3).

## 3. Triggers desabilitados (10)

`TG_INSDEL_Car_Itens_Pedido_InfoEntregaItemPedido`, `INS_CTE_Peca_Retalho`, `TG_INSUPT_Fat_Consiste`,
`Tg_Liv_EntProd_Ind_Ins`, `Tg_Liv_EntProd_Ind_Upd`, `Tg_Liv_EntProdRemInd_Del`,
`Tg_Liv_EntProdRemInd_Ins`, `Tg_Liv_SaiProd_Ind_Ins`, `Tg_Liv_SaiProd_Ind_Upd`,
`Tg_Liv_SaiProdRetInd_Del`. (Vários são dos módulos vazios + SPED "Ind" desativado.)

## 4. Impacto na nova API (read-only)

1. **A API só lê → não dispara triggers.** Mas deve tratar como **materializados** os campos que as
   triggers derivam (`Notas_Fiscais_Rec`, `Produtos_Precos`, `Produtos_Cod_Concat_EFD`, logs).
2. **Fechamento mensal:** não assumir períodos fechados — as tabelas estão vazias. Se no futuro a API
   expuser status de fechamento, ler `*_Fechamento_Mensal`; a lista de campos liberados no mês fechado
   está em `Rec_Fechamento_Campos_Alterados` (67).
3. **Nada a portar:** não replicar triggers. No máximo documentar as derivações que interessam à leitura.
4. **Preço/comercial:** origem é `car_tabela_preco`/`Produtos_Precos`/`Ret_Precos` (mantidas por
   triggers de `Produtos`) — aprofundar no Estudo 17.

## 5. Contagens de apoio

- 672 triggers · 285 tabelas · 10 desabilitados · 180 `NOT FOR REPLICATION`.
- Eventos: INSERT 279 · UPDATE 319 · DELETE 307 · `INSTEAD OF` 1.
- Fechamento: 27 tabelas `%Fechamento%`, todas **0 linhas** exceto
  `Lv3_SdoEst_Fechamento` (4 807) e `Lv3EstoqueFechamentoEntregue` (3 512).
  `Rec_Fechamento_Campos_Alterados` = 67 linhas.
- Maior trigger: `TGI_PRODUTOS` (~23 972 chars); `Tg_Liv_EntProd_InsFacionista` 9 517.
