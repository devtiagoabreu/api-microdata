# Estudo 18 — Área fiscal (Liv_*/EFD/SPED e figura fiscal)

Levantado com **SELECTs somente leitura** (catálogo, contagens e colunas). Sem dados/valores reais.

## 1. Panorama

| Domínio | Tabelas (linhas) |
|---------|------------------|
| **Saídas (livro fiscal)** | `Liv_Saidas` (12 098) + `Liv_SaiProd` (34 043), `Liv_SaiNatOp` (12 098), `Liv_Sai_FormaPagto` (12 078), `Liv_SaiObs` (11 958), `Liv_SaiProdInfAdic` (5 222) |
| **Entradas (livro fiscal)** | `Liv_Entradas` (1 957) + `Liv_EntProd` (22 522), `Liv_EntNatOp` (1 957), `Liv_Ent_FormaPagto` (434), `Liv_EntObs` (1 951), `Liv_EntProdRemInd` (6 937), `Liv_EntProd_DI(_Adic)` (2 427) |
| **XML NF-e importado** | `Liv_XML` (1 690) + `Liv_XML_Emit` (1 690), `Liv_XML_Item` (20 109), `Liv_XML_ItemInfAdProd` (8 656), `Liv_XML_DocRef` (817), `Liv_XML_InfCPL` (1 318), `Liv_XML_FormaPagto` (167) |
| **Figura fiscal (tributos)** | `Fig_GrpFiscItensParamVlr` (20 169), `Fig_GrupoFiscal_Itens` (829), `Fig_Comercializacao_CFOP` (231), `Fig_FiguraFiscal_CFOP` (183), `Fig_GrupoFiscal` (13), `Fig_RegiaoFiscal_UF` (28), `Fig_IBS_Mun` (32 214)/`Fig_IBS_UF` (3 229), ST (PIS/COFINS/IPI/ICMS/IBSCBS), `Fig_Classificacao*` |
| **SPED / EFD** | `Liv_SPED_CEST` (1 172), `Liv_TabRegistros_SPED(_PISCOFINS)` (142/144), `Liv_Ent_Transporte_SPED` (1 756), `Lv3_SdoEst_Fechamento` (4 807), `Lv3EstoqueFechamentoEntregue` (3 512); `EFD_*` (cadastros: países, Reinf, códigos) |
| **Parâmetros** | `SIS_Parametros` (1 521) + `SIS_Parametros_Valor` (7 605) + `SIS_Parametros_Sistemas` (2 050); `Liv_Parametros` (**1**) |

> `Notas_Fiscais_Rec`/`CCD`/`Parcelas` (módulo REC, Estudo 05) são o **título financeiro**; `Liv_Saidas`/
> `Liv_Entradas` são o **registro do livro fiscal**. Ligação por `Empresa`/`Documento`/`Serie`; em
> `Liv_Saidas` o flag `Link_CR` indica o vínculo com o contas a receber.

## 2. Saídas — `Liv_Saidas` + `Liv_SaiProd`

`Liv_Saidas` (68 col): `Empresa`, `Documento`, `Serie`, `Cliente`, `Tipo_Doc`, `Data_Emissao`,
`Valor_Nota`, **`Link_CR`**, `COD_SIT`, `Finalidade_NF`, `COD_MOD`, `Chave_NFe`, `Tipo_Frete`,
`Peso_Liquido/Bruto`, `Usar_Calc_FigFiscal`, `Vr_TotTributosItens`, `Porc_TotTributosItens`, etc.

`Liv_SaiProd` (**231 col**) — item com **todo o detalhamento tributário**:
chave `Empresa+Documento+Serie+NatOp+Seq`; `EmpProd`, `Produto`, `Incremento`, `Qtde`, `Valor_Total`,
`Vr_Unitario`; e os tributos `Vr_ICMS/Vr_BCICMS`, `Vr_ICMS_Subst`, `Vr_IPI`, `Vr_PIS`, `Vr_COFINS`,
`Vr_CSLL`, `Vr_ISS`, `Vr_INSS`, `Vr_IR`, `Vr_Suframa` (cada um com `Porc_*`, `BC_*`, isento/outras).
Classificação fiscal: `Tipo_Comercializacao`, `Codigo_Grupo`, `Regra_Fiscal`, `Regiao_Origem`,
`Regiao_Destino`, `ST_ICMS/IPI/PIS/COFINS`, `ClassFisc`.

`Liv_SaiNatOp` (23 col): totais por natureza de operação (`NatOp`, `Seq`, `CContabil`, `ICM_BC`,
`ICM_Porc`, `ICM_Valor`, `ICM_Subst`, `IPI_*`, `Vr_Contabil`).

## 3. Entradas — `Liv_Entradas` + `Liv_EntProd`

`Liv_Entradas` (64 col): igual às saídas, com `Tipo_Fornec`/`Fornecedor`, `Data_Entrada`, `Path_XML`/
`Arquivo_XML`, `Cliente_Triangular`, `Link_CP`, bases de PIS/COFINS/ISS.

`Liv_EntProd` (230 col): espelho dos itens de entrada (`Tipo_Fornec`, `Fornecedor`, `NFRemessa`…), mesmos
campos de imposto. Complementos: `Liv_EntProd_DI`/`_Adic` (DI/importação), `Liv_EntProdRemInd`
(remessa/industrialização), `Liv_EntNatOp` (30 col, com ST antecipado).

## 4. Importação de NF-e (XML)

- `Liv_XML` (71 col): cabeçalho do XML (`Chave_Acesso`, `ModeloDoc`, `dhEmissao`, `Status_DFe`,
  `Protocolo_DFe`, totais `Vr_BC_ICMS`, `Vr_ICMS`, `Vr_ICMSST`, `Vr_IPI`, `Vr_PIS`, `Vr_COFINS`,
  e campos de reforma `vBCIBSCBS`, `vIBSUF`, `vIBSMun`…) + `E_S` (entrada/saída), `ID_Empresa`.
- `Liv_XML_Emit` (emitente), `Liv_XML_Item` (145 col — item cru da NF-e com CST/CSOSN, CFOP, bases e
  alíquotas de cada tributo), `Liv_XML_ItemInfAdProd`, `Liv_XML_DocRef`, `Liv_XML_FormaPagto`.

## 5. Figura fiscal (motor tributário)

`Fig_GrupoFiscal_Itens` (**85 col**) é a regra: chave `Incremento`, `Codigo_Comerc`,
`Codigo_Grupo`, `Regra_Fiscal`, `Regiao_Origem/Destino`, `Empresa`, `CFOP` → `Porc_ICMS`,
`Porc_ReducaoICMS`, `Porc_IPI`, `Porc_PIS`, `Porc_COFINS`, `Porc_CSLL`, `Porc_ISS`, `Porc_INSS`,
`Porc_IR`, `Porc_Suframa`, `Trib_*`, `Tipo_Trib_*`, `CSOSN`, `SubstTrib`, `Somar_IPI_BCICMS`,
`Origem_Produto`… Valores parametrizados em `Fig_GrpFiscItensParamVlr` (20 169) + `Fig_GrupoFiscalItensParam` (32).

Complementos: `Fig_GrupoFiscal` (13, cabeçalho), `Fig_Comercializacao` (43)/`Fig_Comercializacao_CFOP`
(231), `Fig_FiguraFiscal_CFOP` (183), tabelas `ST_PIS/COFINS/IPI/ICMS/IBSCBS`, `Fig_Enquadramento_IPI`,
`Fig_RegiaoFiscal(_UF)`, e as de **reforma tributária IBS/CBS** (`Fig_IBS_Mun`/`Fig_IBS_UF`,
`Fig_ClassificacaoIBSCBS`, `Fig_ClassificacaoCredPresumido`, `Fig_ST_IBSCBS`).

`Fig_RegiaoFiscal_UF` (28): `Estado`, `pICMSInterPart` (partilha interestadual), `pFCPUFDest`,
`pICMSUFDest` — usado na tabela de preço (Estudo 17).

## 6. Parâmetros do sistema

O sistema de parâmetros que fundamenta `FNC_VlParamEmpSis` (Estudo 15):
`SIS_Parametros` (id/nome/descrição/tipo), `SIS_Parametros_Valor`
(`ID_Empresa` + `Valor_Varchar/Inteiro/Decimal/Datetime`), `SIS_Parametros_Sistemas`
(quais parâmetros pertencem a quais sistemas), `SIS_Parametros_Tipo_Dado` (4), `SIS_Databases` (4),
`SIS_UsuarioEmpresa` (68), `SIS_EmpresaPadrao_Usuario` (9).
`Liv_Parametros` tem **1 registro** (config fiscal; inclui `obs_ipi='N'` visto no Estudo 12).

## 7. SPED / EFD

- **Livro 3 (inventário)**: `Lv3_SdoEst_Fechamento` (4 807) e `Lv3EstoqueFechamentoEntregue` (3 512) —
  únicas tabelas de fechamento com dados (Estudo 16). `LV3_Processamento*`, `Lv3_ProdNaoPassaTrava*`.
- **Tabelas de apoio**: `Liv_SPED_CEST` (1 172), `Liv_TabRegistros_SPED` (142),
  `Liv_TabRegistros_SPED_PISCOFINS` (144), `Liv_Ent_Transporte_SPED` (1 756), `Liv_Classificacao` (207).
- **EFD**: majoritariamente cadastros de referência (`EFD_PAISES` 242, `EFD_CODPAGAMENTOS` 63,
  `EFD_TIPOSERVICOS` 31, `EFD_BandeiraCartaoSefaz` 28, `EFD_Reinf_Tabela01/02/03`,
  `EFD_COD_ATS_CPRB` 1 298). Fechamentos REINF vazios.

## 8. Impacto na API (read-only)

1. **Endpoints fiscais** naturais: saídas (`Liv_Saidas`/`Liv_SaiProd`), entradas
   (`Liv_Entradas`/`Liv_EntProd`), NF-e importadas (`Liv_XML*`), totais por NatOp (`Liv_*NatOp`).
2. **Cálculo de imposto**: a regra está em `Fig_GrupoFiscal_Itens` (+ `Fig_GrpFiscItensParamVlr`) e
   `Fig_RegiaoFiscal_UF`; os valores de cada item já vêm gravados em `Liv_*Prod` (231/230 col) → a API
   deve **ler o valor materializado**, não recalcular.
3. **Params**: qualquer regra parametrizável sai de `SIS_Parametros*` (não chumbar).
4. **Reforma tributária**: já há estrutura IBS/CBS (`Fig_IBS_*`, campos `vIBS*` em `Liv_XML`) — considerar
   nos modelos.
5. **Volumes** definem custo de consulta: `Liv_SaiProd` 34 043 e `Liv_XML_Item` 20 109 são as maiores.

## 9. Contagens de apoio

- Maiores: `Liv_SaiProd` 34 043 · `Liv_SaiFat` 28 959 · `Liv_EntProd` 22 522 · `Liv_XML_Item` 20 109 ·
  `Liv_SaiNatOp`/`Liv_Saidas` 12 098 · `Liv_Sai_FormaPagto` 12 078 · `Liv_EntProdRemInd` 6 937.
- Header: `Liv_Saidas` 12 098 · `Liv_Entradas` 1 957 · `Liv_XML` 1 690.
- Figura fiscal: `Fig_GrpFiscItensParamVlr` 20 169 · `Fig_GrupoFiscal_Itens` 829 ·
  `Fig_Comercializacao_CFOP` 231 · `Fig_FiguraFiscal_CFOP` 183 · `Fig_GrupoFiscal` 13.
- Parâmetros: `SIS_Parametros_Valor` 7 605 · `SIS_Parametros_Sistemas` 2 050 · `SIS_Parametros` 1 521.
- SPED: `Liv_SPED_CEST` 1 172 · `Lv3_SdoEst_Fechamento` 4 807 · `Lv3EstoqueFechamentoEntregue` 3 512.
- Vazios com dados esperados 0: `Liv_Itens_Cupons`, `Liv_Servicos_Itens`, `EFD_*FECHAMENTOREINF`.
