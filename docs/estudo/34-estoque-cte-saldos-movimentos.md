# Estudo 34 — Estoque (`CTE_*`, saldos, gavetas, transferências e inventário)

Aprofundamento do **estoque** do ERP. Consolida e fecha o que já apareceu nos
[Estudos 02](./02-dominio-estoque-pecas.md), [09](./09-estoque-pecas-livros.md),
[19](./19-estoque-pecas-cte-peca.md), [24](./24-enderecamento-gavetas-wms-comex.md) e
[25](./25-expedicao-despacho-separacao.md): aqui o foco é a **posição de estoque** (peça em
aberto), o **snapshot de saldos**, os **endereços ("gavetas")**, as **transferências entre
empresas/destinos**, o **inventário** e o **kardex de terceiros**. Levantamento por `SELECT`
somente leitura.

## 1. Síntese

| Papel | Objeto | Linhas | Estado |
|-------|--------|-------:|--------|
| **Item de estoque** (rolo+peça únicos) | `CTE_Peca` | **297 044** | **Em uso** |
| **Baixa/movimento** de peça | `CTE_Baixa` | **280 240** | **Em uso** |
| **Snapshot de saldos** (mensal, agregado) | `CTE_Saldos` | **5 577** | **Em uso** |
| Observações da peça | `CTE_Obs_Peca` | 3 794 | Em uso |
| Grupo de gaveta (depósito/setor) | `Cte_GrupoGaveta` | 9 | **Em uso** |
| **Gaveta/endereço** | `Cte_Gaveta` | 741 | **Em uso** |
| Log de endereçamento (coletor) | `CTE_PalmGav_Log` | 213 527 | **Em uso** |
| Log de peça × gaveta | `Cte_Peca_Gaveta_Log` | 107 921 | **Em uso** |
| Romaneio de transferência | `CTE_RomTransf` | 4 266 | **Em uso** (Tipo `P`) |
| Itens da transferência | `CTE_Itens_RomTransf` | 130 622 | **Em uso** |
| Destino/setor (regras) | `CTE_Destino` | 8 | Cadastro |
| Inventário (cabeçalho) | `Liv_Inventario` | 71 | **Em uso** (mensal) |
| Inventário (itens) | `Liv_Itens_Inventario` | 5 311 | **Em uso** |
| Kardex de terceiros | `Liv_Kardex_EmpTerc` | 2 283 | Em uso |
| Livro fiscal de qtdes (saída/entrada) | `Liv_SaiProd` / `Liv_EntProd` | 34 043 / 22 522 | Em uso fiscal |
| Operador (coletor) | `CTE_Operador` | 16 | Em uso (**contém `Senha`**) |
| Parâmetros por empresa | `CTE_ParamEmp` | 5 | Em uso |
| Mesclagem de etiquetas | `CTE_Mesclagem` | 293 | Cadastro |
| Backup de saldos | `cte_saldosbkp` | 2 588 | Legado/backup |
| **Stock "genérico"** (`Deposito`, `Inventario`, `Saldo_Inicial`, `PCP_Estoque_Saldo`, `Cte_Romaneio`, `Cte_Fardo`, `CTE_Saldos_Tintur`) | — | **0** | **Vazias** |

> **Não existe** um módulo `Est_*` genérico: o estoque real é o **`CTE_*`** (Controle de Estoque,
> vertical têxtil), cujo grão é a **peça** (`Nro_Rolo` + `Nro_Peca`). As tabelas que aparentam um
> estoque "genérico" (`Deposito`, `Inventario`, `PCP_Estoque_Saldo`…) estão **vazias**.

## 2. Modelo de estoque

```
CTE_Peca  (1 linha por rolo+peça; Situacao = estado do produto)
   │  Empresa+Situacao+Nro_Rolo+Nro_Peca  (PK)
   │
   ├─ CTE_Baixa      (saída da peça — Tipo 'V' = venda/consumo)
   ├─ CTE_Obs_Peca   (observações)
   ├─ Cte_Peca_Gaveta_Log / CTE_PalmGav_Log   (endereçamento)
   │
   └─► estoque em aberto = peça SEM baixa   →  VW_CTE_PECA_EM_ABERTO (16 804)

CTE_Saldos  (snapshot mensal agregado por produto/cor/desenho/…)
   └─► VW_Saldo_Estoque (104) · Vw_Saldos_Produto (267, c/ produto sombra)

CTE_RomTransf ── CTE_Itens_RomTransf   (transferência de peças entre destinos)

Cte_GrupoGaveta ── Cte_Gaveta          (endereço físico NN.NN.NN.N)

Liv_Inventario ── Liv_Itens_Inventario (contagem/inventário fiscal)
```

## 3. `CTE_Peca` (297 044) — item de estoque

- **PK**: `Empresa char(2)` + `Situacao char(3)` + `Nro_Rolo char(10)` + `Nro_Peca char(3)`
  (uma peça = um rolo + número de peça).
- **FKs**: `Cor → Car_Cores`, `Desenho → Car_Desenhos`, `Gaveta → Cte_Gaveta`,
  `Empresa → Empresas`, `EmpProd+Produto → Produtos`, `Situacao → Car_Situacoes`.
- **`Situacao`** (decodificada de `Car_Situacoes`): `000` CRU · `001` TINTO · `002` ESTAMPADO.
  Hoje **100% em `001` (TINTO)**.
- **Cobertura**: `Data_Entrada` de **20/07/2018 → 17/09/2026**; **21 produtos**, **67 cores**,
  **1 desenho** e **653 gavetas** distintas; Σ `Metros` = **20 393 258,28**.
- **Metadados de peça**: `Metros`, `Peso`, `Peso_Bruto`, `Largura`, `Fator_Quebra`,
  `INDICE`, `NUANCE`, `PORCENT_QUALID`, `Custo_Unitario`, `Vr_Unitario*`, `Nro_Rolo_Origem`/
  `Nro_Peca_Origem`, `Rolo_Devolucao`/`Peca_Devolucao`, `Devolucao`, `Bloqueado`,
  `Terceiros`, `Kit`/`Seq_Kit`, `Nro_Fardo`, `CodAcond`, `Num_Etq_Aux`.
- **Origem/rastreabilidade**: `Ordem_Producao`, `Ficha_Tecnica`, `Ficha_Transfer`, `Tear`,
  `Operador`, `Revisadeira`, `Tecelao`, `Turma`, `Processo`, `Item_Processo`, `Malha`,
  `Empresa_Tinto`/`Romaneio_Tinto`, `Empresa_Remessa`/`Nro_Rolo_Remessa`/`Nro_Peca_Remessa`.
- **Compra/importação**: `Tipo_Fornec`, `Fornecedor`, `Documento`, `Serie`, `Nro_RoloImp`,
  `Nro_PecaImp`, `Urd_CxsFios`, `Trama_CxsFios`.
- Estado: `Bloqueado = 'N'` em todas as linhas; `Devolucao`/`Terceiros` quase sempre vazio.

## 4. `CTE_Baixa` (280 240) — saída da peça

- **PK** idêntica à de `CTE_Peca` e **FK** para ela (a baixa é a "negativa" da peça).
- **`Tipo`**: `'V'` = **274 402** (baixa por venda/consumo) e **`NULL` = 5 838** (legado).
- **`Data_Saida`**: 01/08/2018 → 17/09/2026.
- Demais colunas: `Romaneio`, `Corte_Altera`, `Bloqueado`, `Observacao`,
  `Nr_Lancamento_CFC` (ponte com o CFC/produção).
- **Estoque em aberto** = peça que **não** possui baixa
  (`VW_CTE_PECA_EM_ABERTO` = **16 804** peças, com descrições de produto/situação/cor/desenho/
  categoria/variante).

## 5. `CTE_Saldos` (5 577) — snapshot de saldos

- **PK**: `ID_Saldo int` (surrogate); sem FK declarada.
- **Grão**: `Empresa + Situacao + EmpProd + Produto + Cor + Desenho + Categoria + Variante + Data`.
- **Colunas**: `Metros decimal(16,4)`, `Peso decimal(16,4)`, `Qtde int`, `Data smalldatetime`.
- **Estado**: só **`Empresa=13`, `EmpProd=01`, `Situacao=001`**; Σ `Metros` = **1 224 596,74**
  e Σ `Qtde` = **0** (o saldo relevante é em **metros**, não em quantidade).
- **Datas** são **mensais** (ex.: `2026-09-01`, `2026-08-01`, …) de **07/2018 → 09/2026**, com
  alguns lançamentos intradiários e **valores negativos por competência** (furo de snapshot).
- `cte_saldosbkp` (2 588) é um backup dessa tabela.

### Views de saldo

- **`VW_Saldo_Estoque`** (104 linhas): agrega `CTE_Saldos` por empresa/produto/cor/desenho/
  situação/categoria, somando `Metros`/`Peso`/`Qtde` e trazendo `Ret_Unidades.QMP`,
  descartando linhas cuja soma dos três é zero.
- **`Vw_Saldos_Produto`** (267): agrega `CTE_Saldos` e, quando
  `Car_parametros.Usar_ProdutoSombra='S'`, também projeta o **produto sombra**
  (`Produtos_Tecidos.Produto_Origem → Produto`).
- Views relacionadas no PCP/CMT/compras: `VW_PCP_Produtos_Estoque` (364, usa
  `PCP_Estoque_Saldo` — hoje **vazia**), `VW_Saldos_PedCompra` (2 204), `Vw_Car_SaldoPedido`
  (154, saldo de pedido = `Qtde − Qtde_Romaneio − Qtde_Acerto`) e `Vw_Cmt_Saldo_Pedidos`
  (2 171).

## 6. Endereçamento — gavetas

- **`Cte_GrupoGaveta`** (9): `DEPÓSITO 01/02/03`, `PRODUÇÃO`, `TRANSPORTE`, `CANAL VERDE`,
  `CANAL VERMELHO`, `ETIQUETAGEM`, `INVENTARIO`.
- **`Cte_Gaveta`** (741): endereço com **`Codigo char(10)`** no padrão `NN.NN.NN.N`
  (ex.: `02.48.02.0`), `Descricao`, `GrupoGaveta`, `Setor`, `Faz_Sugestao`,
  `Estoque_Plano`, `confirmarTransferencia`.
  - Em uso: `Setor='003'` (739) + `'000'`/`'002'` (1 cada).
  - `Faz_Sugestao='S'` (738) e `Estoque_Plano='S'` (739) → endereçamento **sugere** posição, e
    `confirmarTransferencia='N'` em todas → a transferência de gaveta **não exige confirmação**.
- **Logs**: `CTE_PalmGav_Log` (213 527) e `Cte_Peca_Gaveta_Log` (107 921) são o histórico de
  movimentação de peças entre gavetas (coletor/empilhadeira).
- Na própria `CTE_Peca`, `Gaveta` é amplamente usada (`PACKLIST`, branco `''`, `007`, `001`,
  endereços `NN.NN.NN.N`), mostrando a convivência entre endereço físico e rótulos de fluxo.

## 7. Transferências — `CTE_RomTransf` / `CTE_Itens_RomTransf`

- **`CTE_RomTransf`** (4 266; PK `Empresa + Romaneio`): `Tipo='P'` (100%), `Data_Rom` de
  **12/06/2025 → 17/09/2026** (módulo recente), `Destino`, `Selecionado`, `Empresa_NF`/`Pedido_NF`,
  `Empresa_Consiste`/`Id_Consiste`, `Tipo_Comercializacao`.
- **`CTE_Itens_RomTransf`** (130 622; PK `Empresa + Romaneio + ID_RomTransf`): peças do romaneio
  (`Nro_Rolo`/`Nro_Peca`, `Codigo_Caixa`/`Entrada_Caixa`) e o retorno de facção
  (`Empresa_RetFac`/`Romaneio_RetFac`/`ID_RomTransf_RetFac`).
- **`CTE_Destino`** (8) define os destinos/setores e suas regras
  (`Confirma_Baixa`, `Emitir_NF`, `Transferencia`, `Retorno_Facionista`, `Historico`,
  `Tipo_Tear`, `Setor_ProdAux`): `001` TECELAGEM, `002` MOVEN ESTOQUE, `003` ARMAZÉM PRÓPRIO,
  `004` S, `005` W, `006` WS, `007` ST, `008` K.

## 8. Inventário

- **`Liv_Inventario`** (71): `Empresa` (`01` e `13`) + `Cod_Liv_Inventario` (int, PK) +
  `Descricao`, `Data`, `Bloqueado`. O primeiro é `Saldo Modelo 3` (01/05/2019) e, a partir de
  **2021**, há um **inventário mensal** (fechamento de cada mês) para a empresa `13`.
- **`Liv_Itens_Inventario`** (5 311; PK `Empresa + Cod_Liv_Inventario + Chave`): `Produto`,
  `Qtde`, `Vr_Unitario`, `Vr_Total`, `Unidade`, `Propriedade`, `Tipo_Inventario`, `CNPJ`,
  `ClassFisc`. `Tipo_Item = 5` em todas; `Tipo_Inventario`: `01` (Saldo Modelo 3) 5 121,
  `03` 170, `02` 20. FKs para `Liv_Inventario`, `Liv_Propriedade_Item`,
  `Liv_Tipo_Inventario`.
- Tabelas legadas de inventário (`Inventario`, `Inventario_Security`, `Inv_Saldo_PEPS`,
  `CTE_Saldos_Tintur`, `CTE_Saldos_Consignacao`) estão **vazias**.

## 9. Kardex de terceiros e livro de quantidades

- **`Liv_Kardex_EmpTerc`** (2 283; PK `Id_Kardex + Id_Empresa`): movimento de estoque **de
  terceiros** — `Documento`, `Serie`, `NatOP`, `Produto`, `Tipo`, `Movimentacao`, `Qtde`,
  `Metros`, `Peso`, `VrUnitario`, `VrTotal`, `EntradaData`/`SaidaData`, `Id_KardexRef`/
  `Id_EmpresaRef`. Só há **`Movimentacao='S'` (saída)**: `Tipo='A'` (2 265) e `Tipo='C'` (18).
- **Livro fiscal de quantidades**: `Liv_SaiProd` (34 043) e `Liv_EntProd` (22 522) carregam
  `Qtde`/`Peso` por documento/produto (usados também no custo médio — Estudo 23). **Não têm
  coluna `Data`** — a data vem do cabeçalho (`Liv_Saidas`/`Liv_Entradas`) por
  `Empresa + Documento + Serie`.
- `Produtos` guarda os parâmetros de reposição: `Estoque_Minimo`, `Estoque_Maximo`,
  `Faz_Sugestao`, `Lote_Minimo_Compra`, `Qtde_Multipla_Compra`, `ControleLotes_Saldo`.

## 10. Operadores, parâmetros e auxiliares

- **`CTE_Operador`** (16): operador de coletor — `Codigo`, `Nome`, **`Senha`**, `GrupoOperador`
  e flags (`LiberaRepesagem`, `liberarDifTolerancia*`, `PermiteInsercaoManualOkeaVL`,
  `LiderApont`…). **Contém segredo (`Senha`)** → não replicar.
- **`CTE_ParamEmp`** (5): setores (`Setor_Disponivel`, `Setor_EmProcesso`, `Setor_Urdido`,
  `setor_prodplm`), grupos de goma/pigmento, `Ult_Rom_Transf_Dig`, flags de validação.
- Auxiliares: `CTE_Mesclagem` (293, mesclagem de etiquetas por tabela/campo/máscara),
  `CTE_Help` (22), `CTE_UNIDADE_FABRIL` (11), `CTE_ITENS_TRATAMENTO` (10), `CTE_TRATAMENTO` (1),
  `CTE_CRITICA_PLM` (20), `CTE_Tab_ImportEstoque` (2), `CTE_Parametros` (1).

## 11. Procedures e funções de estoque

- **Posição/consulta**: `SP_CTE_Estoque`, `SP_CTE_ConsEst_Pecas`/`_Itens`/`_Fios`/`_Fardos`/
  `_Tintur`/`_MPAux`/`_RemRet`/`_ValMaq`/`_ValProc`/`_ValTintur`/`_PEent`/`_Facionista`,
  `SP_RelPosicaoEstoque`, `SP_GiroEstoque`, `SP_Rel_CurvaABC_Estoque`,
  `SP_Rel_Car_AnaliseEstoque`, `SP_GESTOR_GRADE_ESTOQUE`, `SP_Gestor_Resumo_Pronta_Entrega`.
- **Mínimo/máximo**: `SP_Cte_RelEstoqueMinimo(_Var)`, `SP_EstoqueMinCorDes(Var)`,
  `SP_CTE_EstMinimoTecFio`.
- **Inventário**: `SP_Liv_Gera_Inventario(_DGB)`, `SP_Lv3_Gera_Inventario`,
  `SP_Lv3_*Saldos*`, `SP_GeraInventario`, `CFC_GeraInventario(2)`, `CFC_ZeraInventario`,
  `Ret_GeraInventario`, `CTE_RelInventario`, `SP_Lv3_RelValEstoque`, `sp_ValorEstoqueInventario`,
  `SP_SaldosReal_Inventario(_Comparativo)`.
- **Valorização/custo**: `SP_CMT_GeraEstoque*`, `SP_CMT_ValorizacaoEstoque`,
  `SP_Lv3_RelCustoEstoque`, `SP_Lv3_RelValEstoque`, `sp_ValorEstoqueTinturaria`,
  `sp_ValorEstoqueFacionista`.
- **Integração/legado**: `Atualiza_Estoque_MIC`, `SP_Atualiza_Estoque_Loja`,
  `SP_CTE_Importa_Estoque`, `SP_CTE_ALIMENTA_ESTOQUE_EAN`, `SP_CMT_GeraEstoquePCP/FAC`.
- Funções: `fn_cteRoloPrimarioListTransfDestino`, `FNC_PCP_Sugestao_Ficha_Tecnica`.

## 12. Impacto para a nova API (Neon)

1. **Grão do estoque é a peça** (`Empresa + Situacao + Nro_Rolo + Nro_Peca`) — materializar
   `fato_estoque_peca` a partir de `CTE_Peca` **antijoin** `CTE_Baixa` para a posição atual
   (equivalente a `VW_CTE_PECA_EM_ABERTO`).
2. **Saldo agregado** pode vir de `CTE_Saldos` (mensal) ou ser calculado; cuidado com os
   **valores negativos** e com a unidade **metros** (QMP em `Ret_Unidades`).
3. **Endereço** = `Cte_Gaveta` (`NN.NN.NN.N`) + `Cte_GrupoGaveta`; movimentos de gaveta em log
   próprio (`Cte_Peca_Gaveta_Log`).
4. **Movimento de estoque** para conciliação: `CTE_Baixa` (saída) e `Liv_EntProd`/`Liv_SaiProd`
   (quantidades fiscais, data no cabeçalho).
5. **Inventário** trimestral/mensal em `Liv_Inventario` + `Liv_Itens_Inventario`.
6. **Não replicar**: `CTE_Operador.Senha`.
7. Tabelas "genéricas" (`Deposito`, `PCP_Estoque_Saldo`, `Cte_Romaneio`, `Cte_Fardo`) estão
   **vazias** → não incluir no ETL.
