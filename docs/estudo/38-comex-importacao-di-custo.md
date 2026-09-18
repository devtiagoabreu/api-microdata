# Estudo 38 — COMEX/Importação (fluxo transversal: DI, custo de importação, fiscal)

> **Data:** 18/set/2026
> **Escopo:** Levantamento do fluxo de importação na DGB — como uma Declaração de Importação (DI) se conecta ao pedido de compra, ao livro fiscal e ao custo do produto importado.
> **Restrições:** apenas leitura; sem objetos novos em produção.

---

## 1. O que é "COMEX" na DGB?

Não existe um módulo chamado "COMEX" no ERP Microdata. O fluxo de importação transita por **múltiplos módulos**:

```
 Cotação ──► Pedido ──► Embarque ──► Aviso ──► Recebimento ──► FISCAL
 (Cmt)      (Cmt)      (Cmt)        (Ret)     (Ret/Cmt)       (Liv)
   │           │          │            │            │           │
   └──► DI ◄───┴──────────┴────────────┴────────────┴───────────┘
         │        Fat_XML_DI / Fat_Itens_Pedido_DI / Liv_EntProd_DI
         └──► CUSTO DE IMPORTAÇÃO
              SP_CMT_CustoImportacaoPainel_Aviso / CMT_ImpostoImportItem_Aviso
```

| Módulo | Prefixo | Papel |
|--------|---------|-------|
| **SIMCompras** | `Cmt_*` | Pedido de compra ao fornecedor estrangeiro |
| **SIMRet** | `Ret_Aviso_*` | Aviso de recebimento (NF do fornecedor) |
| **Siscomex/XML** | `Fat_XML_DI*` | Parse do XML da DI (Siscomex) |
| **Livro Fiscal** | `Liv_EntProd_DI*` | Registro da DI no livro de entradas |
| **Custo Importação** | `CMT_ImpostoImport*`, `SP_CMT_CustoImportacao*` | Cálculo do custo com impostos/encargos |
| **SIMQualidade** | `SIC_*` | Inspeção de recebimento (vazio/desativado) |

---

## 2. Superfície levantada

### 2.1 Pedidos de compra (SIMCompras — detalhe no Estudo 39)

| Tabela | Registros | Observação |
|--------|-----------|------------|
| `Cmt_Pedido` | 228 | 227 emp 13 + 1 emp 01; todos Tipo 01 (TECIDO); moeda `02` (dólar) em 223 deles; Σ Vr_Pedido ≈ R$ 11,5 mi |
| `Cmt_Pedido_Itens` | 2.171 | 228 pedidos, 2 empresas |
| `Cmt_Pedido_Itens_Entrega` | 2.172 | 228 pedidos; ID_Ent 1 em 2.169; máx 3 |
| `Cmt_Pedido_Itens_Obs` | 644 | Observações por item |
| `Cmt_Pedido_Obs` | 3 | |
| `Cmt_Tipo_Pedido` | 2 | 01=TECIDO, 02=FIO — ambos `Importacao='S'` |
| `Cmt_Parametros` | 1 | `Sistema_Parametros='SIMCompras Têxtil'`; `Usar_Aviso_Pedido='S'`; `Integra_Pagar='S'` |
| `Cmt_ParamEmp` | 5 | Emp 13 ativa: `Ult_Pedido='000276'`, `CarregaUltPrecoProdPedAnt='S'`, `EstoqueEntradaCompras='R'` |
| `CMT_LocalDesembaraco` | 2 | 1=ITAJAI (Marítimo), 2=NAVEGANTES (Marítimo) |
| `CMT_Condicoes_Pagto` | 1 | Emp 4, condição `0G` |
| `CMT_SaldosEmAberto` | 108 | Saldo por aviso/pedido/item — `QtdePedido`, `QtdeAviso`, `QtdeAcerto`, `QtdeEstoque`, `SaldoEmAberto` |
| `Cmt_Cotacao*` | ~16 | Cotação (2), itens (4), entregas (6), obs, produtos |
| `Cmt_Necessidade*` | ~7 | Necessidade (2), itens, entregas, obs |
| `CMT_Requisicao*` | 3 | Requisição (1), itens, CCusto |

**Marcas de importação no pedido:**
- `Cmt_Pedido.Codigo_Moeda='02'` = dólar (transformada em R$ pela `Data_Cambio`/`Data_Data_Atualizacao`)
- `Cmt_Pedido.IdLocalDesembaraco` → `CMT_LocalDesembaraco`
- `Cmt_Pedido.Tipo='01'` (TECIDO) / `'02'` (FIO) — ambos `Importacao='S'` em `Cmt_Tipo_Pedido`
- `Cmt_Pedido.Data_Embarque` / `Data_Desembarque` / `Data_Entrega` / `Data_Producao`

---

### 2.2 Aviso de recebimento (SIMRet — detalhe no Estudo 37)

| Tabela | Registros | Observação |
|--------|-----------|------------|
| `Ret_Aviso_Recebimento` | 218 | 10 fornecedores, 214 NFs, moeda 02 (dólar), `Processo` T2xx, fornecedor 00146 = P2B TRADING MANAGEMENT INC |
| `Ret_Aviso_ItensRecebimento` | 2.083 | 17 produtos, ΣQtde ≈ 17,5 mi metros, ΣVr ≈ R$ 11,1 mi |
| `Ret_Aviso_Itens_Pedido_Atend` | 2.083 | Vínculo aviso ↔ pedido de compra (217 pedidos 1:1) |

---

### 2.3 DI — Declaração de Importação (Siscomex)

**Estrutura hierárquica do XML da DI no banco:**

```
Fat_XML_DI
├── Fat_XML_DI_Adicao
│   ├── Fat_XML_DI_detalheMercadoria (itens/tecnica de cada adição)
│   └── Fat_XML_DI_nomenclaturaValorAduaneiro (atributos NCM)
├── Fat_XML_DI_pagamentoTributos
├── Fat_XML_DI_embalagem
├── Fat_XML_DI_icms
├── Fat_XML_DI_documentoInstrucaoDespacho
└── (controle) Fat_XML_DI_Campos_Inexistentes / _DePara_Tabela_XML / _Tratamento_Tag
```

| Tabela | Registros | Observação |
|--------|-----------|------------|
| `Fat_XML_DI` | 1 | DI nº `2420968319`, empresa 4, registro 26/09/2024 |
| `Fat_XML_DI_Adicao` | 1 | NCM 6001.92.00, II 26%, PIS 2,1%, COFINS 10,65%, FOB $47.957, método valor 01 |
| `Fat_XML_DI_detalheMercadoria` | 15 | 15 tecidos (veludo "SILVER"), empresa 01, ~71 mil metros, $0,54/m |
| `Fat_XML_DI_pagamentoTributos` | 4 | II R$ 79.613,04 · PIS R$ 6.430,28 · COFINS R$ 32.610,73 · Siscomex R$ 154,23 (banco 001, débito) |
| `Fat_XML_DI_embalagem` | 1 | código 44 (ROLO), 1.443 volumes |
| `Fat_XML_DI_icms` | 1 | Exoneração do ICMS (SC), valor 0 |
| `Fat_XML_DI_documentoInstrucaoDespacho` | 3 | Conhecimento de Carga, Fatura Comercial, Romaneio |
| `Fat_XML_DI_nomenclaturaValorAduaneiro` | 2 | Subitem NCM (atributos AA/AB) |
| `Fat_XML_DI_Campos_Inexistentes` | 9 | Tags do XML sem coluna alvo (CIDE, redução II, multa) |
| `Fat_XML_DI_DePara_Tabela_XML` | 83 | Mapeamento `Tabela`/`Coluna_Tabela` ↔ `Coluna_XML` (+ `Casas_Decimais`) |
| `Fat_XML_DI_Tratamento_Tag` | 2 | Tags com tratamento especial: `destaqueNcm`, `armazem` |

**Dados-chave da DI única (2024):**
- Importador: **DGB COMERCIO IMPORTACAO E EXPORTACAO LTDA** (CNPJ 27.616.615/0001-01, Itajaí/SC)
- Fornecedor/exportador: **P2B TRADING MANAGEMENT INC** (Tortola/Ilhas Virgens Britânicas)
- Fabricante: ZHEJIANG HAOYUE TEXTILE TECHNOLOGY CO.,LTD (Tongxiang, Zhejiang — China)
- Via: MARÍTIMA (navio MSC MIA); embarque 27/06/2024 (Shanghai) → chegada 03/09/2024 → desembaraço 26/09/2024
- Recinto aduaneiro: PORTONAVE S/A (Itajaí); container TCNU1893433 (40HQ)
- Valores: FOB $47.957,23 · Frete collect $7.900,00 · Seguro $84,75 · **CIF R$ 306.204,00** · taxa R$ 5,4736/US$
- Incoterm FOB; moeda 220 (DÓLAR DOS EUA)

**Proc de cálculo dos impostos da mercadoria (`SP_Fat_Calcula_Impostos_DI`, criada 28/05/2021):**
```sql
UPDATE m SET
  BC_IImp   = m.CIFTotal,
  Vr_IImp   = CIFTotal * a.iiAliquotaAdValorem/100,
  BC_COFINS = CIFTotal, Vr_COFINS = CIFTotal * a.cofinsAliquotaAdValorem/100,
  BC_PIS    = CIFTotal, Vr_PIS    = CIFTotal * a.pisPasepAliquotaAdValorem/100
FROM Fat_XML_DI d
  JOIN Fat_XML_DI_Adicao a ON a.idDI = d.id AND a.idEmpresa = d.idEmpresa
  JOIN Fat_XML_DI_detalheMercadoria m ON m.idDIAdicao = a.id AND m.idEmpresa = a.idEmpresa
WHERE d.id = @IdDI AND d.idEmpresa = @idEmpresa
```

---

### 2.4 Vínculo DI ↔ pedido de compra

| Tabela | Registros | Observação |
|--------|-----------|------------|
| `Fat_Itens_Pedido_DI` | 2.473 | 254 pedidos, 253 DI docs, empresa 13, 2018–2026 |
| `Fat_Itens_Pedido_DI_Adic` | 2.473 | Fabricante + seq adição por item (chave `Id_Adic`, `SeqAdicao`) |

**Colunas-chave de `Fat_Itens_Pedido_DI`:**

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `Empresa` | char | Sempre '13' neste dataset |
| `Pedido` | char(6) | Nº pedido de compra |
| `Item` | int | Item do pedido |
| `Id_DI` | int | enum 1/2/3 (1 na maioria; não é FK para `Fat_XML_DI.id`) |
| `Documento` | char | Nº da DI no formato `AA/NNNNNNN-DV` (ex. `18/1316478-0`) |
| `Data` | smalldatetime | Data do registro |
| `Local_Des` / `UF_Des` / `Data_Des` | | Desembaraço (ITAJAI/NAVEGANTES, SC) |
| `Exportador` | char | Nome do exportador |
| `Vr_PIS` / `Vr_COFINS` | decimal | Impostos por item de pedido |
| `Vlr_AFRMM` | decimal | AFRMM |
| `Tipo_Dcto_Importacao` | char | '0' (padrão); `Num_DrawBack` quase sempre NULL |
| `ID_Fat_ViaTransporte` | int | 1 = marítimo |
| `tpIntermedio` | int | 1 |
| `CNPJ_Adq_Enc` | varchar | CNPJ da adquirente 27.616.615/0001-01 |

**Série histórica (2018–2026):** 44 · 155 · 158 · 311 · 273 · 429 · 440 · 412 · 251 = **2.473 itens**;
Σ PIS ≈ R$ 15,7 mi · Σ COFINS ≈ R$ 77,0 mi · Σ AFRMM ≈ R$ 8,08 mi.

**Consistências:** `Fat_Consiste_DI` e `Fat_Itens_Consiste_DI` — **vazias**.

---

### 2.5 Livro fiscal de entradas com DI

| Tabela | Registros | Observação |
|--------|-----------|------------|
| `Liv_EntProd_DI` | 2.427 | 249 DI docs, 24 produtos, empresa 13 |
| `Liv_EntProd_DI_Adic` | 2.427 | Fabricante + `SeqAdicao` + `Vr_Desconto` por incremento de produto |
| `TPConflito_Liv_EntProd_DI` | 0 | Estrutura idêntica a `Liv_EntProd_DI` (controle de conflito) |

**Colunas alvo:** `Empresa, Documento, Tipo_Fornec, Fornecedor, Serie, NatOp, Seq, EmpProd, Produto, Incremento_Produto, Cod_Liv_EntProd_DI, Tipo_Dcto_Importacao, Num_DI, Num_DrawBack, Vr_PIS, Vr_COFINS, DT_PAG_PIS, DT_PAG_COFINS, LOC_EXE_SERV`.
- Liga-se à `Liv_Entradas` pela chave `Empresa/Documento/Tipo_Fornec/Fornecedor/Serie/NatOp/Seq/EmpProd/Produto/Incremento_Produto` (NatOp `3.102` = importação).
- Os valores `Vr_PIS`/`Vr_COFINS` batem com `Fat_Itens_Pedido_DI` para a mesma DI (mesma origem de digitação).
- Σ PIS ≈ R$ 15,5 mi · Σ COFINS ≈ R$ 74,0 mi (empresa 13).

---

## 3. Custo de importação

### 3.1 Regras por aviso (`CMT_ImpostoImportItem_Aviso`)

| Tabela | Registros | Observação |
|--------|-----------|------------|
| `CMT_ImpostoImportItem_Aviso` | 225 | 224 avisos reais (emp 13) + 1 fantasma (`Empresa='  '`), 2 grupos fiscais |

Colunas: `Empresa, Aviso, Grupo_Fiscal, PercImportacao, PercICMS, PercIPI, PercPIS, PercCofins, ImportacaoCompoeBaseCusto, ICMSCompoeBaseCusto, IPICompoeBaseCusto, PISCompoeBaseCusto, CofinsCompoeBaseCusto`.

- Os **percentuais** de imposto estão **vazios** (`NULL`) no dataset atual; apenas as flags `*CompoeBaseCusto='S'` estão preenchidas (impostos entram na base de custo).
- O vínculo usa **grupo fiscal** do item de aviso (`Ret_Aviso_ItensRecebimento.Grupo_Fiscal`).

### 3.2 Painel de custo de importação (procs)

| Proc | Tamanho | Papel |
|------|---------|-------|
| `SP_CMT_CustoImportacaoPainel` | 16,5 KB | Custo de importação rateado por **pedido** (criada 14/06/2017) |
| `SP_CMT_CustoImportacaoPainel_Aviso` | 25,8 KB | Rateio por **aviso** (criada 06/07/2018; atualizada 20/01/2025) |
| `SP_CMT_CustoImportacaoPainel_AvisoAFRMM` | 24,1 KB | Idem + AFRMM/ATAERO (02/2026) |
| `SP_CMT_ValorizacaoEstoque` | 30,7 KB | Valorização de estoque com custo de importação |
| `SP_CMT_FechamentoCusto` | 3,9 KB | Fechamento do custo |
| `SP_CMT_CustoMercadoriaVendida` | 52,3 KB | CMV (custo da mercadoria vendida) — já visto no Estudo 36 |

**Mecânica do rateio (dentro do `_AvisoAFRMM`/`_Aviso`):**
```
1. Monta #Tmp_CustoImportPedido (idêntico a Model_CMT_CustoImportPedido):
   uma linha por (Pedido, ItemPedido, Aviso, ItemAviso, Codigo_Concatenado)
2. FatorRateio = Vr_TotalMoeda / ΣVr_TotalMoeda do aviso   (rateio por VALOR)
   FatorRateio_Peso = Peso / ΣPeso do aviso                (rateio por PESO, se RateioCustoImpPeso)
3. Imposto de importação:
   Vr = base * IIA.PercImportacao / 100
   seguido de PIS (Porc_Pis), COFINS (Porc_Cofins), ICMS, IPI,
   AFRMM/ATAERO e despesas (frete/seguro/despachante) cada qual com sua base
4. Cada linha expõe: Valor, IncideICMS, CompoeCalculo (do CMT_ImpostoImportItem_Aviso)
```

### 3.3 Despesas financeiras de importação

| Tabela | Registros | Observação |
|--------|-----------|------------|
| `CMT_PedidoCustoImport` | 0 | Vazia — guardaria `IDCustoFinanceiro`, `EmpresaPagar`, `Fornecedor`, `Valor` por pedido |
| `Model_CMT_CustoImportPedido` | 0 | Tabela modelo (template da `#Tmp`) |
| `Model_CMT_PedidoDespesaImport` | 0 | Modelo de despesas por item (IncideICMS, CompoeCalculo, ValorNFE) |
| `SP_CMT_PreencheVr_UnitarioEfetivo` | 7,6 KB | Ajusta valor unitário efetivo dos itens do pedido |

**Observação:** `Model_CMT_*` são os **templates** que a tela espelha em `#Tmp` dentro do EXE Delphi — não trabalhar com elas como fonte.

---

## 4. Qualidade / Inspeção de recebimento (SIC)

- `SIC_*`: 79 tabelas; **78 vazias**; só `SIC_Parametros` (1) tem dados (`Usar_Aviso_Rec_Lotes='N'`, `Ult_Lote_Interno=0`) → módulo **desativado**.
- Views restantes (lote de inspeção, fornecedores IQ/IS/IQF, transportadoras, BIC/RQR/BIT) são de uma época em que o módulo rodava.
- Procs: `SP_SIC_Indice_Atraso_Fornecedor/Transportadora`, `SP_SIC_Indice_Transporte`, `SP_SIC_Distribui_Assinatura`.

---

## 5. Procs envolvidas no fluxo

| Proc | Papel |
|------|-------|
| `SP_Fat_Calcula_Impostos_DI` | Recalcula II/PIS/COFINS das mercadorias da DI (acima) |
| `SP_Fat_Calcula_Impostos_DI_Fornec` | Idem por fornecedor |
| `SP_Fat_Pedido_Atualiza_Dados_DI` | Grava dados da DI no pedido (valor aduaneiro, II, PIS, COFINS, AFRMM, Siscomex, frete, despesas; CST 70 zera PIS/COFINS; diferimento) |
| `SP_Fat_Deleta_Fat_XML_DI` | Remove DI lançada |
| `SP_CMT_CustoImportacaoPainel[_Aviso][_AvisoAFRMM]` | Painel de custo de importação |
| `SP_Liv_Calc_Dif_XML_Liv` | Divergência XML DI × livros |
| `SP_Cmt_ItensAberto_FornProd` | Itens em aberto por fornecedor/produto |
| `SP_CMT_Calcula_SaldoEmAberto` | Alimenta `CMT_SaldosEmAberto` |
| `SP_CMT_AtualizaCusto_CaixaFios` | Custo caixa de fios (emp 13 fiação) |
| `Ret_EnviaPedidoCompra` / `Ret_EnviaUmPedidoCompra` | Integração SIMRet ↔ SIMCompras (empresa local ↔ lojas, via `Ret_PedCompra`) |

---

## 6. Views de apoio

- `VW_CMT_PedidoCompra_Itens`, `VW_CMT_Pedido_Itens_Entrega`, `VW_CMT_RelCompras`, `VW_CMT_RelConsumo`, `VW_CMT_Status_Item_Cotacao`
- `vw_Cmt_Necessidade_Produto_Aberto`, `vw_Cmt_Necess_itens_entrega_Aberto`, `vw_cmt_Pedido_Itens_Entrega_Aberto`, `vw_Cmt_Requisicao_baixa`, `Vw_Cmt_Saldo_Pedidos`
- `Vw_SIC_*` (lote inspeção, fornecedores, transportadoras) — inativas

---

## 7. Configurações e parâmetros resumo

| Objeto | Valor |
|--------|-------|
| `Cmt_Parametros` | SIMCompras Têxtil · `Usar_Aviso_Pedido=S` · `Integra_Pagar=S` · `Usar_Aprovacao_Pedido=N` · tolerâncias aviso 0 |
| `Cmt_ParamEmp` | emp 13: `Ult_Pedido=000276`, `Ult_Cotacao=000002`, `Ult_Necess=6`, `EstoqueEntradaCompras=R` |
| `Cmt_Tipo_Pedido` | 01=TECIDO (Usa_SCD, Importacao=S) · 02=FIO (Usar_Cor, Importacao=S) |
| `CMT_LocalDesembaraco` | 1=ITAJAI, 2=NAVEGANTES (m) |
| `CMT_Condicoes_Pagto` | emp 4 → condição `0G` |
| `SIC_Parametros` | SIMSIC 1.0 · `Usar_Aviso_Rec_Lotes=N` (inativo) |
| `Cmt_Tipo_Pedido` | `FiosFacionista` e `SCD_*` (campos p/ grade tecido) |

---

## 8. Lacunas e observações para a nova API

1. **Não usar** `Model_CMT_*`, `CMT_PedidoCustoImport`, `SIC_*`, `Fat_Consiste_DI`/`Fat_Itens_Consiste_DI` como fonte (vazias ou templates do EXE).
2. **Custo de importação não é persistido** — é sempre recalculado pelo painel a partir da DI/aviso + `CMT_ImpostoImportItem_Aviso`. A nova API deve **reproduzir o rateio** (valor ou peso) da proc `SP_CMT_CustoImportacaoPainel_AvisoAFRMM`.
3. **DI atual (Siscomex):** `Fat_XML_DI*` só tem 1 registro (2024, empresa 4); o histórico 2018–2026 vive em `Fat_Itens_Pedido_DI` (chave da DI = `Documento` + `Empresa`/`Pedido`/`Item`). As duas fontes **não se relacionam** por chave.
4. **Impostos da mercadoria** (`Fat_XML_DI_detalheMercadoria`, campos `Vr_IImp/Vr_PIS/Vr_COFINS/Vr_ICMS/Vr_IPI/BC_*`) são preenchidos por `SP_Fat_Calcula_Impostos_DI`; PIS/COFINS também são **zerados** quando CST 70 (sem direito a crédito) ou regime ≠ Lucro Real — regra de 25/06/2026 (ver `SP_Fat_Pedido_Atualiza_Dados_DI`).
5. **AFRMM** aparece em 3 lugares: DI XML (informada), `Fat_Itens_Pedido_DI.Vlr_AFRMM` e no painel de custo — conferir qual é a fonte canônica por período.
6. Moeda: pedido/aviso em **dólar** (`Codigo_Moeda='02'`); câmbio em `Cmt_Pedido.Data_Cambio`; conversão embutida no custo.
7. **NC e não-relacionamento:** `Cmt_Pedido.Pedido` ≈ `Fat_Itens_Pedido_DI.Pedido` (pedidos 228 × 254) — nem todo pedido tem DI no XML; e `Ret_Aviso_Itens_Pedido_Atend` liga aviso→pedido.
8. Empresa fiscal de importação: pedidos/DI/livros em **emp 13** (NOTA: `Ret_Aviso` também emp 13; DI XML 2024 usa `idEmpresa=4` — conferir mapeamento empresa fiscal × cadastro).

---

## 9. Próximos passos

- **Estudo 39 — SIMCompras (módulo `Cmt_*` completo)**: cotação, necessidade, requisição, aprovação, pedido (digitado e aprovado), `SP_Cmt_GeraPedido` e fluxo de integração SIMRet (`Ret_EnviaPedidoCompra`).
- Entender como computar **custo de importação rateado** em SQL da nova API (espelhar `SP_CMT_CustoImportacaoPainel_AvisoAFRMM`).
- Confirmar campo de **câmbio** usado hoje (tabela de moedas `Ret_Moedas`/`Ret_Moedas_Diario` vs `Cmt_Pedido.Data_Cambio`).

---

_Fontes: pesquisa direta em `sys.tables`/`INFORMATION_SCHEMA` + amostras das tabelas citadas; definições salvas em `defs/SP_Fat_Calcula_Impostos_DI.sql`, `defs/SP_Fat_Pedido_Atualiza_Dados_DI.sql`, `defs/SP_CMT_CustoImportacaoPainel*.sql`._