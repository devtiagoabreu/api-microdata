# Estudo 20 — Importação/COMEX, previsão de compra e SIM Carteira

Levantado com **SELECTs somente leitura** (catálogo, colunas, definições, contagens). Sem dados reais.

O pedido cobriu três frentes que, no ERP, formam um só fluxo: **importação/COMEX**, a
**previsão de compra/recebimento** (`Ret_Aviso_*`) e a **carteira do SIM Carteira** com sua
conciliação com o estoque. Segue o mapa.

## 1. Importação / COMEX

Não existe um módulo "Comex" isolado: a importação é tratada como **entrada de mercadoria com
declaração de importação (DI)** atrelada ao pedido de compra e ao aviso de recebimento.

### 1.1 `Ret_Aviso_Recebimento` — aviso de recebimento (218)

Cabeçalho do **aviso de recebimento** da mercadoria comprada/importada. É a **"previsão/orçamento
de chegada"** que a empresa acompanha contra o pedido.

Colunas (36): `Empresa`, `Aviso`, `Tipo_Fornecedor`, `Fornecedor`, `Nr_NFE`, `Serie`, `Data_Receb`,
`Data_Hora_Receb`, `Observação`, `Dat_Recebimento`, `Vr_Acres`, `Encargos_Financeiros`, `Tipo`,
`Operador`, `Vr_Desconto`, `porc_Desconto`, `Codigo_Moeda`, `Data_Cambio`,
`Data_Cambio_Atualizacao`, `Revisado`, **`MoedaVrAduaneiro`**, **`DataRegistroDI`**, `Path_XML`,
`Arquivo_XML`, `Historico`, **`IdLocalDesembaraco`**, **`Processo`**, `Chave_Acesso`, **`VrAFRMM`**,
**`VrATAERO`**, `Vr_Frete`, `Status`, `Empresa_Fat`, `Facionista`, `StatusColeta`,
`Data_Lancamento`.

Situação atual: 218 avisos, todos `Tipo='01'`, `Revisado='N'`, `Tipo_Fornecedor='0'`, `Status`
predominantemente `NULL` (2 com `'A'`); fornecedor único (o importador), `Processo` no formato
`T<n>`, `MoedaVrAduaneiro` `'01'/'02'`, `DataRegistroDI` presente. Os campos aduaneiros
**`VrAFRMM`/`VrATAERO`** estão `NULL` nos registros atuais (a taxação marítima foi migrada para os
itens/DI — ver 1.3).

### 1.2 `Ret_Aviso_ItensRecebimento` — itens do aviso (2 083)

45 colunas. Chave `Empresa+Aviso+Item_Aviso`. Identificação: `Emp_Prod`/`Produto`, `Cor`, `Grade`,
`Grade_Tam`, `Desenho`, `Variante`, `Situacao`, `Categoria`, `Categoria`; quantidades `Qtde`,
`Metros`, `Peso`, `Peso_Bruto`, `QMP`, `Qtde_Rolos`; valores `Vr_Unitario`, `Vr_Total`,
`Vr_Unitario2`, **`Vr_Moeda_Estrangeira`**, **`Vr_Unitario_Compra`**, `Qtde_Compra`,
`Vr_UnitPedido`; tributos `Porc_IPI`, `Porc_ICMS`, `ICMS_Subst`, `Porc_PIS`, `Porc_COFINS`,
`Aliq_Reducao`, `Porc_Encargos`, `Encargos_Financeiros`, `Vr_AcresDesc`, `Vr_Desconto`,
`porc_Desconto`; vínculos `ID_EstoquePCP`, `Fk_PCP_Acondicionamento`, `produtoReferenciado`,
`Codigo_Concatenado`, `Embalagem`, `Vr_Frete`, `StatusColeta`.

Os pares **`...Compra`/`Vr_Moeda_Estrangeira`/`Vr_Unitario_Compra`** mostram que o item é
registrado em **duas moedas**: a compra (moeda estrangeira) e a nacional (com encargos/câmbio).

### 1.3 Declaração de Importação (DI)

Duas famílias, uma **por pedido** e outra **por entrada**:

- **Por pedido** — `Fat_Itens_Pedido_DI` (2 473) + `Fat_Itens_Pedido_DI_Adic` (2 473):
  `Empresa`, `Pedido`, `Item`, `Id_DI`, `Documento`, `Data`, `Local_Des`, `UF_Des`, `Data_Des`,
  `Exportador`, `Vr_PIS`, `Vr_COFINS`, `Tipo_Dcto_Importacao`, `Num_DrawBack`,
  `ID_Fat_ViaTransporte`, `Vlr_AFRMM`, `tpIntermedio`, `CNPJ_Adq_Enc`, `UFTerceiro`.
- **Por entrada (livro fiscal)** — `Liv_EntProd_DI` (2 427) + `Liv_EntProd_DI_Adic` (2 427):
  `Empresa`, `Documento`, `Tipo_Fornec`, `Fornecedor`, `Serie`, `NatOp`, `Seq`, `EmpProd`,
  `Produto`, `Incremento_Produto`, `Cod_Liv_EntProd_DI`, `Tipo_Dcto_Importacao`, `Num_DI`,
  `Num_DrawBack`, `Vr_PIS`, `Vr_COFINS`, `DT_PAG_PIS`, `DT_PAG_COFINS`, `LOC_EXE_SERV`.

Campos presentes: **DI, Drawback, AFRMM, intermediário, adquirente/encomendante (CNPJ), local de
desembaraço, UF de desembaraço e exportador** — ou seja, o ERP suporta o fluxo aduaneiro completo
(importação direta, por encomenda e drawback).

### 1.4 Procedures de apoio

- Cálculo de tributos: `SP_Fat_Calcula_Impostos_DI`, `SP_Fat_Calcula_Impostos_DI_Fornec`.
- Atualização/limpeza de DI no pedido: `SP_Fat_Pedido_Atualiza_Dados_DI`, `SP_Fat_Deleta_Fat_XML_DI`.
- Itens de DI: `SP_DItens_Comercio`, `SP_DItens_Ret`, `SP_Fat_Troca_DItens_Ret`, `SP_Recau_DItens_Ret`.
- **Custo de importação**: `SP_CMT_CustoImportacaoPainel`, `..._Aviso`, `..._AvisoAFRMM`
  (painel de custo que rateia frete/encargos/aduanas no item).
- Entrada fiscal do aviso: `Ret_EnviaPedidoCompra`, `Ret_EnviaUmPedidoCompra`,
  `sp_Ret_ImportacaoNF_ValidaFiltroProd`, `Ret_RelBlocoEstoquePedido`.

## 2. Previsão de compra × atendimento do pedido

A **conciliação** entre o que foi comprado/previsto (aviso) e o que o pedido consome é a tabela de
ligação:

### 2.1 `Ret_Aviso_Itens_Pedido_Atend` (2 083)

Chave lógica `Empresa+Aviso+Item_Aviso+Pedido+Item_Pedido`. Colunas (10): `Empresa`, `Aviso`,
`Item_Aviso`, `Pedido`, `Item_Pedido`, `ID_Ent`, `Qtde_Atend`, `Qtde_Acerto`, `Qtde_Atend_Compra`,
`Qtde_Acerto_Compra`.

Liga **cada item de aviso** a **um item de pedido** (`Pedido`/`Item_Pedido`) e registra quanto
daquele aviso atende (`Qtde_Atend`) e quanto foi ajustado (`Qtde_Acerto`), em duas moedas
(`..._Compra`). `ID_Ent` aponta para a entidade/estabelecimento de entrega.

### 2.2 Views `vw_Ret_Aviso_Itens_Pedido_Atend(_Ant)`

Calculam o saldo do aviso por item de pedido:

```
Saldo        = Qtde        − Qtde_Anterior           − (Qtde_Atend        + Qtde_Acerto)
Saldo_Compra = Qtde_Compra − Qtde_Anterior_Comnpra   − (Qtde_Atend_Compra + Qtde_Acerto_Compra)
```

com `Qtde_Anterior` = soma de `Qtde_Atend` dos **avisos anteriores** (`N.Aviso < A.Aviso`) para o
mesmo `Empresa+Pedido+Item_Pedido+ID_Ent`. Ou seja: **quanto do item do pedido ainda falta chegar**
do estoque comprado (previsão), par a par. Saldos negativos são truncados em 0
(`CASE WHEN Saldo < 0 THEN 0`). A `_Ant` é a base; a sem sufixo só renomeia colunas.

## 3. SIM Carteira × estoque físico

### 3.1 Saldo da carteira — `Vw_Saldo_Pedido_Carteira_Qlik` (123)

View de BI (Qlik) com o saldo dos pedidos em aberto:

`Empresa`, `Pedido`, `Cliente`, `Vendedor`, `Data_Pedido`, `QMP`, `Codigo_Aux`,
`Produto`/`Situacao`/`Cor`/`Desenho`/`Variante`/`Categoria`, `Linha`/`Descr_Linha`,
`Cond_Pagto`/`Cond_Pagto_Extenso`, `Data_Entrega`, `Qtde_Ped`, `Qtde_Rom`, `Qtde_Acerto`,
`Saldo`, `Vr_Total`, `Status`/`Status_Pedido`, `Tipo_Pedido`/`Descr_Tipo_Pedido`.

Regra (Estudo 13): **`Saldo = Qtde_Ped − Qtde_Rom − Qtde_Acerto`** sobre `Car_Pedido` ⋈
`Car_Itens_Pedido`. É o saldo da carteira que o SIM Carteira/estoque precisa cobrir.

### 3.2 Endereçamento estoque→pedido — `uspEnderecamentoParaAtenderPedidoGeral`

Proc (autoria interna, 2025) que **endereça peças do estoque físico ao pedido**: a partir de
`Vw_Car_Itens_Pedido` (por `Pedido`, `Produto`, `Cor`, com `Qtde_Saldo`), percorre `Cte_Peca`
(excluindo as baixadas em `CTE_Baixa` e rolos de origem `Nro_Rolo_Origem IS NULL`) e acumula
metros por peça (window `SUM(Metros) OVER (ORDER BY RowNum)`) até cobrir a quantidade do item,
devolvendo `Sublote`, gavetas, rolos, nº de peças e total de metros. É a ponte **carteira ↔
estoque de peças** (detalhada no Estudo 02/09/19).

### 3.3 Previsão/entrega do item de carteira

- `Car_Itens_Pedido`: `Data_Entrega`, `DtEntrega`, **`Data_Previsao_Fabril`**, `Qtde_Romaneio`,
  `Qtde_Acerto`, `Data_Acerto`, `Usuario_Acerto`, `estoque_dt`, `estoque_existe`,
  `estoque_item_nu`, `estoque_ped_nu`.
- **`CAR_Itens_Carteira_Data_Previsao_Log`** (5 838) — auditoria de **troca de data de previsão**
  do item da carteira: `ID`, `Empresa`, `Pedido`, `Item`, `Usuario`, `Data_Alteracao`,
  `Data_Anterior`, `Data_Atual`. É o histórico de reprogramações da carteira.
- `VW_CarPedidosRomaneioNF` expõe `Pedido_SimCarteira` / `Data_Pedido_SimCarteira` — distingue
  pedidos originados pelo app.
- `Car_Gestor_Grade` (previsão de grade/fabril por gestor) está **vazia** hoje (0 linhas).
- As views de rótulo "saldo carteira" legadas (`vw_saldocarteira`, `VW_RELSALCARTEIRA`) derivam de
  `CFC_Romaneio`/`Cfc_Itens_Romaneio` (módulo CFC), que está **vazio** (Estudo 14) → retornam 0.
  O saldo válido é o `Vw_Saldo_Pedido_Carteira_Qlik` (123).

## 4. "SIM" (integridade) e "SIM Carteira" (app)

São coisas distintas, ambas com o prefixo "SIM":

- **`SIM_FK_Hint` (346) / `SIM_FK_Columns` (670)** — metadados de **integridade referencial** do
  ERP. `SIM_FK_Hint` descreve bloqueios de exclusão/uso no formato `Existe registro na tabela
  <T>` / `Existe registro na tabela de <...>`, com `Table_Master`/`Status` (principalmente
  `Produtos` e tabelas de produção/preço). `SIM_FK_Columns` mapeia as colunas de junção por
  `Incremento`: `Item`, `Column_Name` (na tabela) ↔ `Column_Master` (no mestre) e
  `Table_Join`/`Column_Join`/`Column_Where`. Serve para montar a checagem "o registro X é usado
  em Y?" antes de permitir alteração/exclusão.
- **SIM Carteira** — é um **app/frente de vendas** da Microdata. No banco aparece como:
  - layouts por cliente em `Car_AnexosNFE_Cliente` (309): `SIMCarteira_Venda`,
    `SIMCarteira_Remessa`, `SIMCarteira_Transf`, `SIMCarteira_Fio`, `SIMCarteira_Fita`,
    `SIMCarteira_Fardo`, `SIMBeneficiamento_Venda`, `SIMTecidos_Urdume` + o par `Layout_*` de cada
    um e `simCarteiraRemessaXML` (XML de remessa assinado por cliente).
  - parâmetros: `Car_Parametros.Usa_Visualizando_Carteira_Novo`, `Cfc_Parametros.Atendimento_SIMCarteira`,
    `Unifica_SIMCon_Carteira`.
  - procedures/triggers que citam SIMCarteira: `SP_Car_Gera_Consiste`, `SP_Car_Analise_Motivo_Reprova_Grupo`,
    `SP_GESTOR_*`, `SP_Carteira_Visualizando`, `TG_InsUpt_Cfc_Vend_Pedido_Unifica`,
    `SP_TntRom_Carteira`, `FNC_Car_VerificaVersaoNFE`/`FNC_Car_VersaoXML`, `SP_Rec_Saldo_CredDevNF`.

## 5. Smartsales / Microdata / pedidos web

- **Smartsales**: não há objeto com esse nome no banco. O que existe é a frente **"Smart" da
  Microdata** em `sp_Fat_GravaProd_Smart` (cabeçalho **"TCS31 - SmartFinances"**, 2016), usada para
  gravar `Produtos` a partir de `Produtos_Cod_Concat_EFD`. Ou seja, **SmartFinances** é o produto
  Microdata efetivamente integrado; **Smartsales não aparece** (a venda externa chega por
  **pedidos web** — ver abaixo).
- **`pedido_web` (2 048) / `pedido_web_prod` (4 915)** — pedidos originados de fora do ERP
  (e-commerce/coletor), com nomenclatura **legada** (`ped_nu`, `cli_cd`, `cond_pgto_cd`,
  `tab_preco_id`, `emp_cd`, `ped_dt`, `fatura_dt`, `efetivado`, `regra_negocio`, `pedido_id`…) —
  distinta do padrão `Car_*` do ERP. Integração por `SP_Fat_PedidosEcommerce`,
  `SP_Fat_Gera_Consiste_PedidoeCommerce`, `SP_Ws_Int_Atualiza_Status_Pedido` (webservice de status).
- **Integração com a Microdata**: ~20 procs citam "Microdata" (REDF/RPS/PDV/Folhamatic/Prosoft:
  `SP_Liv_Gera_REDF_Cupom_PDV`, `SP_Fat_Gera_RPS`, `SP_Naturezas_Folhamatic`, `SP_Liv_Prosoft_ISS`,
  `SP_Cfc_ImpProd_InsereAtualiza_Dados`…). As pontes de dados ficam em
  `Clientes_SPED_Microdata` (11), `Produtos_SPED_Microdata` (1),
  `Produtos_Fiscal_SPED_Microdata` (1) e nos logs `Log_*_SPED*` — alimentam o SPED da Microdata.
- `Fat_NossoNro_Carteira` (+`_Log`): numeração de "nosso número" da carteira (3 / 22).

## 6. Impacto na API (read-only)

1. **Importação/COMEX**: cabeçalho em `Ret_Aviso_Recebimento`, item em
   `Ret_Aviso_ItensRecebimento`; DI em `Fat_Itens_Pedido_DI(_Adic)` (pedido) e `Liv_EntProd_DI(_Adic)`
   (entrada fiscal). Filtrar por `Empresa+Aviso` / `Empresa+Documento+Seq`. Custo de importação é
   calculado por proc (`SP_CMT_CustoImportacao*`) — **reimplementar em leitura**, não executar.
2. **Previsão × pedido**: usar `vw_Ret_Aviso_Itens_Pedido_Atend` (já entrega `Saldo`/`Saldo_Compra`
   por item de pedido, com avisos anteriores deduzidos). É a resposta pronta para "quanto ainda
   falta chegar do comprado para este pedido".
3. **Saldo de carteira**: `Vw_Saldo_Pedido_Carteira_Qlik` (123) — não usar `vw_saldocarteira`/
   `VW_RELSALCARTEIRA` (CFC vazio). Saldo = `Qtde − Qtde_Rom − Qtde_Acerto`.
4. **Trocas de previsão**: `CAR_Itens_Carteira_Data_Previsao_Log` (5 838) dá o histórico
   usuário/data_anterior/data_atual; `Data_Previsao_Fabril` no item é a previsão corrente.
5. **Carteira × estoque físico**: `uspEnderecamentoParaAtenderPedidoGeral` é o endereçamento de
   `Cte_Peca` ao item do pedido (Estudo 02/19). A nova API deve expor o mesmo resultado por
   `SELECT` (rolos disponíveis = `Cte_Peca` sem `CTE_Baixa`).
6. **SIM Carteira**: layouts/assinatura por cliente ficam em `Car_AnexosNFE_Cliente`
   (`SIMCarteira_*`/`Layout_*`/`simCarteiraRemessaXML`); flags em `Car_/Cfc_Parametros`.
7. **Smartsales**: não existe no banco; **SmartFinances** (`sp_Fat_GravaProd_Smart`) e a
   integração **SPED Microdata** (`*_SPED_Microdata`) é o que há. Pedido externo = `pedido_web(_prod)`,
   com nomenclatura legada — mapear para o modelo `Car_*` antes de expor.
8. **`SIM_FK_Hint`/`SIM_FK_Columns`** são metadados de integridade (checagens "usado em X"):
   úteis só se a API for expor validação — não são dados de negócio.

## 7. Contagens de apoio

- Importação: `Ret_Aviso_Recebimento` 218 · `Ret_Aviso_ItensRecebimento` 2 083 ·
  `Fat_Itens_Pedido_DI` 2 473 · `Fat_Itens_Pedido_DI_Adic` 2 473 · `Liv_EntProd_DI` 2 427 ·
  `Liv_EntProd_DI_Adic` 2 427.
- Conciliação: `Ret_Aviso_Itens_Pedido_Atend` 2 083 · views `vw_Ret_Aviso_Itens_Pedido_Atend(_Ant)`.
- Carteira: `Car_Pedido` 15 799 · `Car_Itens_Pedido` 41 224 · `Vw_Saldo_Pedido_Carteira_Qlik` 123 ·
  `CAR_Itens_Carteira_Data_Previsao_Log` 5 838 · `Car_AnexosNFE_Cliente` 309 ·
  `Car_Gestor_Grade` 0 · `Fat_NossoNro_Carteira` 3 (+Log 22).
- Web/integração: `pedido_web` 2 048 · `pedido_web_prod` 4 915 ·
  `Clientes_SPED_Microdata` 11 · `Produtos_SPED_Microdata` 1 · `Produtos_Fiscal_SPED_Microdata` 1.
- Metadados SIM: `SIM_FK_Hint` 346 · `SIM_FK_Columns` 670.
