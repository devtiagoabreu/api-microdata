# Estudo 15 — Catálogo de functions (194)

Levantado com **SELECTs de catálogo** (`sys.objects`, `sys.parameters`, `sys.sql_modules`,
`sys.sql_expression_dependencies`). Apenas assinaturas/finalidade e contagens; sem dados reais.

## 1. Inventário

| Tipo | Qtde |
|------|-----:|
| `SQL_SCALAR_FUNCTION` | 141 |
| `SQL_TABLE_VALUED_FUNCTION` (multi-statement) | 40 |
| `SQL_INLINE_TABLE_VALUED_FUNCTION` | 13 |
| **Total** | **194** |

- **81 de 194 (≈42%) são órfãs** — nenhum outro objeto as referencia (muitas legado/experimento,
  principalmente dos módulos vazios PCP/CTE/TNT/PLM).
- Prefixos mistos: `FN_`/`fn_`/`FNC_`/`fnc_` (sem convenção única).

### Mais referenciadas

| Função | Usos | Papel |
|--------|-----:|-------|
| `FNC_VlParamEmpSis` | 150 | valor de **parâmetro por empresa+sistema** |
| `FNC_VlParamEmp` | 51 | valor de **parâmetro por empresa** |
| `FNC_POEZEROS` | 28 | padding com zeros (esquerda/direita) |
| `fnc_VoltaQMP` | 18 | unidade **QMP** (massa × metro) do produto |
| `Fnc_Proximo_Data_Util` | 10 | próximo dia útil (pula fds/feriados) |
| `FNC_Data_de_DataHora` | 8 | extrai data de datetime |
| `FN_Fig_GrupoContabil_Itens` | 8 | contas contábeis do grupo |
| `FN_PLM_Gerar_Condicao_Processo` | 7 | PLM (módulo vazio) |
| `FNC_LIV_SIT_TRIB` | 5 | situação tributária do item |

## 2. Temas

### 2.1 Parâmetros por empresa/sistema (nucleares)

- **`FNC_VlParamEmpSis(@Param, @Empresa char(2), @ID_Empresa int, @Sistema)`** → `varchar(255)`.
  Resolve o `Id_Empresa` via `Empresas.Codigo_Empresas` e busca o parâmetro na tabela de valores de
  parâmetros, respeitando o **sistema** (lista separada por vírgula, parseada em loop).
- **`FNC_VlParamEmp(@Param, @Empresa, @ID_Empresa)`** → idem, sem filtro de sistema; escolhe o campo
  conforme `campo_valor` (`Valor_Varchar`/`Valor_Inteiro`/`Valor_Decimal`).
- **`FN_SISParametros(@idEmpresa, @nomeParam, @sistema)`** → `varchar(50)` via `VW_SIS_PARAMETROS`
  (`id_Empresa`, `nome`, `ID_Sistema`) — versão que lê a view.

> Conclusão: a configuração é **por empresa** (`Empresas`: `Id_Empresa` int / `Codigo_Empresas` char(2))
> e por **sistema**. Qualquer endpoint parametrizável deve resolver por aqui antes de chumbar regra.

### 2.2 Formatação / conversão de tipo

`FNC_POEZEROS` (28), `fnc_VoltaQMP` (18), `FNC_SomenteNumeros` (4), `FNC_ValCampoNum`,
`FNC_Formata_CPF_CNPJ`, `fnc_Liv_Numerico`, `fnc_Liv_RemoveZeroEsquerda`,
`Fnc_Remove_Caracteres_Especiais`, `Fnc_ValorNumerico`, `FN_LetraAlfabeto_Indice`,
`FNC_GROUP_CONCAT_NATOP_OBS`, `FN_Retorna_String_JSON`, `fnc_string_to_table` (inline TVF).

- `fnc_VoltaQMP(@MEmp, @MProd)` → `char(1)`: decide a unidade QMP lendo
  `Car_Parametros.Usa_QMP_Parametros`, `Fat_Parametros.QMP_Padrao`, `CTE_Parametros.Validar_UnidadeQMP`
  e `Liv_Diario.Empresa_Produtos`.
- `FNC_POEZEROS(@P_VALOR, @P_ZEROS, @P_SENTIDO)` — padding (0=esquerda, 1=direita): usado em várias
  views de romaneio.

### 2.3 Datas úteis / períodos

- `Fnc_Proximo_Data_Util(@Data, @Dias)` (10) e `Fnc_Anterior_Data_Util` (5): pulam sábado/domingo e
  a tabela **`Feriados`**.
- `FNC_QtdeDiasUteis_EntreDatas`, `Fnc_Data_DiasUteis_Periodo`, `FNC_QtdeDiaUtil`,
  `FNC_Valida_FeriadosFDS`.
- `FNC_EndOfMonth` (3), `FNC_StartOfWeek`/`FNC_EndOfWeek`, `Fnc_RetornaPeriodo_PrimeiroUltimo_DiadoMes` (3).
- `FNC_Data_de_DataHora` (8), `FNC_MinuteToHour` (3), `FNC_DateToMinute`, `FNC_Data_de_DataHora`,
  `Fnc_Data_FinalMes`, `fnc_NomeMes`.

> Dependência transversal: **`Feriados`** (calendário) é requisito para replicar prazos em Python.

### 2.4 Fiscal (Liv/Fig/Fat)

- `FNC_LIV_SIT_TRIB(@EMPPROD, @PRODUTO, @CFOP, @SEQ, @ITEM)` → `varchar(3)`: CST/situação tributária
  (ICMS/IPI/PIS/COFINS/ISSQN + tipo de tributação) para livros fiscais.
- `FNC_Produto_BuscaGrupoFiscal(@EmpresaProduto, @Produto, @CodConcat)` → usa
  **`Produtos_Cod_Concat_EFD`** e cai em `Produtos.Grupo_Fiscal`.
- `FNC_Produto_TipoItem(@Empresa, @CodConcat)` → tipo de item (EFD), `Produtos_Cod_Concat_EFD` +
  `ProdutosTipoItemPorEmpresa`.
- `FN_Fig_Critica`, `FN_Fig_GrupoContabil_Itens(@Empresa,@NatOp,@GrupoContabil,@Comercializacao,
  @Cliente,@DataDocumento,@Sistema,@Servico)` (8) + `...ContaDebito`/`...ContaCredito`: contabilização
  (figura fiscal) por grupo contábil/natureza.
- `FN_FAT_CRITICA_ORIGEM_FCI(_INLINE)`, `FN_FAT_FCI_CONTRATANTE_INTERNO`,
  `FN_FAT_MEDIA_PONDERADA_FCI`: **FCI** (Ficha de Conteúdo de Importação) — origem/contratante/média
  ponderada de importação.
- `FNC_Valida_Ean_13` (3), `FNC_GerarEAN13`, `Fnc_Car_Gerar_Validar_EAN13`, `FNC_Calcula_DUN14`
  (logística/EAN/DUN-14).
- `FNC_Ciap_Data_Limite`, `fnc_Fat_Get_Difal_Item`, `FNC_LV3_ObsLivros`, `fnc_fat_geraFatRomCaixas`.

### 2.5 Contas a receber / comissões

- `FN_Rec_DuplicatasEmAberto(@Data_Retroativa)` (inline TVF): parcela em aberto com
  `Valor_Parcelas - SUM(Rec_Baixas.Valor_Liquido)` — base da view `VW_Rec_DuplicatasEmAberto`.
- `FN_REC_SaldoDuplicataEstornada(...)` — saldo considerando baixas de operação
  `'O'`/`'E'`/`'R'`/`'P'` (estorno/repagamento) com `IndTipoOperacao`.
- `FN_REC_SaldoDuplicataRepagamento(...)` (TVF) — saldo via `Rec_Baixas` + `Rec_Integracao_Dup`/
  `Rec_Integracao_Ch_Dup` (cheques devolvidos).
- `FN_Rec_BuscaJurosDescontosIntegracao(...)` (TVF multi) — juros/descontos com e sem vínculo e de
  cheque devolvido.
- `FN_REC_RetornaSomaValorChequesPorDocumento(...,@SituacaoCheque,@IncluirJurosDesconto)` (2).
- `FNC_RetornaSomaValorChequesPorDocumento`, `FNC_Rec_Saldo_CredFornec` (órfã).
- `fnc_tabela_comissoes` (TVF) — % de comissão de `rec_comissoes`.

### 2.6 Preço / comercial

- **`fnc_pesquisa_tab_preco(...)`** (15 params) → delega a `fnc_pesquisa_tab_preco_mod1`/`_mod2`:
  resolve a **tabela de preço** por cliente/empresa/produto/cor/situação/desenho/variante/
  classificação/categoria/cond. pagamento/vendedor/data.
- `fnc_retorno_tab_preco(...)` (inline TVF, 20 params) — retorno detalhado do preço.
- `fnc_calcula_juros_tab_preco(@empresa,@cond_pagto,@tb_preco,@m)` — juros por prazo médio
  (`condicoes_pagto_parcelas.dias_pagto_parcelas`) e `car_tabela_preco.tx_juros_diaria`; flag
  `Juros_SimpComp_TabPreco`.
- `FNC_ValorMinFaturamento(@Empresa,@Produto,@Tabela,@DtReferencia)` — custo × margem
  (`Cfc_Tabelas_Margem`); `Fn_RetornaUltiPrecoCusto` usa `Tnt_CustoMP` ou `Ret_Lancamentos`.

### 2.7 Medidas / conversão

- `FNC_RetornaFator(@Inverter,@Origem,@Destino)` → `Conversao_Medida.Fator` (inverte se preciso).
- `FNC_RetornaQtde_ConversaoMedida(...)` (3) e `FNC_UnidadeExcecao(...)` (3) — exceções por produto/
  fornecedor em `Produto_Excecao_ConvMedida`.
- `fnc_concatCorDesSGSG`, `fnc_cte_faccaoProdutosSGrSgr` (TVF).

### 2.8 Módulos vazios (baixo interesse)

`FN_PLM_*`, `FN_PCP_*`/`FNC_PCP_*`, `FN_CTE_*`/`fn_cte*`/`fncCte*`, `FN_Tnt_*`/`FNC_Tnt_*`/`fnc_tnt*`,
`FN_SCT_*` (custos de produção), `FN_Loj_*`, `FN_Cmt_*` (comodato — este tem dados: 5.270).
Coerente com o **Estudo 14** (módulos de produção vazios).

### 2.9 Infra / metadados

`fn_diagramobjects`, `FN_PLM_CREATE_VIEW` (gera DDL de view!), `fnc_Busca_Tabelas_Filhas`,
`fnc_mic_user` (usada pela view `Vw_Usuarios`), `fn_Mic_Versao`/`_versao_atual`/`_Get_Versao_Comando`.

## 3. Funções referenciadas por *views* (relevantes à API)

| View | Função |
|------|--------|
| `Vw_Car_PedRom`, `VW_Tnt_PedRom` | `FNC_VlParamEmpSis` |
| `VW_PCP_Feed_Item_Romaneio`, `VW_PCP_LotesDisponiveis`, `VW_PCP_ReservaLotes`, `VW_PCP_Pedidos_ReservaLotes` | `FNC_VlParamEmp` |
| `VW_PCP_Pedido`, `Vw_Rec_Cheques`, `Vw_Rec_Inf_Comerciais` | `FNC_Data_de_DataHora` |
| `VW_CTE_Campos_Layout_Embaladora` | `fnc_VoltaQMP` |
| `Vw_Cte_Romaneio`, `Vw_Cte_Rom_Estamparia_Transf` | `FNC_POEZEROS` |
| `Vw_Car_Retorno_Gera_Livros_Ret`/`_Serv` | `fnc_cte_getgrupofiscal`, `FNC_LIV_SIT_TRIB` |
| `Vw_Cfc_PedRom` | `FNC_ValorMinFaturamento` |
| `VW_MP_Auxiliar_Saldo` | `FN_Rendimento` |
| `vw_SIC_FAT_Transportadora` | `Fnc_Proximo_Data_Util` |
| `Vw_Usuarios` | `fnc_mic_user` |

## 4. Impacto na nova API (read-only)

Funções que a API provavelmente precisa **reimplementar em Python** (ou chamar via SELECT):

1. **Parâmetros** —    `FNC_VlParamEmpSis`/`FNC_VlParamEmp`/`VW_SIS_PARAMETROS`: base de toda
   parametrização por empresa/sistema.
2. **Datas úteis/calendário** — `Fnc_Proximo/Anterior_Data_Util`, `FNC_QtdeDiasUteis_EntreDatas`,
   `FNC_EndOfMonth` (dependem de `Feriados`).
3. **Formatação** — `FNC_POEZEROS` (padding de códigos), `FNC_SomenteNumeros`, `fnc_VoltaQMP`.
4. **Fiscal** — `FNC_LIV_SIT_TRIB`, `FNC_Produto_BuscaGrupoFiscal`/`TipoItem` (EFD), FCI
   (`FN_FAT_*FCI`) e contabilização (`FN_Fig_*`).
5. **Receber** — `FN_Rec_DuplicatasEmAberto` + saldos de estorno/repagamento (juros/descontos).
6. **Preço/comercial** — `fnc_pesquisa_tab_preco*`/`fnc_retorno_tab_preco`/`fnc_calcula_juros_tab_preco`.
7. **Medidas** — `FNC_RetornaFator`/`FNC_RetornaQtde_ConversaoMedida`/`FNC_UnidadeExcecao`.

Podem ser **ignoradas** (módulos vazios — Estudo 14): `FN_PLM_*`, `FN_PCP_*`/`FNC_PCP_*`,
`FN_CTE_*`/`fn_cte*`, `FN_Tnt_*`/`FNC_Tnt_*`, `FN_SCT_*`, além das ~81 órfãs.

## 5. Contagens de apoio

- 194 functions · 81 órfãs · 141 escalares / 40 TVF / 13 inline.
- Top uso: `FNC_VlParamEmpSis` 150 · `FNC_VlParamEmp` 51 · `FNC_POEZEROS` 28 · `fnc_VoltaQMP` 18 ·
  `Fnc_Proximo_Data_Util` 10 · `FNC_Data_de_DataHora` 8.
- 21 funções referenciadas por views (tabela da seção 3).
- Tabelas de apoio citadas: `Empresas`, `Feriados`, `Produtos_Cod_Concat_EFD`,
  `ProdutosTipoItemPorEmpresa`, `Conversao_Medida`, `Produto_Excecao_ConvMedida`, `car_tabela_preco`,
  `condicoes_pagto(_parcelas)`, `rec_comissoes`, `Cfc_Tabelas_Margem`, `Tnt_CustoMP`, `Ret_Lancamentos`,
  `Rec_Integracao_Dup`/`Rec_Integracao_Ch_Dup`.
