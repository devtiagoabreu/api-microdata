# Estudo 23 — Financeiro, fluxo de caixa, contábil, fiscal (apuração) e custo médio

Levantamento de **estrutura** (tabelas, colunas, contagens e parâmetros de procedures) por
`SELECT` somente leitura. Nenhum dado real. Objetivo: fechar o mapa do **financeiro** e responder
definitivamente se existem **contábil**, **apuração fiscal** e **custo médio** persistidos.

## 1. Síntese

| Domínio | Situação no ERP | Fonte real |
|---------|-----------------|-----------|
| Lançamentos bancários / conciliação | **Em uso parcial** | `Bco_Lancamentos`, `BCO_HISTORICOS`, cheques |
| Fluxo de caixa | **Em uso** (materializado, poucas linhas) | `Fluxo_Caixa`, `SP_Fluxo_GerarFluxoPorEmpresa`, `flu_*` |
| Contábil (lançamentos/razão/balancete) | **NÃO usado** (0 linhas) | — (só plano de contas SPED) |
| Apuração fiscal (ICMS/IPI/DIFAL/CIAP/EFD-Reinf) | **NÃO persistida** | `Liv_Apura_*`, `CIAP_*`, `EFD_*` vazios |
| Custo médio | **Calculado on-the-fly**, não persistido | `SP_MCG_Custo_Medio_DGB(_Novo)` sobre `Liv_Entradas/Saidas` |

## 2. Financeiro e banco

### 2.1 Lançamentos bancários

- **`Bco_Lancamentos` (10 864, 31 col.)** — movimento de bancos. Chave da conta:
  `Cod_Empresas`, `Nr_Bco_Bancos`, `Nr_Age_Contas`, `Dig_Age_Contas`, `Nr_Conta_Contas`,
  `Dig_Conta_Contas`, `Incremento`. Campos: `Data`, `Cod_Historico`, `Texto_1..4`, `Valor`,
  `Nr_Cheque`, `Compensado`, `Data_Compensacao`, `Cod_Contabil`, `CCusto`, `Bloqueado`,
  `Cheques_Dep`, `Usuario`, `DataHoraGravacao`, `Integracao`, `IntegracaoSIMPag`,
  `DataLancamento`, `idDocumento`, `IDBaixa`, `idBCOConcBancaria`.
  - `Compensado`/`Data_Compensacao` = conciliação; `idBCOConcBancaria` liga à conciliação (vazia).
  - `Cod_Contabil`/`CCusto` = partida gerencial (o contábil não é usado, ver §3).
- **`BCO_HISTORICOS` (37)** — históricos: `Cod_Historico`, `Tipo` (E/S), `Gerar_Contabilidade`,
  `CContabil`, `Transferencia`, `ObrigaCC`, `idContaContabil`, `Deposito`,
  `DepositoIdentificado`, `IncidenciaImposto`, `LancamentoIdentificado`.
- **`Bco_Diario` (1)** / **`Rec_Diario` (1)** / **`Pag_Diario` (4)** — numeração de livro/razão
  (não são o livro contábil; é controle de formulário).

### 2.2 Cheques e CNAB

- **`Cheques_Emitidos` (2 361, 19 col.)** — `Empresa`, `Banco`, `Nro_Cheque`, `Portador`,
  `Data_Emissao`, `Valor`, agência/conta, `Cancelado`, `Data_Vencto`, `IdCheque`.
- **`Cheques_Emitidos_DebitoCC` (7 774, 20 col.)** — lançamentos de débito em conta vinculados a
  título (`Titulo`/`Parcela`/`Fornecedor`/`Tipo`/`Emitido`).
- Cadastros `CH_*` quase todos vazios (`CH_Agencias` 11, `CH_Bancos` 9, `CH_Help` 26,
  `CH_Conta_Parametros` 2). Cadastros de banco reais em `Bancos` (14) / `CNAB_Banco` (15)
  (ver Estudo 17).

### 2.3 Fluxo de caixa (`Fluxo_*` / `flu_*`)

- **`Fluxo_Caixa` (88)** — projeção materializada por `Data` + `Descricao` (cliente/fornecedor):
  `Receber`, `Pagar`, `Cheque`, `Pagar_Outros`, `SIMCompras`, `CREDIARIO`, `Carteira`,
  `Pagar_COMPROR`, `Bancos`. **`Fluxo_Semanal` (88)** = a mesma projeção em bucket semanal.
- Populado por **`SP_Fluxo_GerarFluxoPorEmpresa`** — parâmetros: `@Empresa`, `@GrupoEmpresa`,
  `@Operacoes`, `@DataInicio`, `@DataFim`, `@UsarDiaGraca`, `@ImprimeDolar`, `@RelacionarCheque`,
  `@SepararFornecedor`, `@DiasGraca` e três `OUTPUT` (`ValorReceberAtraso`, `ValorPagarAtraso`,
  `ValorChequeAtraso`). Monta `#TmpFluxoPag`/`#TmpFluxoRec` a partir de receber/pagar/cheques.
  → **único produtor** da `Fluxo_Caixa` (não há proc em `DBProDash` que a leia).
- **`flu_ConsultaDetalheFluxoCaixa` (45)** — definições de **drill-down** do fluxo: por
  `Guia` (`dbgContasAReceber`, `dbgContasAPagar`, …) e `Coluna` (`DuplicatasEmpresas`,
  `DuplicatasAuxiliares`, `ChequesEmAberto`, `ChequesDevolvidos`, `Cartoes`,
  `PedidosSiMCarteira`, `PedidosSIMPCP`, `TitulosEmpresas`, …), cada uma com um `CONSULTA`
  (SELECT parametrizado). É o motor genérico de "consulta gerencial" do fluxo.
- Config: **`flu_Fluxo_BancosAgContas`**, **`flu_Fluxo_BcoOperacaoDias`** (dias de
  operação/compensação por banco), `flu_Fluxo_ItensNatOP`, `flu_Fluxo_OperacaoSIMPag/SIMRec`
  (open banking/SIMPag — **0 linhas**). `Flu_Parametros` (1), `Flu_Help` (5).
- Demais tabelas `Fluxo_*` (`Fluxo_Pag[_Empresa]`, `Fluxo_Rec[_Empresa]`, `Fluxo_RelDespesa`,
  `fluxo_Lancamentos_*`, `Fluxo_ParamImp*`, `Fluxo_*EntCCusto`) — **todas 0**.
- Relatórios (leem, não persistem): `sp_fluxo_ContasAReceber(ContaBancaria)`,
  `sp_fluxo_ContasAPagar(ContaBancaria)`, `sp_fluxo_ContasBancarias(ContaBancaria)`,
  `sp_fluxo_Faturamento`, `sp_fluxo_Resultado(ContaBancaria)`, `SP_Fluxo_Carteira`,
  `SP_Fluxo_Vencimento`, `sp_FluxoGerencial`, `SP_Fl_Rel_FluxoporTipoConta`,
  `SP_Fl_Rel_FluxoTC_Amort`, `SP_ImportaPagarFluxo`, `SP_InsFluxo`, `SRPT_FLUXO_FUTURO`.

### 2.4 Conciliação bancária

- Família `BCO_ConciliacaoBancaria*` existe mas **0 linhas** → conciliação **não usada**.
  `Bco_Lancamentos.idBCOConcBancaria` fica **sem uso**.

## 3. Contábil — **não é mantido no ERP**

- Toda a escrituração está **vazia**: `ctbContaContabil`, `ctbLancamento`, `ctbLancamentoLog`,
  `ctbPartida`, `ctbFatoContabil`, `ctbPeriodoContabil`, `ctbPlanoContas`, `ctbSaldosIniciais`,
  `ctbEncerramento*`, `SECF_Diario`, `SECF_Fechamento`, `SECF_PlanoConta`, `SECF_BalancoPatrimonio`,
  `SECF_SdoCta*`, `Cont_Balancete` (colunas `Conta/Saldo_Anterior/Debito/Credito`), `TFRazao`,
  `CtbECD*` — **todas 0**.
- O que **existe**: cadastros/mapping para SPED/ECD — `Cont_Plano_Contas_SPED` (757) e
  `_OBS` (757), `ctbNaturezaSubConta` (26), `Cont_Layouts_SPED`/`Cont_Layouts_FCont` (28),
  `SECF_TabDinECF_L210` (99), tabelas de domínio `ctbGrupoConta`/`ctbNatureza`.
- **Consequência:** não há razão/balancete/DRE contábil a extrair. Resultado gerencial só via
  faturamento/custo (§2–§5) e as procs de custo/CC do `DBProDash` (Estudo 21).

## 4. Fiscal — apuração **não persistida**

- `Liv_Apura_ICMS/IPI/ICMSST/DIFAL_SPED(_RECOL/_Aj)`, `Liv_Apura_ObrigICMS*`,
  `Liv_Apura_Periodo_SPED`, `Liv_RegApura*` — **0 linhas**. A apuração é feita **na geração do
  SPED** (on-the-fly), não guardada.
- `CIAP_*` — só cadastros (`CIAP_ParamEmp` 3, `CIAP_TabNumParc` 2, `CIAP_TabOrigem_SPEDPC` 2,
  `CIAP_TabUtil_SPEDPC` 4, `CIAP_TabCCusto_SPEDFiscal` 5); fichas/apropriações **0**.
- `EFD_*` (Reinf) — estrutura completa, mas eventos **0** (`EFD_Reinf_*`, `EFD_*Contrib*` etc.);
  só tabelas de domínio têm dados (`EFD_COD_ATS_CPRB` 1 298, `EFD_PAISES` 242,
  `EFD_Reinf_Tabela01` 236, `EFD_TIPOSERVICOS` 31, `EFD_CODPAGAMENTOS` 63, `EFD_EVENTOS` 24).
- **Dados fiscais reais** continuam sendo os livros do Estudo 18 (`Liv_Saidas` 12 098 +
  `Liv_SaiProd` 34 043, `Liv_Entradas` 1 957 + `Liv_EntProd` 22 522, `Liv_XML` 1 690 +
  `Liv_XML_Item` 20 109).

## 5. Custo médio da mercadoria

- **Não há custo médio persistido**: `PCP_Estoque` (0), `PCP_Historicos` (0),
  `Cfc_Produtos_CustoMedio` (0), `Cfc_Saldo_CustoMedio` (0), `Inv_Comerc_PrecoM` (0).
  (Colunas existiam: `PCP_Estoque.Preco/CustoMedioAcu`, `PCP_Historicos.Custo_Medio`.)
- **É calculado on-the-fly** por **`SP_MCG_Custo_Medio_DGB`** / **`SP_MCG_Custo_Medio_DGB_Novo`**:
  - Assinatura: `@Empresa char(2)`, `@DataFn smalldatetime`, `@AS char(1)='S'`,
    `@Produto char(6)=''`, `@Cor char(5)=''`, `@GrupoNatOp char(2)='CM'`.
  - **Média ponderada pelas NFs do SimLivros**: lê `Liv_Entradas`/`Liv_EntNatOp`/`Liv_EntProd`
    (entrada por NatOp de custo `'CM'`, `Vr_Total_Mov = Valor_Total + Acres_Desc`) e
    `Liv_Saidas`/`Liv_SaiProd`, mantendo `Estoque`, `Vr_Total_Acumulado` e `Custo_Medio` em
    tabelas temporárias (`#Tmp_CustoMedio`, `#Tmp_SaldoInv`, `#Tmp_CM_Sintetico`) e devolvendo um
    **result set** (não grava tabela). Considera importação (II) via `Fat_Itens_Pedido_DI`.
  - `@DataFn` = data final; calcula a partir de `01/01` do ano (`@DataIn`).
- **Custos cadastrais/unitários** (persistidos, mas não são custo médio):
  - `Produtos` (64): `CustoBruto`, `CustoLiquido`, `PercentualDeducaoCusto`.
  - `Produtos_Tecidos` (62): `Custo_Cru`, `Custo_Estampado`, `Custo_Remessa`, `Custo_Outros`
    (+ variantes `*Inv`).
  - `Cte_Peca.Custo_Unitario`, `Vr_Unitario1/2` (custo por rolo/peça, com desembaraço da
    importação embutido).
  - `Custo_Parametros` (1) é **apenas rótulo do sistema** (`Sistema_Parametros='SIMCustos'`),
    não parâmetros de cálculo.
- **`LV3_SdoEst_Fechamento` (4 807)** e **`Lv3EstoqueFechamentoEntregue` (3 512)** = inventário
  SPED (Livro 3) por **quantidade** (`Produto`, `CodigoCliente`, `IndicadorPosse`, `Data`,
  `Quantidade`, `Entregue`) — **sem valor**. Valorização não fica aqui.
- Outras procs de custo: `SP_CMT_CustoMercadoriaVendida` (CMV), `SP_GeraCustoMedio`,
  `SP_PCP_CalculaCustoMedioProd(_utos_Precos)`, `SP_CustoMedioFios`, `SP_CTE_Gera/Recarrega_Custo_FioTinto`,
  `SP_CUSTO_APURA_FIO/TEC`, `FN_PCP_RetornaCustoProduto` (escalar), `Vw_Custo_Depreciacao`,
  `vw_PCP_CustoMedio` (lê `PCP_Estoque`+`PCP_Historicos`, hoje vazios).

## 6. Implicações para a API / Neon

1. **Fluxo de caixa**: portar `SP_Fluxo_GerarFluxoPorEmpresa` é a única forma de reproduzir
   `Fluxo_Caixa`; como ele **grava** nas tabelas do ERP (não é read-only), o ETL deve
   **reimplementar o cálculo no Neon** a partir de receber/pagar/cheques — não chamar a proc.
2. **Custo médio**: não há tabela para sincronizar; o ETL precisa **executar/reimplementar o
   algoritmo do `SP_MCG_Custo_Medio_DGB`** (`Liv_Entradas`/`Liv_Saidas`, NatOp `'CM'`, II da
   importação) e **materializar** `core.custo_medio` com watermark `(@Empresa, @DataFn, Produto, Cor)`.
   Alternativa barata: extrair `Cte_Peca.Custo_Unitario` e `Produtos*.Custo*` (persistidos).
3. **Contábil e apuração fiscal**: **não há o que extrair**. DRE/resultado no Neon deve ser
   gerencial (faturamento − CMV − despesas), não contábil.
4. **Banco/conciliação**: a extrair `Bco_Lancamentos`, `Cheques_Emitidos(_DebitoCC)`,
   `BCO_HISTORICOS`; conciliação fica de fora (vazia).

## 7. Objetos-chave deste estudo

- Financeiro: `Bco_Lancamentos`, `BCO_HISTORICOS`, `Cheques_Emitidos`, `Cheques_Emitidos_DebitoCC`.
- Fluxo: `Fluxo_Caixa`, `Fluxo_Semanal`, `flu_ConsultaDetalheFluxoCaixa`, `SP_Fluxo_GerarFluxoPorEmpresa`,
  `sp_fluxo_*`, `SP_Fluxo_Carteira/Vencimento`.
- Contábil (vazio): `ctb*`, `SECF_*`, `Cont_Balancete`, `TFRazao` — **só** `Cont_Plano_Contas_SPED` (757).
- Fiscal (vazio): `Liv_Apura_*`, `CIAP_*`, `EFD_*`.
- Custo: `SP_MCG_Custo_Medio_DGB(_Novo)`, `SP_CMT_CustoMercadoriaVendida`, `Cte_Peca.Custo_Unitario`,
  `Produtos.Custo*`, `Produtos_Tecidos.Custo_*`, `LV3_SdoEst_Fechamento`.
