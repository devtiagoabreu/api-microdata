# Estudo 36 — Custos (custo médio, ficha técnica, valorização)

Aprofundamento do **custo** no ERP. Consolida e detalha o que apareceu de forma panorâmica
nos [Estudos 14](./14-modulos-producao-e-mapa.md), [15](./15-functions.md),
[23](./23-financeiro-contabil-custo.md), [29](./29-faturamento-nf.md),
[34](./34-estoque-cte-saldos-movimentos.md) e [35](./35-fiscal-sped-liv-fig-efd.md).
Aqui o foco é responder: **onde o custo (custo médio, ficha técnica, valorização de estoque)
realmente vive neste banco** — o que é persistido, o que é calculado na hora e o que está
desligado. Levantamento por `SELECT` somente leitura.

## 1. Síntese

O achado central: **o custo não é persistido nesta base**. Praticamente todo o módulo de
custo está **vazio**, e o custo médio de mercadoria é **calculado on-the-fly** pela procedure
`SP_MCG_Custo_Medio_DGB`, que percorre o **livro fiscal** (`Liv_Entradas`/`Liv_Saidas`).

| Papel | Objeto | Linhas | Estado |
|-------|--------|-------:|--------|
| **Motor do custo médio fiscal** | `SP_MCG_Custo_Medio_DGB` / `_Novo` | — | **Em uso** (cálculo on-the-fly) |
| Parâmetros do módulo custo | `Custo_Parametros` | 1 | Só o cabeçalho (sem config real) |
| Tabelas do módulo `Custo_*` | 67 tabelas (ficha técnica, depreciação, energia, máquina, GIF…) | **0** | **Vazias — módulo desligado** |
| Custo por produto/cor persistido | `Produtos_Custos` / `_CustoInv` / `_Custo_Sit` | 0 / 0 / 0 | Vazias |
| Custo médio do PCP/loja | `PCP_Estoque` / `PCP_Produtos_Precos` / `PCP_Historicos` | 0 / 0 / 0 | Vazias |
| Custo médio do CFC (ficha técnica) | `Cfc_Produtos_CustoMedio` | 0 | Vazia |
| Custo de matéria-prima têxtil | `Tnt_CustoMP` | 0 | Vazia |
| Preços/lançamentos de terceiros (`Ret_*`) | `Ret_Lancamentos` / `Ret_Precos` / `Ret_CxsFios` | 1 / 0 / 0 | Resíduo |
| Custo estático do tecido (por produto) | `Produtos_Tecidos` (`Custo_Cru/Estampado/Remessa/Outros`) | 16/15/21/15 de 62 | **Único custo gravado** |
| Custo por peça (rolo) | `Cte_Peca.Custo_Unitario` | **0** de 297 044 | Coluna existe, nunca preenchida |
| Custo no cadastro de produto | `Produtos.CustoBruto/Liquido` | 0 de 64 | Colunas existem, nunca preenchidas |
| Valorização de estoque Modelo 3 | `Lv3_SdoEst_Fechamento` | 4 807 | **Em uso** (fechamento fiscal) |
| Valorização de estoque por item (LV3) | `LV3_Prod_ValorInv` / `_Doc` | 0 / 0 | Vazias |

> Ou seja: para expor **custo médio** na nova API, o caminho é **replicar/consumir o resultado
> de `SP_MCG_Custo_Medio_DGB`** (cálculo determinístico sobre o livro fiscal), e **não** ler uma
> tabela de custo — porque ela não existe preenchida.

## 2. O módulo `Custo_*` (67 tabelas) está desligado

Há **68 tabelas** com prefixo `Custo`:

`Custo_Anotacoes`, `Custo_Atualizacao`, `Custo_Categoria_Produto`, `Custo_Condutivo_MatSemTubo`,
`Custo_Cores`, `Custo_CustoMaquina(_Item)`, `Custo_Deprec_GrupoMaq/_Indice/_Maq/_ProdGrupo/_Producao`,
`Custo_Despesas(_Mensal)(_Mensal_Itens)`, `Custo_Encargos(_Tipo)`, `Custo_Energia(_Itens)`,
`Custo_Fases(_Revisao)`, `Custo_GIF`, `Custo_Grupo_Despesas`, `Custo_ImportaFT*_Log`,
`Custo_Laminado_Material`, `Custo_Mao_Obra_Bag`, `Custo_Maquina(_Redistribuicao)(_x_Produto)`,
`Custo_Operacoes_Bag`, `Custo_Param_Produto_PP`, `Custo_ParamEmp`, `Custo_Parametros`,
`Custo_ParamProducao`, `Custo_ProdTec_Bag`, `Custo_Producao`, `Custo_Produto(_Bag)`,
`Custo_Produto_Comp_Massas`, `Custo_Produto_Condutivo_MaoObra`, `Custo_Produto_Emb_Revisao`,
`Custo_Produto_Fases_Revisao`, `Custo_Produto_MaoObra_Revisao`, `Custo_Produto_Massas_Revisao`,
`Custo_Produto_Observacoes`, `Custo_Produto_Tubetes_Revisao`, `Custo_Produto_Tubo_Revisao`,
`Custo_Produto_Vedante_MaoObra`, `Custo_Rateio_Desp_Setor`, `Custo_Rateio_GIF`,
`Custo_RedistribuicaoGIF`, `Custo_Setor(_Redistribuicao)`, `Custo_Setup_Produto`,
`Custo_SubCategoria_Produto`, `Custo_Tecido_MatSemTubo`, `Custo_Tipo_Fases`, `Custo_Tipo_Produto(_Esp)`,
`Custo_Vedante_MatSemTubo`, `CustoProd_Acabamento`, `CustoProd_Gastos(Gerais)`, `CustoProd_Gerais`,
`CustoProd_Preco` … (e `CurvaABC`/`CustoInv` correlatos).

**Todas com 0 linhas**, exceto `Custo_Parametros` (1 linha — apenas o "cabeçalho" de parâmetros do
módulo: `Sistema_Parametros='SIMCustos'`, `Empresa_Padrao='01'`, rodapés/assinatura; **nenhum custo**).

É o módulo de **custeio industrial** (ficha técnica com massas, tubetes, vedantes, maquinário,
energia, depreciação, GIF/GGF, mão de obra, rateio por setor). Está **integralmente vazio**:
não há apuração de custo industrial persistida nesta base.

## 3. O motor do custo médio fiscal — `SP_MCG_Custo_Medio_DGB`

Assinatura:

```sql
SP_MCG_Custo_Medio_DGB
  @Empresa   char(2),
  @DataFn    smallDateTime,          -- data final do cálculo
  @AS        char(1) = 'S',          -- S=sintético, A=analítico, Q=saldo fiscal
  @Produto   char(6) = '',
  @Cor       char(5) = '',
  @GrupoNatOp char(2) = 'CM'         -- grupo de natureza de operação
```

**Objetivo (do próprio cabeçalho):** "Computar o custo médio pelas NFs E/S do SimLivros"
(criada 02/09/2024, revisada 11/02/2026).

### 3.1 Entradas
- **Saldo/custo inicial:** lido de `Liv_Inventario` + `Liv_Itens_Inventario` na data
  `@DataFn - 1` recuando ao **31/12 do ano anterior** (data retroativa = `01/01` do ano de
  `@DataFn` menos 1 dia). O custo inicial é o `Vr_Unitario` do inventário.
- **Entradas de mercadoria:** `Liv_Entradas` ⋈ `Liv_EntNatOp` ⋈ `Liv_EntProd`, **agrupadas por
  `(Empresa, Data_Entrada, QMP, Produto_Concat)`**, com custo unitário
  `Round(Sum(Valor_Total + Acres_Desc) / Sum(Qtde), 4)`.
  Observação no código: o cálculo foi **redefinido para não descontar PIS/COFINS** e incluir o
  **Imposto de Importação (II)**.
- **Saídas de mercadoria:** `Liv_Saidas` ⋈ `Liv_SaiNatOp` ⋈ `Liv_SaiProd` (baixam a quantidade,
  ao custo médio corrente).
- **Filtro fiscal:** apenas Naturezas de Operação pertencentes ao grupo `@GrupoNatOp`
  (default `'CM'` → **custo de mercadoria**). Ver §4.

### 3.2 Algoritmo (custo médio ponderado móvel)
1. Parte do saldo inicial do inventário.
2. Junta entradas (tipo `'E'`) e saídas (tipo `'S'`) ordenadas por produto/data/tipo.
3. Para cada "concatenado" (produto+cor), itera em `WHILE` mantendo `@Qtde_Mov` e
   `@Vr_Total_Mov` acumulados:
   - entrada: `@Vr_Total_Mov += Qtde * Custo` (ou valor real quando informado);
   - saída: `@Vr_Total_Mov -= Qtde * CustoMedio` (ao custo médio corrente);
   - `Custo_Medio = Round(@Vr_Total_Mov / NULLIF(@Qtde_Mov,0), 4)`;
   - grava `Qtde_Acumulada`, `Vr_Total_Acumulado`, `Custo_Medio`.
4. Ao final, as saídas têm `Custo_Mov` recalculado = `Custo_Medio * Qtde`.

### 3.3 Saídas (`@AS`)
- **`'S'` (sintético, default):** `Produto_Concat`, `Descricao`, `Estoque`, `Custo_Medio_Final`,
  `Vr_Total_CM = Custo_Medio_Final * Estoque`.
- **`'A'` (analítico):** uma linha por movimento (`Id_CM`, `Data_Mov`, `Produto_Concat`, `Descricao`,
  `Estoque_Atual`, `Tipo_Mov`, `Custo_Mov`, `Qtde_Mov`, `Vr_Total_Mov`, `Vr_Estoque_Atual`,
  `Custo_Medio`, `Data_Final`). Exige produto **e** cor informados.
- **`'Q'`:** como o sintético, mas devolve `Saldo_Estoque_Fiscal` + `Custo_Medio_Final`
  (para confrontar com saldos de inventário).

`SP_MCG_Custo_Medio_DGB_Novo` (17 KB) é a variante reescrita/ajustada (mesma família).

## 4. Natureza de operação por grupo — `Fat_Itens_GrupoNatOp`

O motor filtra as NFs pelas Naturezas de Operação do grupo. A tabela de-para é
`Fat_Itens_GrupoNatOp` (`Codigo` × `NatOp` × `Seq`), com 3 grupos nesta base:

| Grupo | Significado | NatOps |
|-------|-------------|--------|
| `CM` | Custo de mercadoria | `1.201`, `1.202`, `2.124`, `2.201`, `2.202`, `3.102`, `5.102`, `6.102`, `6.110`, `6.901`, `6.902`, `6.949` (12) |
| `BN` | Beneficiamento | `5.910`, `5.911`, `6.910`, `6.911` (6 combinações de Seq) |
| `DV` | Devolução/devolvido? | `1.201` (2 Seqs) … (4) |

Se o grupo não existir, o motor usa o fallback `('3.102','5.102','6.102','5.110','6.110')`.
Isso significa que **a definição de "custo" é configurável pela natureza de operação**, não fixa.

## 5. "Concatenado" = Produto(6) + Cor(5)

O grão do custo médio é o **código concatenado** `Produto_Concat`, resolvido por
`Produtos_Cod_Concat_EFD.Codigo_Concatenado` (Empresa + `Cod_Produto` + `Codigo_Concatenado`,
`Tipo_Item`, `Unidade`, `ClassFisc`…). Nesta base: **364 linhas**, 2 empresas.

- A unidade de medida do concatenado (`QMP`) vem de **`Ret_Unidades`** (`Codigo`, `Descricao`,
  `Casas_Decimais`, `QMP` = **P**(peso)/**M**(metros)/**Q**(quantidade), `Unidade_MtsQuadrados`,
  `Aplicar_Fator`). São **5 unidades**: `KG→P`, `M2→M`, `MT→M`, `PC→Q`, `UN→Q`.
- O cadastro `Liv_Diario` (1 linha por empresa) faz a ponte **empresa de venda ↔ empresa de
  produto** (`Empresa_Produtos`): nesta base, todas apontam para `'01'`.

## 6. Os outros caminhos de custo (todos vazios nesta base)

O ERP tem **vários motores de custo paralelos**, por vertical/era. Todos apontam para tabelas
que estão **zeradas** aqui:

| Caminho | Motor | Onde gravaria | Linhas |
|---------|-------|---------------|-------:|
| Custo médio fiscal (mercadoria) | `SP_MCG_Custo_Medio_DGB` | cálculo on-the-fly | — |
| Custo médio por produto/cor | `SP_PCP_CalculaCustoMedioProd` | `PCP_Estoque.CustoMedioAcu/SaldoAcu` | 0 |
| Custo médio via função | `FN_PCP_RetornaCustoProduto` (`M`=médio/`U`=última) | `PCP_Produtos_Precos` | 0 |
| Custo médio CFC (ficha técnica) | `SP_GeraCustoMedio` → `CFC_ProdCustos` | `Cfc_Produtos_CustoMedio` | 0 |
| Último preço / MP têxtil | `Fn_RetornaUltiPrecoCusto` | `Tnt_CustoMP`, `Ret_Lancamentos` | 0 / 1 |
| Custo médio de fios (cru/tinto) | `SP_CustoMedioFios` | `Ret_CxsFios`/`Ret_BaixaCxsFios` | 0 |
| Custo industrial têxtil | `SP_CUSTO_APURA_FIO/TEC/BAG`, `SP_Custo_*` | tabelas `Custo_*` | 0 |
| Custo de importação / CMV | `SP_CMT_CustoMercadoriaVendida` (52 KB), `SP_CMT_*` | cálculo/temporárias | — |
| Depreciação de máquina | `Vw_Custo_Deprec_*` sobre tabelas `Custo_Deprec_*` | `Custo_Deprec_*` | 0 |
| Energia por máquina | `SP_Custo_Energia*` | `Custo_Energia*` | 0 |
| Custo real de beneficiamento | `SP_Tnt_CustoReal_*` | `Tnt_*` | 0 |

`FN_PCP_RetornaCustoProduto` lê o **último** registro de `PCP_Produtos_Precos` (`MAX(ID)`) por
empresa/produto/código de barra, escolhendo `CustoMedio` (`@Tipo_Custo='M'`) ou `Preco` (`'U'`).

## 7. O que **é** custo gravado nesta base

1. **`Produtos_Tecidos`** — custo **estático por produto de tecido**, em 4 variantes:
   `Custo_Cru`, `Custo_Estampado`, `Custo_Remessa`, `Custo_Outros` (+ as variantes `*Inv`).
   Preenchidos em **16/15/21/15** dos **62** produtos. São custos cadastrais (referência), não
   apurados. Ex.: produto `000010` tem `Custo_Cru=Estampado=Remessa=Outros=3,82`.
2. **`Lv3_SdoEst_Fechamento`** — **fechamento de estoque do Modelo 3** (Bloco K), 4 807 linhas,
   de **31/05/2019 a 31/08/2026**, empresa `4`, 18 produtos, Σ Quantidade ≈ 39,5 mi, 3 335
   marcadas `Entregue='S'`. Colunas: `Id`, `IdEmpresa`, `Produto`, `Concatenado`,
   `CodigoCliente`, `IndicadorPosse`, `Data`, `Quantidade`, `Cod_Liv_Inventario`,
   `Cod_Liv_Item_Inventario`, `Entregue`. É a **posição de estoque fiscal de terceiros** usada
   na valorização/escrituração — não um "custo" em si.
3. **`Cte_Parametros`** — parâmetros do módulo têxtil com **flags de custo**, e a maioria
   **desligada**: `usa_CustoMedio='N'`, `Custo_Cor='N'`, `Usar_Custo_Entrada_Tecido='N'`,
   `Usar_Custo_FichaTransf='N'`, `Usar_Custo_Quebra='N'`, `ConsiderarFios='N'`,
   `Usar_Custo_FT_Detalhada='N'`. `Empresa_Local='13'`, `Cor_Cru='00000'`.

Contudo, mesmo os campos de "custo" do cadastro de produto e da peça estão **zerados**:
`Produtos.CustoBruto/PercentualDeducaoCusto/CustoLiquido` = 0 (64 produtos) e
`Cte_Peca.Custo_Unitario` = 0 (**297 044 peças**). Logo, **não confiar nesses campos** para
relatórios de valorização nesta base.

## 8. Modelo 3 / valorização de estoque (`LV3_*`)

Há **30 tabelas `LV3_*`/`Lv3_*`** ligadas ao **registro fiscal de estoque (Bloco K)**:
`Lv3_SdoEst_Fechamento` (4 807, em uso), `Lv3EstoqueFechamentoK280(_Entregue)`,
`LV3_ProcessamentoMod3_Log(_Det)`, `LV3_ProcessamentoHist`, `Lv3_ProceduresProcessamento`,
`LV3_LinkMovEstoque`/`_LinkFT`/`_LinkOPF(NV)`, `LV3_ParamSpValorizacao(_Filtro)`,
`LV3_ParamVlrArbitrado`, `LV3_Prod_ValorInv(_Log/_Doc)`, `LV3_Prod_ValorImpostos`,
`LV3_SaldoIntegraFat(_Notas)`, `Lv3_ParamExclusaoRelModelo3`, `lv3_CadastroK220/K270`,
`Lv3_Produto_Similaridade`, `Lv3_ProdNaoPassaTravaFaturamento`, `lv3_OrigemCorrecaoApontamento`,
`Lv3EstoqueFechamentoEntregue`, `Lv3_Layouts_Implantacao`, `LV3ClientesSemNotaDeCobertura`.

Todas as tabelas de **valorização** (`LV3_Prod_ValorInv*`, `LV3_ParamSpValorizacao`,
`LV3_SaldoIntegraFat*`, `LV3_Prod_ValorImpostos`) estão **vazias** — só o **fechamento de saldo**
(`Lv3_SdoEst_Fechamento`) é usado. Conclusão: a valorização de estoque fiscal está implementada
mas **não alimentada** (custeio desligado).

## 9. Views de custo

- **Custo médio de estoque:** `vw_PCP_CustoMedio` = `Avg(PCP_Estoque.Preco)` por
  Empresa+Código de barra, onde `PCP_Historicos.Custo_Medio=1` e `PCP_Estoque.ES=1` (vazia).
- **Depreciação:** `Vw_Custo_Depreciacao` (`Avg(Custo_Depreciacao)` por Empresa/Setor/Grupo),
  `Vw_Custo_Deprec_Custo/_Indice/_Maq/_ProdMedia`, `VW_Custo_GrupoMaquinas`, `vw_Custo_Maquina(_Redistribuicao)`,
  `VW_Custo_Maquinas`, `Vw_Custo_ProdSetor`.
- **Custo de produto / formação de preço:** `VW_Custo_Produto_FormPreco`, `VW_Custo_Produto_PP_Perc`,
  `VW_CTE_Acessorios_FT_QtdeCusto`, `Vw_Itens_Custo_FioTinto`.
- **Simulação de custo (ficha técnica têxtil):** `VW_CTE_SimulacaoCusto` (+ `_Fios`, `_TotMP`, `_VrVenda`),
  que cruza `CTE_FT_SimulacaoCusto` × `CTE_Sit_FT_SimulacaoCusto` × `VW_CTE_SimulacaoCusto_VrVenda`,
  trazendo `Vr_MP`, `Vr_CP` (custo de produção), `Vr_CV`, `Vr_Quebra`, ICMS, comissão, PIS/PASEP e
  o custo da tinturaria (`SSC.Vr_Tinturaria`).
- **CMV/administrativo:** `SP_CMT_*`, `VW_SCT_FPVM/FPVT_CustoAdmProd`, `VW_Tnt_Processo_Custo`.

## 10. Superfície de procedures e funções de custo (catálogo)

O prefixo de busca é amplo; as principais famílias (todas **read-only para a API**):

- **Custo médio fiscal:** `SP_MCG_Custo_Medio_DGB`, `_Novo`, `SP_MCG_Referencia_Cruzada`.
- **PCP/loja:** `SP_PCP_CalculaCustoMedioProd(_Precos)`, `FN_PCP_RetornaCustoProduto`,
  `SP_PCP_Ficha_Custo_FT`, `SP_PCP_RelCustoSimplificado`.
- **Importação/CMV:** `SP_CMT_CustoMercadoriaVendida`, `SP_CMT_FechamentoCusto`,
  `SP_CMT_AtualizaCusto_CaixaFios`, `SP_CMT_CustoImportacaoPainel(_Aviso/AFRMM)`.
- **Industrial têxtil:** `SP_CUSTO_APURA_FIO/TEC/BAG`, `SP_CUSTO_FIO_*`, `SP_CUSTO_TECIDO_TUBOS_REVISAO`,
  `SP_Custo_{Processo,Materia,Energia,Teorico,Rateio_GIF,ImportaFT*,Atualiza_PercSetor,…}`.
- **Ficha técnica/CFC:** `CFC_FichaTec_Custo(_Grade)`, `CFC_ProdCustos`, `Sp_Cfc_CustoTecidoUnificado`,
  `SP_Cfc_CustoFTAcessorios`, `SP_GeraCustoMedio`.
- **Fios / fio tinto:** `SP_CTE_Gera/Recarrega/Salva_Custo_FioTinto`, `SP_CustoMedioFios`,
  `sp_Fio_CustoCaixa_*`.
- **Tinturaria/TNT:** `SP_Tnt_CustoReal_Calc/Quimicos`, `SP_Tnt_Cons_CustoRealBenef`, `SP_Tnt_Atualiza_CustoMaq`.
- **Custo real/administrativo:** `FN_SCT_CustoADMProducao`, `FN_SCT_CustoTotalFio`,
  `SP_SCT_Custo*`, `SP_Custo_Prod_NFFaccionista`, `SP_Rel_Custo_Faccionista`.
- **Modelo 3:** `SP_Lv3_RelCustoEstoque`.
- **Funções:** `Fn_RetornaUltiPrecoCusto`, `FN_PCP_RetornaCustoProduto`, `FN_SCT_*`.

## 11. Implicações para a API / Neon

1. **Não há tabela de custo para ler.** Expor "custo médio" exige **reimplementar o algoritmo**
   de `SP_MCG_Custo_Medio_DGB` no ETL (Python) — é um **custo médio ponderado móvel** sobre o
   livro fiscal (`Liv_Entradas`/`Liv_Saidas`) filtrado por grupo de NatOp (`CM`), ancorado no
   inventário (`Liv_Inventario`) do fim do ano anterior.
2. **Grão = Produto_Concat (produto+cor).** No Neon, modelar `custo_medio(empresa, produto_concat, data,
   qtde, custo_medio, valor_total)` e materializar as **três** saídas do motor (`S`/`A`/`Q`)
   como views/marts.
3. **A definição de "custo" é configurável** (`Fat_Itens_GrupoNatOp`): levar a tabela de grupos
   para o Neon (snapshot) e calcular por grupo.
4. **QMP** (`Ret_Unidades.QMP`) precisa ser transportado para comparar quantidades (peso/metro/peça).
5. **Campos de custo do cadastro estão zerados** (`Produtos.Custo*`, `Cte_Peca.Custo_Unitario`):
   a API **não deve** depender deles; se expostos, sinalizar que não estão em uso.
6. **`Produtos_Tecidos.Custo_*`** é o único custo gravado — útil como *fallback* estático por
   produto, mas é cadastral (pode estar desatualizado).
7. **Modelo 3**: `Lv3_SdoEst_Fechamento` é dado fiscal real (posição de estoque de terceiros);
   bom candidato a mart fiscal, mas não é valorização.
8. **Custeio industrial (`Custo_*`) está desligado** nesta base: não vale a pena portar as 67
   tabelas agora; documentar como "não usado" e revisitar se outro cliente as usar.

## 12. Gotchas encontrados

- `Custo_Parametros` e `Cte_Parametros` **não são** "linha de custo": são o cabeçalho de
  parâmetros do módulo (rodapé/assinatura). Não usar como fonte de dados.
- `SP_MCG_Custo_Medio_DGB` usa `#Tmp_CM_Aux` com `WHILE` + `UPDATE` por concatenado: em bases
  grandes é **caro**; o próprio código adicionou **PK em `#Tmp_CM`** (11/02/2026) para acelerar.
- A busca do custo inicial depende de `Liv_Inventario.Data = 31/12` do ano anterior — **se não
  houver inventário nessa data, o custo inicial é 0** e o médio começa "do zero" pela 1ª entrada.
- O custo de entrada ignora PIS/COFINS mas **inclui II** (comentário explícito no código).
- Tabelas `PCP_*`/`Cfc_*`/`Tnt_*` de custo existem e têm procs ativas, mas os dados estão zerados —
  o `WHILE` de `SP_PCP_CalculaCustoMedioProd` **atualiza** `PCP_Estoque` (é escrita; a API legada
  não deve acioná-la em produção).

## 13. Próximos passos

- **Estudo 37 — `Ret_*`** (retorno de terceiros / tecelagem / facção): `Ret_CxsFios`,
  `Ret_Lancamentos`, `Ret_Precos`, `Ret_Aviso_*`, `Ret_Unidades` (já tocada aqui como QMP) e a
  relação com tinturaria/faccionistas.
- Depois: COMEX, Compras, `Rpt_*`, `Usua_*`, infra.
- Na implementação do custo médio no Neon: validar a reimplementação contra o resultado real
  de `SP_MCG_Custo_Medio_DGB` para 2–3 produtos/cores (empresa de produto `'01'`).
