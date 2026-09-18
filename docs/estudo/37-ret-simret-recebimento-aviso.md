# Estudo 37 — SIMRet (`Ret_*`): recebimento, avisos, razão e cadastros têxteis

Aprofundamento do módulo **`Ret_*`**. Consolida e **corrige** o que apareceu nos
[Estudos 10](./10-compras-e-recebimento.md), [20](./20-importacao-comex-sim-carteira.md),
[23](./23-financeiro-contabil-custo.md), [24](./24-enderecamento-gavetas-wms-comex.md),
[26](./26-mapa-modulos-microdata.md), [27](./27-cadastros-base-profundo.md),
[34](./34-estoque-cte-saldos-movimentos.md) e [36](./36-custos-mcg-custo-medio.md).
Levantamento por `SELECT` somente leitura.

> **Retificação de entendimento.** Nos estudos anteriores o prefixo `Ret_` foi descrito
> sumariamente como "retorno de terceiros/tecelagem (facção)" e `Ret_Aviso_*` como "COMEX".
> O nome real do módulo é **SIMRet** (`Ret_Parametros.Sistema_Parametros = 'SIMRet'`). Ele é o
> **módulo de retaguarda de estoque/entradas do ERP têxtil** — **aviso de recebimento**,
> **razão/movimentação de estoque de MP**, **pedidos de compra**, **listas de preço**, **caixas
> de fios** e os **cadastros de classificação têxtil** (seção/grupo/subgrupo/linha). A facção é
> apenas **um** dos temas dentro dele.

## 1. Síntese

São **103 tabelas** com prefixo `Ret` (96 `Ret_*`/`ret_*` + 7 utilitárias sem `_`), mas só
**23 têm dados** — e dessas, apenas as do **aviso de recebimento** têm volume relevante. O
resto são **cadastros de configuração** ou **vestígios** de uma era em que a movimentação de
estoque vivia em `Ret_Lancamentos`/`Ret_Saldos`/`Ret_NFEntrada`, hoje substituída por
`NF_Entradas` ([Estudo 31](./31-contas-a-pagar-pag.md)), `CTE_*`
([Estudo 34](./34-estoque-cte-saldos-movimentos.md)) e `Liv_*`
([Estudo 35](./35-fiscal-sped-liv-fig-efd.md)).

| Papel | Objeto | Linhas | Estado |
|-------|--------|-------:|--------|
| **Aviso de recebimento** (cabeçalho) | `Ret_Aviso_Recebimento` | **218** | **Em uso** (COMEX) |
| Itens do aviso de recebimento | `Ret_Aviso_ItensRecebimento` | **2 083** | **Em uso** |
| Atendimento do pedido de compra pelo aviso | `Ret_Aviso_Itens_Pedido_Atend` | **2 083** | **Em uso** |
| Cabeçalho de NF de entrada (legado) | `Ret_NFEntrada` | 1 | Residual |
| Itens de NF de entrada (legado) | `Ret_ItensNFEntrada` | 1 | Residual |
| Lançamentos de estoque (legado) | `Ret_Lancamentos` | 1 | Residual |
| Saldo mensal por produto/tipo (legado) | `Ret_Saldos` | 1 | Residual |
| Tabela de preço | `Ret_Tabelas` | 1 | Cadastro |
| Help do módulo | `Ret_Help` | 38 | Cadastro |
| Tributação (alíquotas ICMS) | `Ret_Tributacoes` | 11 | Cadastro |
| Históricos e tipos de histórico | `Ret_Historicos` / `Ret_Tipo_Historico` | 9 / 9 | Cadastro |
| Moedas e cotação diária | `Ret_Moedas` / `Ret_Moedas_Diario` | 2 / 9 | Cadastro |
| Unidades (com `QMP`) | `Ret_Unidades` | 5 | **Em uso** (via cost/estoque) |
| Classificação: seção/grupo/subgrupo/linha | `Ret_Secao` (4) / `Ret_Grupos` (5) / `Ret_SubGrupos` (5) / `Ret_Linha` (1) | 15 | Cadastro |
| Parâmetros por empresa | `Ret_ParamEmp` (4) / `Ret_ParamEmp_Ext` (2) / `Ret_Parametros` (1) | 7 | **Em uso** |
| Encargos de compra | `Ret_Encargos` | 3 | Cadastro |
| **Demais ~80 tabelas** | avisos de peça, caixas de fios/índigos, pedido de compra, inventário, trocas, devolução de facção, volumes, preços, rateio de importação… | **0** | **Vazias** |

## 2. Aviso de Recebimento — `Ret_Aviso_*` (o núcleo vivo)

É um **documento de entrada** que precede/embasa o recebimento físico, com forte pegada de
**importação**. Nesta base: **218 avisos**, de **06/07/2021 a 14/09/2026**, de **10
fornecedores** (o principal, `00146` = uma *trading* no exterior), **214 NFs**, todos
`Tipo='01'`, `Revisado='N'`, `StatusColeta='F'`, moeda `02` (dólar).

**`Ret_Aviso_Recebimento` (cabeçalho)** — chave `Empresa + Aviso`:
- Identificação: `Tipo_Fornecedor`, `Fornecedor`, `Nr_NFE`, `Serie`, `Chave_Acesso`,
  `Empresa_Fat`, `Facionista`.
- Datas: `Data_Receb`, `Data_Hora_Receb`, `Dat_Recebimento`, `Data_Lancamento`,
  `DataRegistroDI`, `Data_Cambio`, `Data_Cambio_Atualizacao`.
- Importação/COMEX: `Codigo_Moeda`, `VrAFRMM`, `VrATAERO`, `Vr_Frete`, `Vr_Acres`,
  `Vr_Desconto`, `porc_Desconto`, `Processo`, `MoedaVrAduaneiro`, `IdLocalDesembaraco`,
  `Path_XML`, `Arquivo_XML`.
- Estado: `Tipo`, `Status`, `StatusColeta`, `Revisado`, `Obs`, `Historico`, `Operador`.

**`Ret_Aviso_ItensRecebimento` (itens)** — chave `Empresa + Aviso + Item_Aviso`:
- Produto/dimensão: `Emp_Prod`, `Produto`, `Codigo_Concatenado`, `produtoReferenciado`,
  `Cor`, `Desenho`, `Variante`, `Situacao`, `Categoria`, `Grade`/`Grade_Tam`, `Embalagem`.
- QMP e medidas: **`QMP='M'` (metros) em 100%** dos itens, com `Qtde`, `Metros`, `Peso`,
  `Qtde_Rolos`, `Peso_Bruto`.
- Valores: `Vr_Unitario`, `Vr_Unitario2`, `Vr_Total`, `Vr_UnitPedido`, `Vr_Unitario_Compra`,
  `Vr_Moeda_Estrangeira`, `Vr_AcresDesc`, `Vr_Desconto`, `porc_Desconto`, `Vr_Frete`.
- Tributos: `Porc_IPI`, `Porc_ICMS`, `ICMS_Subst`, `Aliq_Reducao`, `Porc_PIS`, `Porc_COFINS`,
  `Porc_Encargos`, `Encargos_Financeiros`.
- Coleta/estoque: `Nr_Lancamento`, `StatusColeta`, `ID_EstoquePCP`, `Fk_PCP_Acondicionamento`.

Totais: 217 avisos com itens, 17 produtos, Σ Qtde ≈ **17,5 mi** (metros), Σ `Vr_Total` ≈
**R$ 11,1 mi**. Todos com `Categoria='01'` e `Situacao='001'` (classificação têxtil padrão).

**`Ret_Aviso_Itens_Pedido_Atend` (ponte aviso ↔ pedido de compra)** — chave
`Empresa + Aviso + Item_Aviso`:
- `Pedido`, `Item_Pedido` (pedido de compra atendido), `ID_Ent`,
  `Qtde_Atend`, `Qtde_Acerto`, `Qtde_Atend_Compra`, `Qtde_Acerto_Compra`.
- 2 083 linhas, 217 avisos, **217 pedidos** (1:1 aviso↔pedido), Σ `Qtde_Atend` ≈ 17,5 mi.
- A view **`vw_Ret_Aviso_Itens_Pedido_Atend`** (→ `_Ant`) calcula `saldo`/`saldo_compra`
  = `Qtde - Qtde_Anterior - (Qtde_Atend + Qtde_Acerto)`.
- `Ret_Aviso_Itens_Pedido_Atend` tem trigger `TG_INSUPDDEL_...`; `Ret_Aviso_Recebimento`
  tem trigger de `Data_Lancamento`; `Ret_Aviso_ItensRecebimento` tem 5 triggers (inclusive
  `TG_CMT_INS_ATUALIZA_CUSTO_FIO` e `TG_RET_Del_AvisoEstoquePCP`).

**Relevância cross-módulo:** `Ret_Aviso_Recebimento` é referenciada por dezenas de objetos,
notadamente o **custo de importação** `SP_CMT_CustoImportacaoPainel(_Aviso/AFRMM)`,
`SP_CMT_CustoMercadoriaVendida`, `SP_CMT_GeraEstoque(FAC)`, **qualidade/lote** `SP_SIC_*`/`vw_SIC_Lote_Inspecao_*`,
`SP_PCP_CalculaCustoMedioProdutos_Precos` e `SP_Liv_Gera_EConsiste`. Ou seja, o aviso de
recebimento é a **espinha dorsal da entrada de importação** (ver [Estudo 20](./20-importacao-comex-sim-carteira.md)/[24](./24-enderecamento-gavetas-wms-comex.md)).

## 3. Razão/movimentação legada — resíduo

O conjunto abaixo foi, no passado, o **livro de movimentação de estoque** (mercadoria),
com partidas de entrada/saída e saldo por mês — hoje **ocioso**:

- **`Ret_Lancamentos`** (1) — `Empresa`, `Nr_Lancamento`, `Produto`, `Historico`, `Documento`,
  `Qtde`, `Preco`, `Total`, `Data_Lancamento`, `MesAno`, **`E_S`** (E/S), `Lote`, `Destino`,
  `Cambio`, `Bloqueado`, `Nota_Fiscal`, `Aviso`/`ItemAviso`, `produtoReferenciado`.
  A linha existente é de **2019-07-29** (empresa `13`, produto `000015`, E).
- **`Ret_Saldos`** (1) — `Produto`, `MesAno`, `Tipo_Historico`, `Cambio`, `Entrada`,
  `Valor_Entrada`, `Saida`, `Valor_Saida` (mesma data, empresa `13`).
- **`Ret_NFEntrada`** (1) / **`Ret_ItensNFEntrada`** (1) — cabeçalho/item de NF de entrada
  **legado**, com tributos, `Retorno_Terceiros`, `EnviaFac`, `Apropriacao_Direta`,
  `Lancar_Pagar`, `Devolucao_Fios`, `Tipo_Comercializacao`, `idFT`. Superado por
  `NF_Entradas`/`NFE_Parcelas` ([Estudo 31](./31-contas-a-pagar-pag.md)).

O **mapa de históricos** permanece como cadastro (útil para decodificar dados antigos):

| `Ret_Historicos` | Descrição | `Tipo_Historico` |
|---|---|---|
| 000 | COMPRAS | 00 (influi preço) |
| 001 | TRANSFERENCIA | 01 |
| 002 | BONIFICACOES | 02 |
| 003 | ACERTOS | 03 |
| 004 | DEVOLUCOES | 04 |
| 005 | VENDAS | 05 (não influi) |
| 006 | OUTROS MOVTOS | 06 |
| 007 | RETIRADA PARA PRODUCAO | 07 (não influi) |
| 008 | RETORNO DE FACCIONISTA | 06 |

`Ret_Tipo_Historico` (9) tem `Influi_Preco` (`S` para compras/transferência/bonificação/
acerto/devolução/outros; `N` para vendas/retiradas/suprimentos). Views de saldo legado:
`VW_Ret_Lancamentos_SaldoProduto` (Σ entrada − Σ saída por produto) e
`VW_Ret_Lancamentos_Lotes_SaldoLotes`.

## 4. Cadastros de classificação têxtil

Hierarquia de produto do SIMRet (usada em telas e relatórios antigos):

- **`Ret_Secao`** (4): `001 GERAL`, `002 TECIDOS`, `003 FIOS`, `004 FIBRAS`
  (`Tipo_Produto` 0–3).
- **`Ret_Grupos`** (5): por seção — ex. seção `003`/FIOS tem grupo `001` e `050 ALGODAO`.
- **`Ret_SubGrupos`** (5): `Secao+Grupo+Codigo` — ex. `003/050/051 = 16/1` (título de fio);
  tem `Fornecedor`, `Inativo`, `FatorConversao`, `AdicionarAFormula`.
- **`Ret_Linha`** (1): `Codigo`, `Descricao`, `Qual_Preco`, `Artigo`, `Tear` (linha de produção).

## 5. Cadastros de apoio

- **`Ret_Unidades`** (5) — unidades com **`QMP`** (`P`/`M`/`Q`), `Casas_Decimais`,
  `Unidade_MtsQuadrados`, `Aplicar_Fator`, `Unidade_ABNT`: `KG→P`, `M2→M`, `MT→M`, `PC→Q`,
  `UN→Q`. **Referenciada por custo médio** ([Estudo 36](./36-custos-mcg-custo-medio.md)) e por
  views de saldo de estoque ([Estudo 34](./34-estoque-cte-saldos-movimentos.md)).
- **`Ret_Tributacoes`** (11) — CST/alíquota de ICMS: `ISENTA`, `7%`, `12%`, `18%`, `25%`,
  `DIFERIDO`, `SUBSTITUICAO`, `SUSPENSAO`, `NAO TRIBUTADA`, `18% c/ redução 33,33%`, `4%`
  (com `Cod_Impressora`, `Totalizador_SPED`, `Aliq_ImpIfiscal`).
- **`Ret_Encargos`** (3): `INFLACAO`, `PIS`, `COFINS`.
- **`Ret_Moedas`** (2): `01 Real / 02 DÓLAR` (+ `Ret_Moedas_Diario` com cotações — 9 linhas).
- **`Ret_Tabelas`** (1) — índices/comissões 1..5 da tabela de preço `000` (zerados).
- **`Ret_Help`** (38) — tópicos de ajuda do módulo.

## 6. Parâmetros (`Ret_Parametros`, `Ret_ParamEmp`, `Ret_ParamEmp_Ext`)

- **`Ret_Parametros`** (1) — parâmetros **globais do SIMRet**. Entre centenas de flags,
  destacam-se: `Usar_Aviso_Recebimento='N'`, `Historico_Avisos='000'`, `Preco_Medio_Diario='N'`,
  `Usar_Cambio` (controle de câmbio), `Ativar_MP_Fiacao='N'`, `Informar_Cones='N'`,
  `Ratear_IPI='S'`, `Ratear_AcresDesc='S'`, `Usar_Formacao_Preco_Tabela='S'`,
  `Empresa_CodProdutos='01'`, `Hist_Inventario='003'`.
- **`Ret_ParamEmp`** (4: empresas `01`, `02`, `13`, `14`) — parâmetros **por empresa**:
  `Usar_Tabela`, `Usar_Desmembramento`, `Usar_Montagens`, `Usar_Tecidos`, `Tabela_Atual`,
  `Tipo_Historico_Venda='05'`, `Historico_Compras='000'`, `Integra_Pagar='S'`,
  `Integra_Livros`, `Ultimo_Lancto`, `Ult_Caixa`, `Ult_Aviso`, `Ult_RomTransf`,
  `CasasDecimais_Unitario_E`, `Usar_MPAux`, `Ramo_Fio` (empresa `13` = `FIACAO`),
  `Ramo_Fibra`, `Ramo_MPAux`, `Recalc_Preco_impXML`, `Usar_Qualidade`.
- **`Ret_ParamEmp_Ext`** (2) — extensão: `Usar_PedCompra`, `Gerar_Pedido`,
  `Usar_Tabela_Compra`, `Fornecedor_PedCompra`, `Empresa_Central`, `Recebimento_Qtde_Dias`.

A empresa **`13`** (têxtil/fiação) é a que usa o módulo de fato (`Ramo_Fio='FIACAO'`,
`Usar_Tecidos='S'`, `Ult_Aviso=292`).

## 7. Caixas de fios, pedido de compra, inventário, trocas e volumes (vazios)

- **Caixas de fios:** `Ret_CxsFios`, `Ret_Cones_CxsFios`, `Ret_BaixaCxsFios`,
  `Ret_Gaveta_CxsFios`, `Ret_ExcessaoCFOPCaixaFio`, `Ret_CxsFios_AuxGera`, `Ret_Itens_Lote`,
  `Ret_RmCxsFios`, `ret_RmCxsFios` — **0 linhas** (embora haja views de saldo
  `Ret_CxsFios_Saldo`, `VW_Ret_ConeCxsFios_Saldo` e triggers). O custo médio de fios
  (`SP_CustoMedioFios`) lê `Ret_CxsFios`/`Ret_BaixaCxsFios`, portanto **também vazio**
  ([Estudo 36](./36-custos-mcg-custo-medio.md)).
- **Pedido de compra (SC):** `Ret_PedCompra`, `Ret_ItensPedCompra`, `Ret_PedCompra_NFE`,
  `Ret_PedCompra_Trocas`, `Ret_PedCompra_Bonificacao`, `Ret_Parcela_PedCompra` — 0.
  Procs `Ret_EnviaPedidoCompra`/`Ret_EnviaUmPedidoCompra`/`Ret_EnviaStatusPedCompra`
  (integração) existem, mas `Ret_ParamEmp_Ext. Usar_PedCompra='N'`.
- **Inventário:** `Ret_Inventario`, `Ret_Inventario_Log`, `Ret_PalmInventar` — 0
  (o inventário real é `Liv_Inventario`, [Estudo 34](./34-estoque-cte-saldos-movimentos.md)).
- **Trocas/devoluções:** `Ret_Movimentos_Troca`, `Ret_Digita_Troca(_Log)`, `Ret_Saida_Troca`,
  `Ret_Estoque_Troca`, `Ret_DevolucaoFaccao`, `Ret_Facionista_Fornec`, `Ret_Fabricantes` — 0.
- **Volumes/fardos:** `retVolumes`, `retVolumeRomaneio`, `retVolumeBaixas`,
  `retParam*Volumes` — 0 (ver [Estudo 24](./24-enderecamento-gavetas-wms-comex.md)).
- **Preços:** `Ret_Precos`, `Ret_Precos_Pdv`, `Ret_Linha_Precos_Lucro`,
  `Ret_Tabela_ComGrupoVen`, `Ret_Promocao` — 0. A tabela de preço viva é
  `CAR_TABELA_PRECO*` ([Estudo 17](./17-cadastros-comerciais.md)).
- **Importação:** `Ret_Rateio_Importacao`, `Ret_Importacao_Encargos`,
  `Ret_NatOPComerc_ImportNF`, `Ret_Imposto_NFE`, `Ret_NFComplementar` — 0.
- **MPAux/auxiliares:** `Ret_MP_Auxiliares`, `Ret_BaixaMP_Auxiliares`,
  `Ret_prodFaccaoSecGrSbgr`, `Ret_paramProdRef*`, `Ret_Depositos`, `Ret_Enderecos`,
  `Ret_Fechamento_Mensal`, `Ret_Compradores`, `Ret_Balanca`, `Ret_EtqProdutos/Secao`,
  `Ret_Indices`/`Ret_Itens_Indices`, `Ret_Zebra`/`Ret_S_Zebra`, `Ret_TiposNaoMovimentaveis`,
  `Ret_EnviarEmail`/`Ret_EnvioEmail_Documentos` — 0.

## 8. Views

14 views `Ret*`, das quais as relevantes:

- **`vw_Ret_Aviso_Itens_Pedido_Atend`** / **`_Ant`** — saldo pendente de pedido de compra por
  item de aviso (usada na conferência de recebimento).
- **`VW_Ret_Lancamentos_SaldoProduto`** / **`VW_Ret_Lancamentos_Lotes_SaldoLotes`** — saldo
  legado por produto/lote.
- **`Ret_CxsFios_Saldo`** / **`Ret_CxsFios_SaldoRe`** / **`VW_Ret_ConeCxsFios_Saldo`** —
  saldo de caixas/índigos de fios.
- **`vw_Ret_SomaValoresItensDocumento`** / **`vw_Ret_VerificaValoresDocumento`** — conferência
  de valores de itens.
- `vw_ret_CaixaProdRef`, `VW_Ret_EtqAvisoLote`, `vw_Ret_ItensProdLoteCaixa`,
  `Vw_Ret_ItensRmCxsFios`, `Vw_Ret_ProdContraTipo`.

## 9. Procedures e triggers

**Procedures `Ret_*`** (≈43) — em geral **relatórios** e **integração**:
- Relatórios: `Ret_RelRazao(_Resumo/_SaldoInicial)`, `Ret_RelLancamentos`, `Ret_RelMovtoEstoque`,
  `Ret_RelInventario`, `Ret_RelAtendFornec(_Gerencial/_Sintetico)`, `Ret_RelUltimasCompras`,
  `Ret_RelMaxMin`, `Ret_RelMargemBruta(_Resumo)`, `Ret_RelListPrecos(_Custos)`,
  `Ret_RelPrecosAlterados`, `Ret_RelProdutos`, `Ret_RelCompValores`, `Ret_RelSemMov`,
  `Ret_RelSaldoSemVenda`, `Ret_RelPedCompra`, `Ret_RelBlocoEstoquePedido`,
  `Ret_CFC_RelLancamentos(2)`, `Ret_RelDataUltimaCompra`, `Ret_RelConsulta`,
  `Ret_RelPlanilha`, `Ret_RelRegInventario`, `Ret_RelDataUltimaCompra`, `RetVSaldos(2)`,
  `RetVCustos(2)`, `Ret_Compara_Inventario`.
- Escrita/processo: `Ret_Lanca_Entradas` (11 KB — lança entradas), `Ret_GeraInventario`,
  `Ret_AtualizaPreco`, `Ret_ExcluiMovtoProduto`, `Ret_ExcluiProduto`, `Ret_maior_lancto`,
  `Ret_Maior_Lancto_Recau`, `Ret_PalmControle`/`Ret_PalmExporta` (coletor),
  `Ret_EnviaPedidoCompra`/`Ret_EnviaUmPedidoCompra`/`Ret_EnviaStatusPedCompra`.

**Triggers:** ~65 triggers sobre tabelas `Ret_*` (a maioria em `Ret_Lancamentos`,
`Ret_CxsFios`, `Ret_BaixaCxsFios`, `Ret_ItensNFEntrada`, `Ret_Aviso*`) — vestígios da época em
que essas tabelas eram o centro do estoque. **A API read-only não dispara nada disso**, mas é
importante saber que existem caso se pense em escrita.

## 10. Implicações para a API / Neon

1. **`Ret_*` não é "facção"; é o SIMRet** (retaguarda de entradas/estoque). Ao documentar/portar,
   tratar o prefixo pelo módulo real.
2. **O único dado vivo e relevante é o Aviso de Recebimento** (`Ret_Aviso_Recebimento` +
   `_ItensRecebimento` + `_Itens_Pedido_Atend`): é a **entrada de importação** amarrada ao
   pedido de compra. Deve virar um mart próprio (`recebimento_aviso` + itens + atendimento).
3. **Cuidado com a armadilha de completude:** existem **muitas** tabelas `Ret_*` com nomes
   promissores (preços, pedido de compra, inventário, caixas de fios) que estão **vazias**.
   Não construir features sobre elas sem confirmar uso (`COUNT`).
4. **Cadastros a migrar como domínio:** `Ret_Unidades` (QMP — já exigido pelo custo/estoque),
   `Ret_Tributacoes` (alíquotas ICMS), `Ret_Historicos`/`Ret_Tipo_Historico`, `Ret_Moedas(_Diario)`,
   `Ret_Secao`/`Ret_Grupos`/`Ret_SubGrupos`/`Ret_Linha`.
5. **Parâmetros (`Ret_ParamEmp*`)** são por empresa e definem o comportamento do módulo
   (ex.: `Ramo_Fio='FIACAO'` na empresa 13, `Integra_Pagar='S'`); snapshot útil, mas revisar
   sensibilidade antes de expor.
6. **Não portar o razão legado** (`Ret_Lancamentos`/`Ret_Saldos`/`Ret_NFEntrada`): os dados
   oficiais hoje estão em `NF_Entradas` + `Liv_*` + `CTE_*`.

## 11. Gotchas encontrados

- **Contagem de tabelas varia com o padrão**: `Ret_*`/`ret_*` = 96; com as 7 utilitárias sem
  `_` (`retVolumes`, `retParam*Volumes`…) chega-se a **103**. A maioria vazia.
- `Ret_Aviso_Recebimento.Status` é **quase todo `NULL`** (só 2 avisos com `Status='A'`) —
  **não usar `Status`** como estado do aviso; o sinal vivo é `Revisado`/`StatusColeta`.
- `Ret_Aviso_ItensRecebimento.QMP` está **100% `'M'`** nesta base (metros) — não assumir peso.
- `Ret_Aviso_Itens_Pedido_Atend.ID_Ent` tem só **3 valores** (1..3): não é o documento de
  entrada, é um identificador interno do atendimento.
- O `Facionista` do aviso está **sempre vazio** aqui (`SUM=0`): nesta base o aviso é
  **importação**, não facção.
- O link direto `Ret_Aviso_Recebimento → NF_Entradas` não fecha por `Tipo_Fornecedor`
  (a coluna não existe em `NF_Entradas`); a amarração com o recebimento definitivo é feita via
  `Aviso_Recebimento`/`Empresa_Aviso` em `Ret_NFEntrada` e nos processos `SP_CMT_*`.
- `Ret_Parametros` é um "super-cadastro" de ~85 colunas; **não** é um registro de dados.

## 12. Próximos passos

- Próximo módulo do mapa ([Estudo 26](./26-mapa-modulos-microdata.md)): **COMEX** (em parte já
  coberto por `Ret_Aviso_*` + `Fat_XML_DI`/`Liv_EntProd_DI`), depois **Compras**, `Rpt_*`,
  `Usua_*` e infra (`SIS_*`/`LOG_*`).
- No ETL: criar o mart de **aviso de recebimento** e mapear `Clientes_Principal.Codigo_Cliente` ↔
  `Razao_Nome_Cliente` (fornecedor `00146` = *trading* exterior) para relatórios de importação.
