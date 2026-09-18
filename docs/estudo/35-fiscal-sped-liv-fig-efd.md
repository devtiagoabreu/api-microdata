# Estudo 35 — Fiscal/SPED (`Liv_*`, `Fig_*`, `EFD_*`, `SIS_Parametros`)

Aprofundamento do **módulo fiscal** do ERP. Consolida e detalha o que apareceu de forma
panorâmica nos [Estudos 08](./08-cadastros-base.md), [10](./10-compras-e-recebimento.md),
[11](./11-procedures-e-views.md), [13](./13-views-dbmicrodata.md),
[15](./15-functions.md), [18](./18-fiscal-liv-efd.md) e [23](./23-financeiro-contabil-custo.md).
Aqui o foco é: **livro fiscal de saídas/entradas** (`Liv_Saidas`/`Liv_Entradas` + satélites),
**tabelas de apoio fiscal**, **motor de regra fiscal** (`Fig_*`), **SPED/EFD**, **importação de
NF-e XML** (`Liv_XML*`), **modelo 3** e **parâmetros** (`SIS_Parametros*`). Levantamento por
`SELECT` somente leitura.

## 1. Síntese

O módulo fiscal tem **232 tabelas `Liv_*`**, **40 `Fig_*`**, **125 `EFD_*`** e **31 `SPED*`**
(≈ **426 objetos**). O núcleo é o **livro fiscal** — uma linha por documento (nota) na
`Liv_Saidas`/`Liv_Entradas` e uma por **item** em `Liv_SaiProd`/`Liv_EntProd` —, tudo derivado do
faturamento (`Fat_*`) e do recebimento (`NF_Entradas`), e alimentado também pela **importação de
XML**.

| Papel | Objeto | Linhas | Estado |
|-------|--------|-------:|--------|
| **Livro de saídas** (cabeçalho) | `Liv_Saidas` | **12 098** | **Em uso** |
| Itens de saída (fiscal, por produto) | `Liv_SaiProd` | 34 043 | Em uso |
| Faturamento da saída (por título/parcela) | `Liv_SaiFat` | 28 959 | Em uso |
| Natureza de operação da saída | `Liv_SaiNatOp` | 12 098 | Em uso |
| Formas de pagamento da saída | `Liv_Sai_FormaPagto` | 12 078 | Em uso |
| Observações da saída | `Liv_SaiObs` | 11 958 | Em uso |
| Informações adicionais por produto | `Liv_SaiProdInfAdic` | 5 222 | Em uso |
| Notas referenciadas (saída) | `Liv_SaiNFRef` | 3 | Em uso |
| **Livro de entradas** (cabeçalho) | `Liv_Entradas` | **1 957** | **Em uso** |
| Itens de entrada | `Liv_EntProd` | 22 522 | Em uso |
| Natureza de operação da entrada | `Liv_EntNatOp` | 1 957 | Em uso |
| Observações da entrada | `Liv_EntObs` | 1 951 | Em uso |
| Transporte/SPED da entrada | `Liv_Ent_Transporte_SPED` | 1 756 | Em uso |
| Itens remessa/industrialização | `Liv_EntProdRemInd` | 6 937 | Em uso |
| DI (declaração de importação) + adições | `Liv_EntProd_DI` / `_DI_Adic` | 2 427 / 2 427 | Em uso |
| Notas referenciadas (entrada) | `Liv_EntNFRef` | 835 | Em uso |
| Formas de pagamento da entrada | `Liv_Ent_FormaPagto` | 434 | Em uso |
| Informações adicionais por produto (entrada) | `Liv_EntProdInfAdic` | 40 | Em uso |
| Natureza de operação (cadastro) | `Liv_Natureza` | 132 | Cadastro |
| Classificação fiscal / NCM | `Liv_Classificacao` | 207 | Cadastro |
| Serviços | `Liv_Servicos` | 129 | Cadastro |
| Gênero do produto (SPED) | `Liv_Genero_Produto` | 97 | Cadastro |
| CEST (SPED) | `Liv_SPED_CEST` | 1 172 | Cadastro |
| **Figura fiscal** | `Fig_FiguraFiscal` | 5 | Cadastro |
| Figura fiscal × CFOP | `Fig_FiguraFiscal_CFOP` | 183 | Cadastro |
| Grupo fiscal (natureza do item) | `Fig_GrupoFiscal` | 13 | Cadastro |
| **Regra fiscal por item** | `Fig_GrupoFiscal_Itens` | **829** | **Em uso** |
| Valores de parâmetros da regra | `Fig_GrpFiscItensParamVlr` | 20 169 | Em uso |
| Comercialização (tipo de operação) | `Fig_Comercializacao` | 43 | Cadastro |
| Comercialização × CFOP | `Fig_Comercializacao_CFOP` | 231 | Cadastro |
| Região fiscal + UF | `Fig_RegiaoFiscal` / `_UF` | 5 / 28 | Cadastro |
| **IBS municipal** (reforma) | `Fig_IBS_Mun` | 32 214 | Em uso (2026+) |
| IBS estadual (reforma) | `Fig_IBS_UF` | 3 229 | Em uso (2026+) |
| Classificação IBS/CBS | `Fig_ClassificacaoIBSCBS` | 152 | Em uso (2026+) |
| Enquadramento IPI | `Fig_Enquadramento_IPI` | 129 | Cadastro |
| Classificação seletivo (IS) | `Fig_ClassificacaoSeletivo` | 28 | Cadastro |
| ST ICMS/IPI/PIS/COFINS/IBS/Seletivo | `Fig_ST_*` | 11/14/32/32/23/6 | Cadastro |
| Motivo de desoneração ICMS | `Fig_MotivoDesoner_ICMS` | 12 | Cadastro |
| **XML de NF-e importado** | `Liv_XML` | 1 690 | Em uso |
| Itens do XML | `Liv_XML_Item` | 20 109 | Em uso |
| Emitente do XML | `Liv_XML_Emit` | 1 690 | Em uso |
| Informações complementares do XML | `Liv_XML_InfCPL` | 1 318 | Em uso |
| Documentos referenciados do XML | `Liv_XML_DocRef` | 817 | Em uso |
| Formas de pagamento do XML | `Liv_XML_FormaPagto` | 167 | Em uso |
| Cobrança do XML | `Liv_XML_Cob` | 66 | Em uso |
| Info adicional por item do XML | `Liv_XML_ItemInfAdProd` | 8 656 | Em uso |
| Modelo 3 (importação/exportação) | `Liv_Mov_Modelo3` | 29 | Pouco uso |
| Parâmetros do sistema | `SIS_Parametros` | 1 521 | **Em uso** |
| Valores de parâmetro por empresa | `SIS_Parametros_Valor` | 7 605 | **Em uso** |
| De-para parâmetro × sistema | `SIS_Parametros_Sistemas` | 2 050 | Em uso |
| Tipos de dado de parâmetro | `SIS_Parametros_Tipo_Dado` | 4 | Cadastro |

> **Não há** um módulo `Est_*` nem uma "tabela de impostos" única: a tributação é **calculada** e
> **gravada linha a linha** em `Liv_SaiProd`/`Liv_EntProd` (ICMS, ICMS-ST, IPI, PIS, COFINS, ISS,
> CSLL, IR, INSS e os novos **IBS/CBS/IS**), e a **regra** que a gera vive no motor `Fig_*`.

## 2. Modelo fiscal

```
Fat_* / NF_Entradas ──► Liv_Saidas / Liv_Entradas            (cabeçalho: 1 linha por documento)
   │                        │
   │                        ├─ Liv_SaiProd / Liv_EntProd     (1 linha por item: tributos + NCM/CFOP)
   │                        ├─ Liv_SaiNatOp / Liv_EntNatOp   (natureza de operação do doc)
   │                        ├─ Liv_SaiFat / Liv_EntFat      (rateio/parcelas do documento)
   │                        ├─ Liv_Sai_FormaPagto / Liv_Ent_FormaPagto
   │                        ├─ Liv_SaiObs / Liv_EntObs       (observações / obs. do fisco)
   │                        ├─ Liv_SaiNFRef / Liv_EntNFRef   (documentos referenciados)
   │                        └─ Liv_EntProd_DI / _DI_Adic     (importação)
   │
   └─► Liv_XML ── Liv_XML_Item ── Liv_XML_*                  (NF-e importada de terceiros)

Motor de regra fiscal (define o tributo de cada item):
   Fig_GrupoFiscal_Itens  (item × grupo × empresa × CFOP × região → alíquotas/CST/CSOSN)
        └─ Fig_GrpFiscItensParamVlr  (valores extras por parâmetro)
   Fig_FiguraFiscal ── Fig_FiguraFiscal_CFOP   (figura: PADRÃO/NAO CONTRIBUINTE/IMPORTACAO/…)
   Fig_Comercializacao ── Fig_Comercializacao_CFOP
   Fig_RegiaoFiscal ── Fig_RegiaoFiscal_UF

SPED/EFD:
   Liv_Layouts_SPED (+DF/PE/ECF/PISCOFINS/G5) · Liv_TabRegistros_SPED (+Fiscal_DF/PE/PISCOFINS)
   EFD_PERIODO/EFD_PROCESSOS · EFD_Reinf_* (R-2000/R-4000/R-9000) · SPED_PC_* (Contribuições)

Parâmetros: SIS_Parametros ── SIS_Parametros_Valor ── SIS_Parametros_Sistemas
```

## 3. Livro fiscal de saídas

### 3.1 `Liv_Saidas` (12 098) — cabeçalho do documento de saída

- **PK**: `Empresa char(2)` + `Documento varchar` + `Serie char`.
- **FKs**: `COD_MOD → Liv_SPED_Modelo_Dcto`, `COD_SIT → Liv_SPED_Situacao_Dcto`,
  `Cliente → Clientes_Principal`, `Empresa → Empresas`.
- **Cobertura**: `Data_Emissao` de **18/07/2018 → 17/09/2026**; **empresa 13** = 12 097 linhas
  (a empresa **01** tem 1 linha avulsa).
- **Situação (`COD_SIT` → `Liv_SPED_Situacao_Dcto`)**:
  | COD | Significado | Linhas | Σ `Valor_Nota` |
  |----:|-------------|-------:|---------------:|
  | 1 | Documento regular | 11 959 | 208 779 234,75 |
  | 3 | Cancelado extemporâneo | 135 | 0 |
  | 6 | Documento fiscal complementar | 3 | 0 |
  | 5 | NF-e numeração inutilizada | 1 | 0 |
- **Modelo (`COD_MOD`)**: `30` = **NF-e modelo 55** (12 097) e `1` = NF modelo 1 (1 avulsa).
- **Valores**: `Valor_Nota`, `Valor_Frete`, `Valor_Desconto`, `Valor_Seguro`,
  `Valor_Outras_Despesas`, `Vr_Tot_DescProd`, `Vr_DescontoGeral`, `Vr_Grande_Total`.
- **Tributos totalizados**: `Vr_TotTributosItens` + `Porc_TotTributosItens` e a abertura
  `{Porc,Vr}_Trib_Itens_Federal|Estadual|Municipal`; FCP `vFCP`/`vFCPST`/`vFCPSTRet`.
- **Local/transporte**: `Tipo_Transporte`, `Tipo_Frete`, `Peso_Liquido`/`Peso_Bruto`,
  `Qtde_Volume`, `Veiculo_Placa`/`Veiculo_UF`, `CNPJ_CPF_{Coleta,Entrega}`,
  `IE_{Coleta,Entrega}`, `Cod_IBGE_{Coleta,Entrega}`.
- **EMIT/EFD**: `IND_EMIT`, `Finalidade_NF`, `Ind_Pres`, `CRT`, `Natureza_Operacao`,
  `VersaoXML`, `Chave_NFe`, `Tipo_Parcela`; contingência (`DataHora_Contingencia`/
  `Justificativa_Contingencia`); cupom/ECF (`COO`, `CRO`, `CRZ`, `ECF_*`, `Nota_Cupom`).
- `Link_CR bit` = ponte para a geração do **contas a receber** (`Notas_Fiscais_Rec`).

### 3.2 `Liv_SaiProd` (34 043) — item fiscal da saída

- **Grão**: `Empresa + Documento + Serie + Seq` (item).
- **Chaves de negócio**: `EmpProd + Produto`, `NatOp` (natureza), `Tipo_Comercializacao`
  (→ `Fig_Comercializacao`), `Codigo_Grupo` (→ `Fig_GrupoFiscal`), `Regra_Fiscal` +
  `Regiao_Origem`/`Regiao_Destino` (**localizam a regra em `Fig_GrupoFiscal_Itens`**),
  `Incremento` (→ `Fig_GrupoFiscal_Itens`), `Unidade`/`UnidadeTributavel`.
- **Identificação**: `ClassFisc` (NCM), `CEST`, `Cod_EAN_GTIN`, `Descricao_Produto`,
  `Codigo_Produto_Concat`/`Descricao_Produto_Concat`, `T` (tipo do item), `Totalizador_SPED`.
- **Tributos (alíquotas e valores)**: ICMS (`Vr_ICMS`, `Vr_BCICMS`, `Porc_ICMS`, `ST_ICMS`,
  `Aliq_ICMS_Interna`, `Aliq_Red_ICMS`, `Vr_Red_BC`, `Porc_ICMSDeferido`/`Vlr_ICMSDeferido`,
  `Vlr_ICMS_OP`), ICMS-ST (`Vr_BCICMS_Subst`, `Porc_IVA`, `Porc_ICMS_Subst`,
  `Vr_ICMS_Subst`, `ModBCST`, `Porc_ReducaoBCICMS_ST`, `Vr_ICMSST_Antecipado`),
  ICMS-ST-UF-destino (`vBCUFDest`/`pFCPUFDest`/`pICMSUFDest`/`pICMSInterPart`,
  `vICMSUFDest`/`vICMSUFRemet`, `pICMSInter`), DIFAL (`Vr_ICMS_DifAliquota`),
  FCP (`vBCFCP`/`pFCP`/`vFCP`, `vBCFCPST`/`pFCPST`/`vFCPST`, `..._Ret`),
  IPI (`Vr_IPI`, `Vr_BCIPI`, `ST_IPI`, `Vr_IPI_NCreditado`, `Vr_IPI_Isento`/`Outras`),
  PIS/COFINS/CSLL (`Porc_PIS`/`Vr_PIS`, `BC_PIS`, `Porc_COFINS`/`Vr_COFINS`, `BC_COFINS`,
  `Vr_CSLL`, `Vr_PISCOFINSCSLL`), ISS (`Porc_ISS`/`Vr_ISS`/`Vr_BC_ISSQN`,
  `ExigibilidadeISS`, `IndIncentivoISS`, `IndISSRet`), IR/INSS (`Porc_IR`/`Vr_IR`,
  `Vr_BC_IRRF`/`Vr_IRRF`, `Porc_INSS`/`Vr_INSS`), Suframa (`Porc_Suframa`/`Vr_Suframa` e
  os descontos por tributo).
- **Rateio/reforma**: `Porc_TotTributos`/`Vr_TotTributos` e a abertura
  `{Porc,Vr}_Trib_{Federal,Estadual,Municipal}`; **campos IBS/CBS/IS** presentes
  (`CST_IBSCBS`, `vBCIBSCBS`, `vIBSUF`, `vIBSMun`, `vCBS`, `AliquotaIBSUF`,
  `AliquotaIBSMunicipio`, `AliquotaCBS`, créditos presumidos e `v_IS`/`CST_IS`).
- **Contabilização**: `Cta_Contabil*` (ICMS/IPI/PIS/COFINS/geral), `Id_Cod_SubItem_CR`/`DB`.
- **Rastreabilidade**: `Metros`, `Qtde_Baixa`, `nFCI`/`ID_Fat_FCI`, `Nr_Ped_Compra`/
  `Item_Ped_Compra`, `idMotivoRestituicaoSPED`, `ID_Fig_MotivoDesoner_ICMS`,
  `Ctrl_Emprest_Terceiros`, `Id_Liv_ProdutosOrigem`.
- **Devolução**: `Porc_Prod_Devolvido`, `Vr_IPI_Devolvido`.

### 3.3 Demais satélites de saída

- `Liv_SaiFat` (28 959) — faturamento/parcelas do documento.
- `Liv_SaiNatOp` (12 098) — natureza de operação (1 por documento).
- `Liv_Sai_FormaPagto` (12 078) e `Liv_SaiObs` (11 958) — pagamento e observações.
- `Liv_SaiProdInfAdic` (5 222) e `Liv_SaiNFRef` (3) — info adicional e notas referenciadas.
- Ajuste/apuração por UF: `Liv_Ajuste_SPED`, `Liv_Adic_ICMSAjuste_SPED`,
  `Liv_Apura_ICMS_SPED`/`ICMSST`/`IPI`/`DIFAL` (+ `Aj`, `Obrig`, `Periodo`), `Liv_Debitos`/
  `Liv_Creditos`, `Liv_EstornoICMS`, `Liv_DocExport_SPED`, `Liv_Export_SPED`.

## 4. Livro fiscal de entradas

### 4.1 `Liv_Entradas` (1 957) — cabeçalho da entrada

- **PK**: `Empresa + Documento + Tipo_Fornec + Fornecedor + Serie` (identifica também o emitente).
- **FKs**: `COD_MOD`, `COD_SIT`, `Fornecedor → Clientes_Principal`, `Empresa → Empresas`.
- **Valores**: `Valor_Nota` (Σ **111 850 066,35** nas 1 948 linhas regulares), `Valor_Frete`,
  `Valor_Desconto`, `Valor_Seguro`, `Valor_Outras_Despesas`, `Vr_Tot_DescProd`,
  `Vr_DescontoGeral`; retenções `Valor_IR`, `Valor_INSS`, `Valor_ISS`,
  `Valor_PISCOFINSCSLL`, `Base_PIS`/`Base_COFINS`, FCP `vFCP`/`vFCPST`/`vFCPSTRet`.
- **Situação (`COD_SIT`)**: regular `1` = 1 948; cancelado extemporâneo `3` = 5;
  complementar `6` = 3; cancelado `2` = 1.
- **Datas**: `Data_Emissao` e `Data_Entrada` (a entrada tem **data própria**), `Hora_Entrada`,
  contingência; `Link_CP bit` = ponte para o **contas a pagar** (`NF_Entradas`).
- **Importação/XML**: `Path_XML`/`Arquivo_XML` (nota importada), `CnpjVinculado`,
  `Cliente_Triangular`, `Facionista`, `isConsumoC500`.
- **Tributos totalizados**: `Vr_TotTributosItens` + `Porc_TotTributosItens` e a abertura
  `{Porc,Vr}_Trib_Itens_{Federal,Estadual,Municipal}`; `CRT`, `Natureza_Operacao`, `VersaoXML`.

### 4.2 `Liv_EntProd` (22 522) — item fiscal da entrada

Espelha `Liv_SaiProd` (mesmos blocos de ICMS/ST/IPI/PIS/COFINS/ISS/IBS/CBS), com diferenças:

- `Tipo_Fornec`/`Fornecedor` na chave; **`NFRemessa`/`Serie_NFRemessa`** (nota de remessa),
  `BC_IImp`/`Vr_IImp`/`Vr_DespAduaneira`/`Vr_IOF_Imp` (importação),
  `Vr_OutrosCred_ICMS`/`Vr_OutrosDeb_ICMS`, `Quebra`, `Acrescimo`, `Qtde_Ref`,
  `Id_Cod_SubItem_CR`/`DB`, `VrICMSDesonerado`.

### 4.3 Demais satélites de entrada

`Liv_EntNatOp` (1 957), `Liv_EntObs` (1 951), `Liv_Ent_Transporte_SPED` (1 756),
`Liv_EntProdRemInd` (6 937, remessa/industrialização), `Liv_EntProd_DI` + `_DI_Adic` (2 427),
`Liv_EntNFRef` (835), `Liv_Ent_FormaPagto` (434), `Liv_EntProdInfAdic` (40); ainda
`Liv_EntFat`, `Liv_Ent_Obs_Fisco`, `Liv_Ent_NFEletrica_SPED`, `Liv_Ent_Telecom_SPED`,
`Liv_Ent_SPED_DocArrecRef`/`ProcRef`, `Liv_EntProdCombustiveis`, `Liv_EntProdRefInd`.

## 5. Tabelas de apoio

- **`Liv_Natureza`** (132) — cadastro de **natureza de operação** (`Codigo`, `Sequencia`,
  `Descricao`, `Aliq_ICMS`, `Nova_CFOP`, `Sit_Trib`, `SomarFrete_ICMBC`, `Calcular_IPI`,
  `Porc_PIS`/`Porc_COFINS`, `ICM_Subst`, `Serv_Indust_Prod_Aplic`, `Informar_NFRemessa`,
  `ST_IPI`/`ST_PIS`/`ST_COFINS`, `ST_ISSQN`, `CSOSN`, `IndOrdemTerceiro`, `IOB_Dest*`).
- **`Liv_Classificacao`** (207) — **NCM**: `Codigo` (formato `0000.00.00`), unidade,
  alíquota de IPI e descrição.
- **`Liv_Servicos`** (129), **`Liv_Genero_Produto`** (97), **`Liv_SPED_CEST`** (1 172),
  **`Liv_DIPI`** (16), **`Liv_CSOSN`** (10), **`Liv_RegimeTributacao`** (9),
  **`Liv_ProdutosOrigem`** (9), **`Liv_Propriedade_Item`** (3), **`Liv_Convenio`** (3).
- **Dicionários do SPED**: `Liv_SPED_Modelo_Dcto` (37 — códigos de modelo: `55`, `57` CT-e,
  `65` NFC-e, `59` CF-e, `67` CT-e OS, `66` NF3e, `56` NFSe…), `Liv_SPED_Situacao_Dcto`
  (9 — `00`…`08` situação do documento).

## 6. Motor de regra fiscal (`Fig_*`)

A tributação de cada item é resolvida por **5 dimensões**: *figura fiscal* × *grupo fiscal* ×
*natureza/comercialização* × *região de origem/destino* × *CFOP/empresa*.

### 6.1 `Fig_FiguraFiscal` (5) + `Fig_FiguraFiscal_CFOP` (183)

Cadastro das "figuras" que definem o enquadramento e os incentivos:

| Código | Descrição | Incentivo ICMS |
|-------:|-----------|----------------|
| 1 | PADRÃO | porc. SUFRAMA |
| 2 | NÃO CONTRIBUINTE | — |
| 3 | IMPORTAÇÃO | porc. SUFRAMA |
| 4 | ZONA FRANCA | — |
| 5 | SIMPLES NACIONAL DE SC | — |

`Fig_FiguraFiscal_CFOP` liga a figura a um **CFOP + regra + grupo fiscal**.

### 6.2 `Fig_GrupoFiscal` (13) — natureza do item

`PRODUCAO PROPRIA`, `NAO UTILIZADO`, `ATIVO IMOBILIZADO`, `MATERIA PRIMA`, `USO E CONSUMO`
(com/sem ST), `EMBALAGEM/SACARIA/VASILHAME`, `MAO DE OBRA`, `TELEFONIA`, `ENERGIA`,
`OLEO/COMBUSTIVEL/LUBRIFICANTES`, `FRETES`, `PRODUTOS IMPORTADOS`. Cada grupo carrega
`ModBCST`, `Porc_IVA`, `Porc_ICMS_Antes_ST`, `Nao_Calcular_Reducao`, `Tipo_Item` e
`Codigo_Tipo_Servico`.

### 6.3 `Fig_GrupoFiscal_Itens` (829) — a **regra fiscal** propriamente dita

Chave composta: `Codigo_Comercializacao` + `Codigo_Grupo` + `Regra_Fiscal` +
`Regiao_Origem` + `Regiao_Destino` + `Empresa` + `CFOP` (+ `Incremento`, `CSOSN`). Para cada
combinação guarda **alíquotas e CSTs**: `Porc_ICMS`, `Porc_ReducaoICMS`, `Porc_IPI`, `Porc_PIS`,
`Porc_COFINS`, `Porc_CSLL`, `Porc_ISS`, `Porc_INSS`, `Porc_IR`, ST
(`Porc_ReducaoBCICMS_ST`, `Porc_Red_IVA`, `ModBCST`), `Trib_*` (CST por tributo),
`Tipo_Trib_*`, `SubstTrib`, `Origem_Produto`, incentivos, `Aliq_ICMS_Interna`,
`ID_Fig_MotivoDesoner_ICMS`, `Enq_IPI`, `cBenef`, e **os campos IBS/CBS/IS**
(`idClassTribIBSCBS`, `CST`/`CSTReg`, `AliquotaIBSUF`, `AliquotaCBS`, créditos presumidos,
`AliquotaSeletivo`…). Valores parametrizáveis adicionais ficam em
**`Fig_GrpFiscItensParamVlr`** (20 169 — `Valor_String`/`Valor_Decimal`/`Valor_Integer`/
`Valor_Bit`).

### 6.4 Demais dimensões

- **`Fig_Comercializacao`** (43) + `_CFOP` (231) — tipo de operação. Exemplos relevantes:
  `(PADRAO) VENDAS` (1), `DEVOLUCAO DE COMPRA` (3), `REMESSA PARA INDUSTRIALIZACAO` (4),
  `RETORNO DE INDUSTRIALIZACAO` (100), `COMPRAS` (103), `DEVOLUCAO DE VENDA…` (21/109),
  `VENDA PARA ENTREGA FUTURA` (111), `NOTAS DE IMPORTACAO` (24). Cada registro tem os bits
  `rec`/`es` (receita/despesa), `dev` (devolução) e `terc` (terceiros).
- **`Fig_RegiaoFiscal`** (5) + `_UF` (28) — região fiscal e o de-para com UF.
- **`Fig_ST_ICMS`/`IPI`/`PIS`/`COFINS`/`IBSCBS`/`Seletivo`** — tabelas de CST/situação
  tributária. **`Fig_Enquadramento_IPI`** (129), **`Fig_ClassificacaoSeletivo`** (28),
  **`Fig_MotivoDesoner_ICMS`** (12), **`Fig_ClassificacaoCredPresumido`**,
  **`Fig_Exigibilidade_ISS`**, **`Fig_IndPres`**, **`Fig_Grupo_IVA`**,
  **`Fig_Cod_DIPAM`**, **`Fig_GrupoContabil`** (+ `_Itens`).

### 6.5 Reforma tributária (IBS/CBS/IS)

O banco **já suporta a reforma**: além dos CST/regras, há as tabelas
**`Fig_IBS_Mun`** (32 214 — alíquota por município), **`Fig_IBS_UF`** (3 229 — por UF:
`Id`, `UF_Estado`, `Incremento`, `Aliquota`, `AliquotaReducao`, `AliquotaDiferimento`) e
**`Fig_ClassificacaoIBSCBS`** (152 — `cClassTrib`), espelhadas nos campos `vBCIBSCBS`,
`vIBSUF`, `vIBSMun`, `vCBS`, `vCredPres*`, `AliquotaIBSUF`/`AliquotaCBS` e no
**Imposto Seletivo** (`v_IS`, `CST_IS`, `AliquotaSeletivo`) de `Liv_SaiProd`/`Liv_EntProd`/
`Liv_XML_Item`.

## 7. SPED / EFD

- **Layouts**: `Liv_Layouts_SPED` (124) + variantes `Liv_Layouts_SPED_PISCOFINS` (66),
  `_G5` (137), `_DF`, `_PE`, `_ECF`. **Registros**: `Liv_TabRegistros_SPED` (142) +
  `_PISCOFINS`, `_Fiscal_DF`, `_Fiscal_PE`.
- **Período/apuração**: `EFD_PERIODO`, `EFD_PROCESSOS`, `EFD_LogImportacao`,
  `Liv_Fechamento_Fiscal`, `Liv_Apura_Periodo_SPED`, `Liv_Apura_ICMS*`/`IPI*`/`DIFAL*`,
  `Liv_Ajuste_SPED*`, `Liv_DocCredFisc_SPED`, `Liv_TabObrigaAjuste_SPED`,
  `Liv_TabCodAjuste_SPED`/`CodCredFisc`/`CodIPIAjuste`/`InfAdAjuste`/`OrigemDoc`/`OrigemProc`,
  `Liv_TabSitTribIPIAjuste_SPED`, `Liv_TabTipoConhec_SPED`.
- **Contribuições (`SPED_PC_*`, 31 tabelas)**: apuração (`EFD`/`Apuracao`/`ApuracaoEntrada`/
  `ApuracaoSaida`), registros `P010`/`P100`/`P110`/`P199`/`P200`/`P210`, `SPED_PC_Campos_P100`,
  `BaseCalculoCredito`, `CodAjuste`/`CodigoAjuste`/`CodDet`/`CodSujRecBruta`,
  `Calculo_Credito_CFOP`, `OpGeradoresContrCredito`/`Cons_OpLP(_Item)`, `Ind_CompRec`,
  `Retencao`, `Parametros`, `SPED_PC_0145`, `SPED_Reg_1010`, `SPED_IdSpedContribuicoes`.
- **EFD ICMS/IPI (`EFD_*`, 125)**: `EFD_LINK*`, `EFD_Protocolos`, mais o bloco **REINF**
  (`EFD_Reinf_Evento_R2060`, `R4010`/`R4020`/`R4040`/`R4080` e suas tabelas-filhas com
  deduções/rendimentos/processos, `R9001`/`R9005`/`R9011`/`R9015` — totalizadores por período;
  `EFD_EVENTOS`/`EVENTOSREINF`, `EFD_REGISTROSREINF`, `EFD_LAYOUTS_REINF`, tabelas
  `EFD_Reinf_Tabela01/02/03`).
- **Cadastros de domínio**: `EFD_PAISES` (242), `EFD_CODPAGAMENTOS` (63), `EFD_TIPOSERVICOS` (31),
  `EFD_COD_ATS_CPRB` (1 298), `EFD_BandeiraCartaoSefaz` (28), `EFD_CODSUSPENSAO` (13),
  `EFD_TRIBEXTERIOR` (11), `EFD_RENDEXTERIOR` (17), `EFD_INFEXTERIOR` (9), `EFD_EVENTOS` (24).
- **NFS-e**: `EFD_NFSERVICOPERIODO`, `EFD_SERVICOS_NF` (+ `_DETALHES`, `_PROCESSO`,
  `_PROCESSO_ADICIONAL`).
- **Cupons/ECF**: `Liv_Cupons`, `Liv_Cupons_Dados_Cfe`, `Liv_Cupons_Finalizadores`,
  `Liv_Itens_Cupons(_Imposto)`, `Liv_ReducaoZ`, `Liv_Maq_Loj`.

## 8. Importação de NF-e XML (`Liv_XML*`)

Fluxo paralelo ao livro fiscal para **notas de terceiros importadas**:

- **`Liv_XML`** (1 690) — cabeçalho (PK `ID_Empresa + ID`): `E_S char` (entrada/saída),
  `cUF`, `CodDFe`, `Documento`, `Serie`, `ModeloDoc`, `Chave_Acesso`, `Status_DFe`,
  `Protocolo_DFe`, `dhEmissao`/`dhEntSai`, `tpOper`, `IndPag`/`IndFrete`, `FinalidadeDFe`,
  `IndFinal`, `idDestinatario`, `cMunFG_ICMS`; totais `Vr_Prod`, `Vr_Frete`, `Vr_Seguro`,
  `Vr_Desconto`, `Vr_II`, `Vr_IPI`, `Vr_PIS`, `Vr_COFINS`, `Vr_Outro`, `Vr_Documento`,
  `Vr_BC_ICMS`/`Vr_ICMS`(+`Deson`), `Vr_BCICMSST`/`Vr_ICMSST`, FCP e ISSQN, e o bloco
  **IBS/CBS** (`vBCIBSCBS`, `vIBSUF`, `vIBSMun`, `vCBS`, créditos presumidos).
- **`Liv_XML_Item`** (20 109) — item: `nItem`, `Codigo_Produto`, `Descricao_Produto`,
  `cEAN_GTIN`, `ClassFisc` (NCM), `CFOP`, `CSOSN`, unidades/qtde, ICMS/ST/IPI/PIS/COFINS/ISS
  completos, FCP, `CEST`, `cBenef`, DIFAL e **todo o bloco IBS/CBS/IS**
  (`CST_IBSCBS`, `AliquotaIBSUF`/`IBSMunicipio`/`CBS`, `v_IS`/`CST_IS`).
- Satélites: `Liv_XML_Emit` (1 690), `Liv_XML_InfCPL` (1 318), `Liv_XML_DocRef` (817),
  `Liv_XML_FormaPagto` (167), `Liv_XML_Cob` (66), `Liv_XML_ItemInfAdProd` (8 656) e
  `Liv_LogImportacaoXML_SFF`.
- Consistência: `Liv_EConsiste` (+ `_DocRef`, `_InfCPL`, `_Item`, `_ItemInfAdic`).

## 9. Modelo 3 (importação/exportação de estoque)

`Liv_Mov_Modelo3` (29) + `_Itens` (99) + `_Saldo` (6) + `_ConsSaldo` (44) +
`_ImportacaoSaldos` (1) e ainda `_Fec`, `_Obs`, `_RefInd`, `_RemRet`, `_SaldoTerc`,
`_TabelaSaldos`, `_ValorArbitrado`, `_ValorizacaoEstoque`, `_RegistrosIgnorar`. Colunas de
`Liv_Mov_Modelo3`: `Data_Lancamento`, `Empresa`, `Documento`, `Serie`, `Chave_NFe`,
`Fornecedor`/`Tipo_Fornec`, `E_S`, `Tipo_Documento`/`Tipo_Lancamento`, `CPF_CNPJ`,
`Valor_Nota`, `Emp_Origem`, `Valor_IR/PIS/COFINS/INSS`, `Usuario`, `Bloqueado`,
`Finalidade_NF`, `COD_MOD`, `COD_SIT`, `Ind_Emit`. Módulo de **pouco uso** (29 linhas).

## 10. Parâmetros (`SIS_Parametros*`)

- **`SIS_Parametros`** (1 521) — catálogo global de parâmetros (nome/código).
- **`SIS_Parametros_Valor`** (7 605) — valor por empresa/chave.
- **`SIS_Parametros_Sistemas`** (2 050, PK `ID_SIS_Param_Sistema`) — de-para
  `ID_Sistema` ↔ `ID_SIS_Parametros` (um parâmetro vale para N "sistemas"/telas).
- **`SIS_Parametros_Tipo_Dado`** (4) — tipos de dado do valor.
- Parâmetros específicos do fiscal também vivem em `Liv_Parametros`,
  `SPED_F_Parametros`, `SPED_PC_Parametros`, `Liv_Parametros_Folhamatic`/`_Prosoft`, e há os
  backups `SIS_PARAMETROS_BKP_20180716` / `SIS_PARAMETROS_NOVOS_20180716`.
- Outras tabelas de infra correlatas: `SIS_Databases`, `SIS_UsuarioEmpresa`,
  `SIS_EmpresaPadrao_Usuario`, `Sistemas`/`Sistemas_Config(_Itens)`, `Sis_Atalhos`.

## 11. Views e procedures

**Views de conferência/apoio** (usadas pela conciliação fiscal):

- `Vw_Liv_Sai_Rel_Conferencia` (11 961), `Vw_Liv_Ent_Rel_Conferencia` (1 956),
  `VW_LIV_SAIPROD` (34 043), `VW_Liv_NotasRemInd` (633), `VW_FAT_FIGURAFISCAL` (829),
  `Vw_Cliente_Endereco_SPED` (1 661), `vwPnLivNatureza` (132), `Vw_LivE_ProdUltNota` (350).

**Procedures** (superfície de geração/integração):

- Livro fiscal: `SP_Liv_*` (importação REDF, exportações Folhamatic/Prosoft/Domínio/Contimatic/
  Asplan), `SP_Lv3_*` (modelo 3), `SP_EFD_*`, `SP_SPED_PC_*` (contribuições),
  `SP_Apura_*`/`SP_Fechamento_Fiscal`.
- Ver [Estudo 11](./11-procedures-e-views.md) para o catálogo completo de procs/views.

## 12. Regras e cuidados para a nova API

1. **Fonte fiscal = `Liv_Saidas`/`Liv_Entradas`** (não `Fat_*`): o dado oficialmente fiscal
   é o `Liv_*`. `Fat_*`/`NF_Entradas` são a origem transacional; `Link_CR`/`Link_CP` amarram
   os dois mundos.
2. **Título = documento** para saída (`Empresa+Documento+Serie`) e **+ emitente** para entrada
   (`+Tipo_Fornec+Fornecedor`): não há surrogate; **normalizar padding** (`char` com espaços).
3. **Item = tributação**: alíquotas/CST/valores estão no item (`Liv_SaiProd`/`Liv_EntProd`),
   **não** recalculáveis na API — apenas transportar. O bloco IBS/CBS/IS já existe (reforma).
4. **Motor `Fig_*` é configuração** (829 regras + 20 169 parâmetros): replicar a regra exigiria
   toda a cadeia `Comercializacao × GrupoFiscal × RegiaoFiscal × CFOP × Empresa`; para
   relatórios, **ler o resultado gravado no item**, não recalcular.
5. **`COD_SIT ≠ 1`** = documento cancelado/inutilizado/complementar: excluir/segurar no ETL
   (saídas: 139 linhas; entradas: 9 linhas).
6. **XML (`Liv_XML*`)** é repositório de NF-e de terceiros (importadas por `E_S`), útil para
   conferência/auditoria, separado do livro fiscal.
7. **SPED/EFD** são **saídas geradas** (layouts/registros + Reinf/Contribuições): a API deve
   expor consulta, **nunca** escrita.
8. `SIS_Parametros*` é o **registro de configuração** do sistema: bom candidato a snapshot
   para o Neon, mas com nomes/valores possivelmente sensíveis — revisar antes de expor.
