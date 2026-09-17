# Estudo 25 — Expedição/armazém: distribuição, ordem de separação, coleta, romaneio e despacho

Levantamento de **estrutura** (tabelas, colunas, status, procs e **contagens**) por `SELECT`
somente leitura. Nenhum dado sensível. Objetivo: entender os documentos de **armazém/expedição** —
em especial **ordem de despacho** e **solicitação/ordem de separação** — e como se encadeiam.

## 1. Síntese

| Documento | Objeto principal | Estado |
|-----------|------------------|--------|
| Distribuição / alocação | `Car_Pecas_Distribuidas`, `Car_Gestor_*`, `CAR_DISTRIBUICAO` | **Modelado, 0 linhas** |
| Efetivação / ordem de embarque | `Car_Efetiva_Distri`, `Car_OrdEmbarque` | **0 linhas** |
| **Ordem de separação** | `CAR_SEPARACAO` + `_ITENS` + `_PECAS` | **3 ordens** (2021), ativo mas pouco usado |
| Coleta (palm) | `Car_Coleta` (115), `CTE_PalmGav_Log` | **Em uso** (Estudo 24) |
| **Romaneio** | `Car_Romaneio` (14 596) + `Car_Itens_Romaneio` (274 402) | **Em uso** (documento central) |
| Requisição | `Car_Requisicao` (96) | Cadastro/fluxo auxiliar |
| **Minuta de despacho** | `Fat_Minuta_Despacho` (7) + `_Notas` (9) | **Em uso** (transporte/CTRC) |
| Romaneio de outros módulos | `CFC_*`, `Tnt_*`, `PCP_*`, `Cte_*` | **Vazios** |

> O módulo `Car_*` (Carteira) concentra a expedição. O módulo **`SP_GESTOR_*`** é o “WMS de
> pedidos” (distribuir → efetivar → separar → coletar), hoje com tabelas **vazias**, mas com as
> procs e views prontas.

## 2. Fluxo de expedição (do pedido à NF)

```
Car_Pedido / Car_Itens_Pedido
      │  (distribuição/alocação de rolos)
      ▼
Car_Pecas_Distribuidas ──SP_GESTOR_DISTRIBUIR──► CAR_SEPARACAO (+_ITENS,+_PECAS)
      │  efetivação                                    │  status 0..4
      ▼                                                 │
Car_Efetiva_Distri (Ordem_Embarque) ◄──SP_GESTOR_EFETIVAR + sp_OrdemSeparacao
      │  (imprime OS / separação)                        │
      ▼                                                  ▼
Car_Coleta (coletor/palm)  ────────────────►  Car_Romaneio + Car_Itens_Romaneio
      │                                                  │  (crítica/consiste)
      ▼                                                  ▼
Fat_Minuta_Despacho (+_Notas)  ◄── agrupa NFs ──  Fat_Pedido / Notas_Fiscais
      │                                                  │  (transportadora/CTRC)
      ▼                                                  ▼
   SIC/CTRC (transporte)                            Rec_* / faturamento (Estudo 05)
```

## 3. Módulo “Gestor” (distribuição/expedição de pedidos)

### 3.1 Tabelas (estrutura pronta, **0 linhas**)

- **`Car_Pecas_Distribuidas`** — peças alocadas ao pedido: `empresa, inc, nro_rolo, nro_peca,
  pedido, item_ped, ordem_embarque` (inserida por `SP_GESTOR_DISTRIBUIR`).
- **`Car_Efetiva_Distri` (33 col.)** — efetivação/ordem de embarque: `Empresa, Ordem_Embarque,
  Item, Item_Ped, Romaneio, Pedido, Data_Distribui, Cliente, Razao_Nome_Cliente, Produto,
  Situacao, Cor, Desenho, Categoria, Qtde, Qtde_Romaneio, Saldo, Mts_Distribui, Obs_Distribui,
  Saldo_Distr, Data_Pedido, Data_Entrega, **Selecionado, Data_Efet, Impresso, Ordenador, VrDistri,
  Cidade, Flag_Imprimir, Usuario, Variante, Em_Leitura, Romaneio_Reservado**`.
- `CAR_DISTRIBUICAO` / `CAR_DISTRIBUICAO_Pedido` (0) — distribuição por pedido.
- `Car_Corte_Distribuicao`, `Car_Obs_Distribuicao` (0).
- `Car_Gestor_Estoque`, `_Pecas`, `_Grade`, `_Grade_Estoque`, `_Reserva`, `_Bloqueio`,
  `_Visualizacao`, `_Param_Visualizacao`, `_Tam_Minimo_SGS` (0) — cache/parâmetros do painel.
- **`Car_Gestor_Parametros` (1)** — parâmetros do Gestor.
- `Car_Pecas_Invalidas`, `CAR_PECAS_CORTE` (0), `TMP_VW_GESTOR` (340) — snapshot temporário.
- `SIC_Documento_Distribuicao` (0) — documento (SAC/qualidade) da distribuição.

### 3.2 Procedures do Gestor (ativas)

`SP_GESTOR_PAINEL` (painel de estoque/pedidos), `SP_GESTOR_DISTRIBUIR`, `SP_GESTOR_EFETIVAR`,
`SP_GESTOR_CANCELAR_EFETIVACAO`, `SP_GESTOR_SEPARAR`, `SP_GESTOR_CONSISTIR_SEPARACAO`,
`SP_GESTOR_CANCELAR_SEPARACAO`, `SP_GESTOR_GRADE_ESTOQUE`, `SP_GESTOR_LER_PECAS`,
`SP_Gestor_Reservar_Corte`; views `VW_GESTOR`, `VW_GESTOR_PCP`, `VW_GESTOR_GRADE`,
`VW_GESTOR_Ordem_Separacao`, `VW_Gestor_Total_Ordens_Aberto`, `VW_Car_Distribuidos`,
`VW_Car_BloqDistribuidos`.

- `SP_GESTOR_DISTRIBUIR(@pedido,@item)` → insere peças em `Car_Pecas_Distribuidas`
  (com `ordem_embarque`).
- `SP_GESTOR_EFETIVAR(@pedido,@item,@ordemEmbarque)` → grava `Car_Efetiva_Distri` (Ordem_Embarque).
- `sp_OrdemSeparacao(@Empresa,@Operador,@TodosClientes,@BloqueiaCliente)` → marca
  `Car_Efetiva_Distri.Impresso='S'` para imprimir a **Ordem de Embarque/OS** por cliente.
- `sp_InsereCarDistribuicao(...)` → monta a distribuição por filtros (empresa/período/vendedor/
  cliente/produto/situação…).
- `VW_Car_Distribuidos` = pedido × item × produto × `Ordem_Embarque` × `Romaneio` × `Saldo`.

## 4. Ordem / Solicitação de Separação — `CAR_SEPARACAO*`

### 4.1 Estrutura (em uso: 3/4/11 linhas)

- **`CAR_SEPARACAO`** — cabeçalho: `NUMERO (PK), EMPRESA, PEDIDO, CLIENTE, DATA_GERACAO,
  DATA_EMISSAO, DATA_CONFIRMACAO, DATA_CANCELAMENTO, ROMANEIO, TIPO, STATUS, Motivo_Bloqueio,
  CreditoCliente, ValorOS, ValorDup, ValorCh, SaldoCredito, Sistema_Pedido, ID_Deposito,
  ObservacaoColetaPeca`.
- **`CAR_SEPARACAO_ITENS`** — `NUMERO, EMPRESA, ITEM_SEP, PEDIDO, ITEM, SALDO_PEDIDO,
  QTDE_ORIGINAL, QTDE_SEPARADA, TEM_PECAS, STATUS`.
- **`CAR_SEPARACAO_PECAS`** — peças escolhidas: `NUMERO, EMPRESA, ITEM_SEP, PEDIDO, ITEM,
  SITUACAO, NRO_ROLO, NRO_PECA, QTDE, STATUS, OPERADOR`.

**Legenda de `STATUS`** (de `SP_GESTOR_SEPARAR`): **0 = Gerado, 1 = Impresso, 2 = Em Coleta,
3 = Confirmado, 4 = Bloqueado**. `TIPO='V'` (venda) e `Sistema_Pedido='CAR'` (carteira).
`VW_GESTOR_Ordem_Separacao` traduz o status (`Gerado`/`Impresso`/`Em Coleta`).

### 4.2 Ciclo e procedures

- Geração: **`SP_Car_GeraPedidoSeparacao`** (gera pedido + separação para “romaneio sem pedido”,
  com `@Terminal, @Empresa, @Cliente, @Usuario, @Ordem_Gerada OUTPUT`) e `sp_OrdemSeparacao`.
- Consistência/confirmação: **`SP_GESTOR_CONSISTIR_SEPARACAO`** → `STATUS=3`,
  `DATA_CONFIRMACAO = Car_Romaneio.Data_Rom`.
- Cancelamento: `SP_GESTOR_CANCELAR_SEPARACAO`; exclusão: `SP_CAR_DeletaColetaPecasSeparadas`.
- Romaneio: `SP_Car_InsertRomaneio_Separacao`.
- Views: `Vw_Car_SeparacaoVenda` (separação→itens→peças→pedido→cliente), `_FCI`,
  `VW_Car_SeparacaoPedido_CodBarras`, `Vw_PDV_SeparacaoItens`, `Vw_PCP_Estoque_Separado`.

> Uso real baixo (3 ordens, jun/2021): a operação normalmente vai **do pedido direto ao
> romaneio**, usando a Ordem de Separação apenas em casos específicos.

## 5. Coleta (palm) — ponte separação ↔ romaneio

`Car_Coleta` (115) + `Car_Coleta_Log` (0) e o coletor de gaveta `CTE_PalmGav_Log` (213 527) —
ver Estudo 24. `Car_Coleta` liga `Pedido`, `Ordem_Separacao`, `Rolo_Coletado`, `Peca_Coletada`,
`Terminal`, `Critica_OK/Critica`. `CTE_PalmGav_Log` é o movimento físico de endereço feito no
coletor enquanto se separa.

## 6. Romaneio — documento central de expedição

### 6.1 `Car_Romaneio` (14 596, 42 col.)

`Empresa, Romaneio, Tipo, Empresa_Pedido, Pedido, Cliente, Data_Rom, Pedido_NF, Urdume, Trama,
Largura_Acabada, Observ_1..5, Nota_Fiscal, Situacao_Ret, **Status**, SubLote, **Requisicao**,
Empresa_NF, Operador_Critica, OK_Critica, Peso_Bruto, Peso_Liquido, Bloqueado, Data_Status,
**Status_Geracao**, CliTinturaria, Selecionado, Id_Consiste, Tipo_Comercializacao,
Empresa_Consiste, Reprocesso, Irrecuperavel, Data_Troca, UsuarioSelecao, Status_ImpPecas,
Empresa_Importa, data_retorno, eh_Proprio`.

- `Status`: `'N'` = 14 575, `'S'` = 21. `Selecionado`: `'N'` = 14 579, NULL = 17.
  `OK_Critica` 100 % NULL (crítica não usada hoje).
- Período: 01/08/2018 → 17/09/2026; `Tipo` = `'V'` (venda) em 100 %.

### 6.2 `Car_Itens_Romaneio` (274 402, 55 col.)

`Empresa, Romaneio, Tipo, Incremento, Nro_Peca, Produto, Situacao, Cor, Desenho, Categoria,
Qtde, Peso, Vr_Unitario, Vr_Total, Empresa_Pedido, Pedido, Nro_Item_Pedido, Nro_Peca_Pedido,
Rolos, Largura, Mts_Rolo, Item_Peca, Pacote, Data_Prevista, Classificacao, Banho, Fundo,
Comissao, Origem_Saldo_Tintur, Situacao_Ret, Avaliacao, Unid, Unid_Fat, Qtde_Fat,
Vr_Unitario_Fat, **Fardo**, Item_Fatura, Id_ItensConsiste, Variante, Sublote, Nuance,
Vr_Desconto, Porc_Desconto, Produto_Ret, Cor_Ret, Desenho_Ret, Categoria_Ret, Variante_Ret,
unit_servico_entrada, unit_servico_saida, Codigo_Produto_Concat, Id_PCP_Estoque, Codigo_Barra,
**Rolo_Coletado, Peca_Coletada**`.

- **`Rolo_Coletado`/`Peca_Coletada` = 100 % vazios** (274 402 sem coleta) → a coleta não é
  registrada no item de romaneio.
- `Car_Itens_Romaneio` **liga ao estoque** por `Nro_Peca`/`Item_Peca` ↔ `Cte_Peca`
  (`Nro_Rolo`/`Nro_Peca`), e ao pedido por `Empresa_Pedido/Pedido/Nro_Item_Pedido`.

### 6.3 Modelos correlatos (vazios)

`Car_OE_Romaneio` (Ordem de Embarque por peça: `Romaneio, Incremento, Nro_Peca, Nro_Seq, …,
Data_Coleta, Hora_Coleta, Operador, Critica`), `Car_Pedido_Romaneio` (link pedido↔romaneio),
`Car_Romaneio_Coleta`, `Car_Romaneio_Faturamento`, `Car_Itens_Romaneio_Coletado`.

### 6.4 Procedures de romaneio (ativas)

`SP_Romaneio_Expedicao`, `SP_DivideFatRomaneio`, `SP_Car_DivideRomaneio`,
`sp_Car_ImportarRomaneio`, `SP_CAR_Insere_Peca_Romaneio_EAN`, `SP_CAR_Exclui_Peca_Romaneio_EAN`,
`SP_CAR_Exclui_Caixa_Romaneio_EAN`, `SP_GeraRomVenda`, `SP_GeraRomTintur`;
views `VW_Car_Romaneio`, `VW_RB_Car_Romaneio`, `VW_Car_Itens_Romaneio(_CodBarras)`,
`VW_CarPedidosRomaneioNF`, `VW_Consulta_Romaneios`, `VW_Qtde_Romaneio`, `VW_Rolos_Romaneio`.

## 7. Ordem de Embarque / efetivação

- **`Car_Efetiva_Distri.Ordem_Embarque`** = documento de carga/embarque (ver §3.1);
  `sp_OrdemSeparacao` imprime por `Ordem_Embarque`/`Ordenador`.
- `Car_OrdEmbarque` (0) — modelo de controle de carregamento: `Codigo, Chave_NFe, Pedido,
  Cliente, Data_Emissao_NF, Data_Inicio/Hora_Inicio, Data_Final/Hora_Final,
  Operador_Inicio, Operador_Final` (execução da carga).
- `Car_OE_Romaneio` (0) — embarque por peça.
- `CAR_DISTRIBUICAO(_Pedido)` (0) — distribuição de pedidos.

## 8. Requisição — `Car_Requisicao` (96)

`Empresa, Requisicao, Data, Hora, Usuario`. Usada como cabeçalho de **requisição** (referenciada
por `Car_Romaneio.Requisicao`) — fluxo auxiliar de retirada/entrega interna. Sem itens próprios
com carga (tabelas correlatas vazias).

## 9. Minuta de Despacho — `Fat_Minuta_Despacho`

- **`Fat_Minuta_Despacho` (7)**: `Empresa, Nr_Minuta, Data` (01 → 09; 2025-09 → 2026-07).
- **`Fat_Minuta_Despacho_Notas` (9)**: `Empresa, Nr_Minuta, Nr_Nota, Serie` → agrupa **notas
  fiscais** na minuta (é a **ordem de despacho / manifesto de entrega**).
- Trigger `TG_INS_Fat_Minuta_Despacho`: se `SIC_Parametros.Usar_Inspecao_Minuta='S'`, cria a
  avaliação em `SIC_Avaliacao_Minuta` (a partir de `SIC_Inspecao_Minuta`).
- Consumida por: `SP_SIC_BIT_Transportadoras`, `SP_SIC_Indice_Transporte`, `SP_SIC_REL_BIT`,
  `Vw_RB_SIC_Transportadoras_CTRC` → gera **CTRC / transporte (SIC)**.
- **`Fat_Pedido`** carrega os campos de transporte/dispatch: `Cod_Transp, Des_Transp,
  Placa_Transp, Local_Transp, **Romaneio**, Imprime_Romaneio, Despesa_Transp,
  Nr_Conhecimento_Transp` → liga faturamento ↔ romaneio ↔ conhecimento de transporte.

## 10. Módulos de romaneio/embarque **vazios** (não usados nesta base)

- CFC: `CFC_Embarque`, `CFC_Itens_Embarque` (embarque por pedido/romaneio/coletor),
  `CFC_Romaneio*`, `Cfc_Ordem_Producao*`.
- TNT: `Tnt_Romaneio*`, `TNT_RomaneioRemessa*`, `Tnt_Ordem_NFE*`.
- PCP: `PCP_Romaneio*`, `PCP_Volume_Romaneio`, `PCP_OrdemProd*`.
- CTE: `Cte_Romaneio*`, `CTE_Romaneio_Urdume*`.
- `Rec_CargaRetorno*` (retorno de carga) e `CFC_Embarque`.

## 11. Implicações para a API / Neon

1. **Documento de expedição real = `Car_Romaneio` + `Car_Itens_Romaneio`** → extrair como
   `core.shipment`/`shipment_item` (PK `Empresa+Romaneio+Tipo+Incremento`), ligando a
   `Car_Pedido`/`Car_Itens_Pedido` e a `Cte_Peca` (rolo/peça).
2. **Ordem de separação = `CAR_SEPARACAO*`** → `core.pick_order`(`_item`,`_piece`) com status
   `0..4`; ligar a romaneio (`ROMANEIO`) e pedido.
3. **Distribuição/ordem de embarque** (`Car_Efetiva_Distri`, `Car_Pecas_Distribuidas`) está
   vazia: no Neon pode-se **modelar** (`shipment_order`/`load`) sem carga histórica.
4. **Coleta**: `Car_Coleta` (por pedido/OS) + `CTE_PalmGav_Log` (por endereço) — dois trilhos a
   unificar em `core.pick_move` (Estudo 24).
5. **Despacho**: `Fat_Minuta_Despacho(_Notas)` → `core.dispatch_note`/`dispatch_note_invoice`,
   ligando NFs; útil para logística/CTRC.
6. **Cuidado com os vazios**: não portar `CFC/TNT/PCP/CTE` de romaneio; mapear como “feature
   não usada”.

## 12. Objetos-chave deste estudo

- Gestor/distribuição: `SP_GESTOR_{PAINEL,DISTRIBUIR,EFETIVAR,SEPARAR,CONSISTIR_SEPARACAO,CANCELAR_*}`,
  `Car_Pecas_Distribuidas`, `Car_Efetiva_Distri`, `Car_Gestor_*`, `VW_GESTOR*`, `sp_OrdemSeparacao`.
- Separação: `CAR_SEPARACAO`, `CAR_SEPARACAO_ITENS`, `CAR_SEPARACAO_PECAS`,
  `SP_Car_GeraPedidoSeparacao`, `SP_Car_InsertRomaneio_Separacao`, `Vw_Car_SeparacaoVenda`.
- Romaneio: `Car_Romaneio`, `Car_Itens_Romaneio`, `Car_OE_Romaneio`, `Car_OrdEmbarque`,
  `SP_Romaneio_Expedicao`, `SP_DivideFatRomaneio`, `VW_Car_Romaneio(_Cond_Pagto)`.
- Coleta: `Car_Coleta`, `CTE_PalmGav_Log` (Estudo 24).
- Despacho: `Fat_Minuta_Despacho(_Notas)`, `Vw_RB_SIC_Transportadoras_CTRC`,
  campos de transporte em `Fat_Pedido`.
