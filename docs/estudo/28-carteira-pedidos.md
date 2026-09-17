# Estudo 28 — Carteira/Pedidos (`Car_*`): pedido de venda em profundidade

Levantamento de **estrutura** (tabelas, colunas, PK/FK, índices, status, views, procs, triggers e
**contagens**) por `SELECT` somente leitura. Nenhum dado sensível. Objetivo: mapear por completo o
**coração comercial** do ERP — o pedido de venda — que alimenta faturamento, estoque e expedição.

> Escopo: tabelas `Car_*` relacionadas a **pedido/carteira**. Romaneio/expedição (`Car_Romaneio`,
> `Car_Itens_Romaneio`, `CAR_SEPARACAO`, `Car_Coleta`) já foram detalhados no
> [Estudo 25](./25-expedicao-despacho-separacao.md) e são apenas referenciados aqui.
> Cadastros usados pelo pedido (cliente, produto, cor, desenho, vendedor, tabela de preço) foram
> detalhados no [Estudo 27](./27-cadastros-base-profundo.md) e no
> [Estudo 17](./17-cadastros-comerciais.md).

## 1. Síntese

| Papel | Objeto principal | Linhas | Estado |
|-------|------------------|-------:|--------|
| **Pedido (cabeçalho)** | `Car_Pedido` | 15 799 | **Em uso** (todo o histórico é empresa `13`) |
| **Itens do pedido** | `Car_Itens_Pedido` | 41 224 | **Em uso** |
| Vendedor do pedido | `Car_Vend_Pedido` | 15 774 | **Em uso** (1 vendedor/pedido) |
| Observações do pedido | `Car_Obs_Pedido` | 15 779 | **Em uso** (quase 1:1 com pedido) |
| Peças do item (fracionamento) | `Car_Pcs_Pedido` | 4 389 | Uso pontual |
| Itens por data de entrega | `Car_ItensPedido_PorDataEntrega` | 906 | Uso pontual |
| Resumo por item (reserva/separado) | `Car_ItensPedido_Resumo` | 924 | Uso pontual |
| **Auditoria de item** | `Car_Itens_Modificados` | 15 403 | **Em uso** (`Tipo` `A`/`D`) |
| Itens cancelados | `Car_Itens_Pedido_Cancelado` | 89 | Uso pontual (2025–2026) |
| Log de alteração de previsão | `CAR_ITENS_CARTEIRA_DATA_PREVISAO_LOG` | 5 838 | **Em uso** |
| Alteração de “posição” (crédito) | `Car_AltPosicao` | 4 801 | **Em uso** |
| Anexos NFe por cliente | `Car_AnexosNFE_Cliente` | 309 | Integração fiscal |
| **Tabela de preço** | `CAR_TABELA_PRECO` (+8 satélites) | 9 | **Em uso** (ver Estudo 17) |
| Perfis/filtros de tela | `Car_Perfil`/`_Filtro`/`_Valor` | 23 / 15 124 / 15 264 | Config de UI |
| Poderosa consulta geral | `Car_Consulta_Geral(+_Param/_Script)` | 16 / 59 / 1 603 | Config de relatórios |
| Distribuição/OS/geolocalização | `Car_*` (0 linhas) | 0 | Modelado, não usado |

O módulo `Car_*` tem **190 tabelas / 452 705 linhas** no total (incluindo romaneio, Estudo 25).

## 2. Fluxo do pedido na carteira

```
Car_Pedido  (Status: 1 Em análise → 2 Aprovado | 3 Cancelado | 4 Análise comercial)
   │  Car_Vend_Pedido (vendedor/comissão)   Car_Obs_Pedido (obs. 1..10 + carteira)
   │  Car_AnexosNFE_Cliente (layout fiscal do cliente)
   ▼
Car_Itens_Pedido  (Produto+Situacao+Cor+Desenho+Variante+Categoria; Qtde, Vr_Unitario)
   │  Qtde_Romaneio  ← separação/expedição (Estudo 25)
   │  Qtde_Acerto    ← ajuste de sobra na coleta
   │  Status_Item '' aberto / 'E' encerrado   →  Status_Ped do cabeçalho
   ▼
Car_Romaneio → Fat_Pedido → Nota Fiscal   (Estudos 04, 05 e 25)
```

- **Saldo do item** (regra canônica): `Saldo = Qtde - Qtde_Romaneio - Qtde_Acerto`
  (usada em `VW_Car_Pedido_Aberto` e `Vw_Saldo_Pedido_Carteira_Qlik`).
- Pedido **aberto** = `Status <> 3` **e** `Status_Ped <> 'E'` (`VW_Car_Pedido_Aberto`).

## 3. `Car_Pedido` (cabeçalho)

- **PK**: `Empresa char(2)` + `Pedido char(8)`. **Todo o histórico é da empresa `13`** (15 799).
- **FKs**: `Cliente → Clientes_Principal.Codigo_Cliente`; `Empresa → Empresas.Codigo_Empresas`;
  `tp_orig_ped_cd → tipo_orig_ped`; `usu_cd → usuario`.
- **Índices**: `Ind_Car_Pedido_CS[Cliente,Status]`, `Ind_Cliente[Empresa,Cliente,Pedido]`,
  `IX_CAR_PEDIDO_STATUS[Status_Ped]`.
- **Período**: `Data_Pedido` de **30/07/2018** a **17/09/2026**.

### 3.1 Domínios / status (decodificados)

| Coluna | Valores | Legenda |
|--------|---------|---------|
| `Status` | `2` 12 762 · `3` 2 969 · `1` 47 · `4` 21 | **1** Em Análise (financeira) · **2** Aprovado · **3** Cancelado · **4** Análise Comercial (`VW_Car_Pedido`/`VW_RB_Car_Pedido_Status`) |
| `Status_Ped` | `''` 9 170 · `E` 6 564 · NULL 65 | `''` **Aberto** · `E` **Encerrado** (calculado pela trigger a partir de `Status_Item`) |
| `Tipo_Pedido` | `1` 15 784 · `4` 13 · `2` 2 | **1** Vendas · **2** Pilotagem · **3** P.Entrega · **4** Serviço · **5** Cortesia (via `Vw_Saldo_Pedido_Carteira_Qlik`) |
| `tp_orig_ped_cd` | NULL 13 889 · `2` 1 785 · `1` 125 | Origem: **1** Celular · **2** Web (`tipo_orig_ped`) |
| `regra_negocio` | `1` 13 638 · `2` 1 807 · NULL 354 | Marca a regra de negócio aplicada (interna) |
| `Tipo_Comercializacao` | `1` 15 604 · `15` 113 · `4` 54 · outros | Tipo de comercialização (referência `Fig_Comercializacao`) |
| `Classificacao` | `1` 15 366 · `4` 248 · `3` 177 | Aponta `Car_Classificacoes` (1 = 100 %, 2 = 50 %, …) |
| `Frete_Conta` | `0` 9 394 · `1` 6 103 · `4` 216 · `3` 50 · `2` 36 | Modalidade de frete (a decodificar com o ERP) |
| `Bloqueado` / `Bloqueado` | `N` 15 799 | Nunca bloqueado no período |
| `Pedido_Urgente` | NULL 11 336 · `N` 4 463 | Sem pedidos urgentes |
| `Politica`, `Marcacao_cd`, `Status_Email` | todos NULL/vazio | Não usados |
| `validado_gestor` | — | Validação do gestor comercial (`SP_GESTOR_*`) |

### 3.2 Colunas (agrupadas)

- **Chaves/relacionamento**: `Empresa`, `Pedido`, `Cliente`, `ClienteEntrega`, `Cliente_Triangulo`.
- **Datas**: `Data_Pedido`, `Data_Entrega`, `Datas_Entrega`(texto), `Datas_Entrega2`,
  `dt_ultima_aprov_comerc`, `DataHora_Alteracao`, `Prazo_Medio`.
- **Comercial**: `Cond_Pagto`, `Cond_Pagto_Extenso`, `Tabela_Tinturaria`, `LinhaProduto`,
  `Tipo_Pedido_Comercial`, `cod_tabela_preco_def_usuario`, `Porcentagem_Comissao`,
  `Porc_Desc`, `Porc_Acresc`, `PercRentabilidadeGeral`, `Politica`.
- **Flags “sugerido”**: `SPro, SSit, SCor, SDes, SCat, SLarg, SVariante`.
- **Transporte**: `Cod_Transp`, `Des_Transp`, `Cod_Redesp`, `Des_Redesp`, `End1_Redesp`,
  `End2_Redesp`, `Redespacho_Conta`, `Frete_Conta`, `Vr_Frete`, `Local_Entrega`.
- **Endereços**: `End1/2_Cobranca`, `End1/2_Entrega`.
- **Banco/cobrança (2 contas)**: `Banco_1/2`, `Agencia_1/2`, `DigAge_1/2`, `Conta_1/2`,
  `DigCon_1/2`, `Operacao_1/2`, `Cobranca_1/2`, `Cheque_1/2`, `Pagto_1/2`, `VerObs_1/2`.
- **Aprovação/crédito**: `MotivoReprova`, `DescricaoReprova`, `alerta_cd`, `marcacao_cd`,
  `regra_negocio`, `validado_gestor`, `email_enviado`, `Status_Email`.
- **Integração**: `tp_orig_ped_cd`, `usu_cd`, `motivo_alt_cd`, `cond_cd`, `ped_orig_nu`,
  `pedido_id`, `Pedido_Ecommerce`, `Pedido_Representante`.

### 3.3 Volumetria e distribuições

Pedidos por ano: 2018 **173** · 2019 **763** · 2020 **1 309** · 2021 **1 759** · 2022 **1 938** ·
2023 **2 518** · 2024 **2 946** · 2025 **2 653** · 2026 **1 740** (até 17/09).
Itens por pedido: mín. **1**, máx. **56**, média **≈ 2,6**.

Top clientes por valor (itens): LINOFORTE MÓVEIS (142 pedidos), GRUPO K1 (várias filiais),
TOPAZIO, MARANHÃO COLCHÕES, TOPPING ESTOFADOS, U G COLCHÕES DA AMAZÔNIA.
Top produtos: **VELUDO SILVER** (`000020`), **VELUDO CONFORT** (`000014`), **VELUDINHO** (`000015`),
**VELUDO GOLD** (`000013`), **VELUDO JAGUAR** (`000019`), BELGA, VELUDO BOUCLE NICE, MICRO SIDE.

## 4. `Car_Itens_Pedido` (itens)

- **PK**: `Empresa + Pedido + Item(int)`. **FK** `(Empresa,Pedido) → Car_Pedido` e
  `(Cor,Fornecedor,Tipo_Fornec) → Car_Cores_Fornec`.
- **Índices**: `Ind_Car_Itens_Pedido[Empresa,Produto,Situacao,Cor,Desenho,Categoria]` e variante
  com `Variante` (para busca de produto acabado por grade).
- **Chave do item**: `Produto char(6)` + `Situacao char(3)` + `Cor char(5)` + `Desenho char(5)` +
  `Variante char(5)` + `Categoria char(2)` + `Largura char(6)`.
- **PK do produto**: `Produto` é PK **da empresa de produto** (`01`, via `Liv_Diario`), enquanto o
  pedido é da empresa `13` (ver §9).

### 4.1 Domínios

| Coluna | Valores | Legenda |
|--------|---------|---------|
| `Status_Item` | `''` 20 743 · `E` 20 481 | **Aberto** / **Encerrado** (calculado pela trigger) |
| `Tipo` | NULL 21 759 · `I` 18 075 · `A` 1 390 | Item de **Inventário**/Venda e **A**certo/ajuste |
| `aprovado_comercial` | `N` 23 113 · `S` 17 955 | Aprovação comercial do item |
| `Liberado` | `N` 40 917 · NULL 307 | Nunca liberado (flag pouco usada) |
| `Unid` / `Unid_Fat` | `MT` (metros) predominante; `KG` 6 | Unidade de pedido × faturamento |
| `Tipo_Fornec` | sempre NULL | Não usado |

### 4.2 Colunas (agrupadas)

- **Comercial**: `Produto`, `Situacao`, `Cor`, `Desenho`, `Variante`, `Categoria`, `Largura`,
  `Produto_Cliente`, `Produto_Cliente`, `Qtde`, `Vr_Unitario`, `Vr_Unitario2`, `Vr_Total`,
  `Classificacao`, `Comissao`, `ComissaoS`, `Vr_Desconto`, `Porc_Desconto`, `desc_porc`,
  `acres_porc`, `preco_orig`, `preco_err`, `categ_err`.
- **Expedição/faturamento**: `Qtde_Romaneio`, `Qtde_Acerto`, `Data_Acerto`, `Usuario_Acerto`,
  `Qtde_Fat`, `Vr_Unitario_Fat`, `Unid_Fat`, `Distrib_MetrosIn`, `Distrib_MetrosFn`.
- **Tabela de preço/rentabilidade**: `cod_tab_preco`, `val_tabela_preco`, `val_tabela_preco_total`,
  `dif_val_tabela_preco`, `dif_perc_tabela_preco`, `PercRentabilidade`,
  `AprovadoComercialRentabilidade`, `MotivoReprovaRentabilidade`, `PercImpostos`, `CustoProduto`,
  `Peso_Padrao`, `Nro_Unidades`, `perc_min_aprovacao`.
- **Aprovação**: `aprovado_comercial`, `dt_ver_aprov_com`, `Liberado`, `comissao_manual`.
- **Serviço**: `Vr_Unit_Servico`, `Vr_Unit_Prod_Aplicado`.
- **Datas**: `Data_Entrega`, `DtEntrega`, `Data_Previsao_Fabril`, `estoque_dt`.
- **Estoque (e-commerce/integração)**: `estoque_existe`, `estoque_ped_nu`, `estoque_item_nu`.

## 5. `Car_Vend_Pedido` (vendedor do pedido)

- **PK**: `Empresa + Pedido + Vendedor(char 3)`. FK para `Car_Pedido`.
- Colunas: `Tipo_Comissao char(1)`, `Porc_Comissao`, `Porc_ComissaoS`.
- 15 774 linhas para 15 799 pedidos → praticamente **1 vendedor por pedido**
  (vendedor também em `Rec_Vendedores`, Estudo 27).

## 6. Satélites do pedido

| Tabela | PK | Papel |
|--------|----|-------|
| `Car_Obs_Pedido` | `Empresa+Pedido` | quase 1:1 com o pedido (15 779 p/ 15 799); `Observacao_1..10` (60) e `ObsCarteira_1..13` (50) |
| `Car_Pcs_Pedido` | `Empresa+Pedido+Item+Peca` | fracionamento do item em peças: `Qtde`, `Metragem`, `Qtde_Romaneio` |
| `Car_ItensPedido_PorDataEntrega` | `ID` | item × `DataEntrega`/`Qtde` (entregas parciais programadas) |
| `Car_ItensPedido_Resumo` | `ID` | `QtdePedido`, `Reservado`, `Separado`, `DataFabril` por item |
| `Car_Itens_Modificados` | `Empresa+Pedido+Item+Seq` | **auditoria do item** (`Tipo` `A` 14 409 / `D` 994; `Usuario`, `Data`, `Hora`) |
| `Car_Itens_Pedido_Cancelado` | `Empresa+Pedido+Item` | cancelamento de item com `Motivo(250)`, `Usuario`, `Data_Hora` (89 linhas; 2025–2026) |
| `CAR_ITENS_CARTEIRA_DATA_PREVISAO_LOG` | `ID` | log de alteração de previsão (`Data_Anterior`→`Data_Atual`, `Usuario`) |
| `Car_AltPosicao` | `Empresa+Pedido+Sequencia` | alteração de “posição”/ordem (`PosIni`, `PosFim`, `Observacao`) |
| `Car_AnexosNFE_Cliente` | `Cliente` | flags de layout fiscal por sistema (`SIMCarteira_Venda`, `..._Remessa`, `..._Fio`, `..._Fardo`, `SIMTecidos_Urdume`) |
| `Car_Perfil` / `_Filtro` / `_Valor` | `Id` | perfis e filtros salvos por tela (`Grid_Visual1.*`) |
| `Car_Consulta_Geral` / `_Param` / `_Script` | `ID` | catálogo de consultas gerais parametrizáveis (`Descricao`, `Sistema`) |
| `Car_Pedido_Log` / `Car_Itens_Pedido_Log` | `Log_Seq` | **logs vazios** (mirror das tabelas; `Log_Data`, `Log_Tipo`) |
| `Car_Pedido_Romaneio` | `ID_PedRom` | vínculo pedido×romaneio (**vazio**; relação real via `Car_Itens_Romaneio`) |

## 7. Tabela de preço (`CAR_TABELA_PRECO`)

Cabeçalho (`ID int`) + satélites por **produto**, **dia**, **região fiscal**, **vendedor**,
**cliente** e **figura fiscal** (detalhada no Estudo 17):

| Tabela | Linhas | Chave |
|--------|-------:|-------|
| `CAR_TABELA_PRECO` | 9 | `ID`; `EMPRESA`, `COD_TABELA`, `DESCRICAO`, `DT_VIGENCIA`, `ATIVO`, `CLASSIFICACAO`, `tx_juros_diaria`, `dias_carencia` |
| `CAR_TABELA_PRECO_PRODUTO` | 18 | `ID` → `ID_CAR_TABELA_PRECO`; `PRODUTO`, `EMP_PROD`, `SITUACAO/COR/DESENHO/VARIANTE` |
| `CAR_TABELA_PRECO_PRODUTO_VALOR` | 104 | `ID` → produto × `ID_CAR_TABELA_PRECO_DIA`; `VALOR` |
| `CAR_TABELA_PRECO_DIA` | 55 | `ID` → tabela; `NUM_DIA` (0, 30, …) + `PORCENTAGEM` |
| `CAR_TABELA_PRECO_REGIAO` | 20 | tabela × `ID_REGIAO_FISCAL` |
| `CAR_TABELA_PRECO_VENDEDORES` | 8 | `ID`+`ID_CAR_TABELA_PRECO`+`CODIGO_VENDEDOR` |
| `car_tabela_preco_figura` | 40 | tabela × `id_figura_fiscal` |
| `CAR_TABELA_PRECO_CLIENTE` | 0 | tabela × `CODIGO_CLIENTE` (não usado) |
| `Car_Tabela_Preco_Controle_ID` | 1 | contadores de ID de cada satélite |

- A **resolução de preço** (produto → região × tabela × dia; desconto por vendedor/cliente) está
  descrita no Estudo 17. No pedido, o preço aplicado é persistido em `Car_Itens_Pedido.Vr_Unitario`
  e o de referência em `val_tabela_preco` (permite auditar desvios via
  `dif_val_tabela_preco`/`dif_perc_tabela_preco`).

## 8. Views (o “contrato pronto” da carteira)

| View | Linhas | Conteúdo |
|------|-------:|----------|
| `VW_Car_Pedido` | 15 734 | Pedido + **totais** (`Qtde_Itens`, `Qtde_Total_Pedido`, `Vr_Total_Pedido`), `Status_Pedido_Desc` (1 Em Análise / 2 Aprovado / 3 Cancelado / else Programado) e `Tipo_Pedido_Descricao` (via `Fat_Parametros.Tipo_Pedido_1..5`) |
| `Vw_Car_Itens_Pedido` | 41 224 | Item + **descrições** (`Produto_Descricao`, `Situacao_Descricao`, `Cor_Descricao`, `Desenho_Descricao`, `Categoria_Descricao`, `Variante_Descricao`) e **`Qtde_Saldo`** |
| `VW_Car_Pedido_Aberto` | 20 712 | Itens com `Status_Item <> 'E'`, pedido `Status <> 3` e `Status_Ped <> 'E'`; `Qtde_Saldo`, `Vr_Class` (classificação especial) |
| `VW_CarPedidosEmAberto` | 159 | **Saldo > 0**, com razão social, produto, vendedor, QMP e `VR_TotalAberto` |
| `VW_Car_Pedido_Aprov` | 33 402 | Fila de aprovação (join pedido×item) |
| `VW_RB_Car_Pedido` | 15 799 | Espelho do cabeçalho (Relatório Builder) |
| `VW_RB_Car_Pedido_Status` | 4 | Dicionário fixo de status (1–4) |
| `VW_RB_Car_Itens_Pedido` / `VW_Car_Itens_Romaneio` | 41 224 / 274 402 | Espelhos p/ relatórios e romaneio |
| `Vw_Saldo_Pedido_Carteira_Qlik` | 123 | Saldo agregado por produto/grade para Qlik, com `Descr_Linha` (via `Produtos_Tecidos.Linha` → `Car_Linha`) e `Descr_Tipo_Pedido` |

> **Achado**: `Vw_Car_Itens_Pedido` e `Vw_Saldo_Pedido_Carteira_Qlik` fazem
> `Join Liv_Diario LD ON LD.Empresa = CI.Empresa` para, em seguida, casar
> `Produtos ON Produtos.Empresa = LD.Empresa_Produtos`. É o mecanismo que liga a **empresa de venda
> (`13`)** à **empresa de produto (`01`)** — ver §9.

## 9. A ponte empresa de venda ↔ empresa de produto (`Liv_Diario`)

`Liv_Diario` tem **1 linha por empresa** (5 linhas) e mapeia `Empresa → Empresa_Produtos`
(todas apontam para `01`):

| Empresa | Empresa_Produtos |
|---------|------------------|
| 01/02/03/13/14 | 01 |

Consequências (importante para o ETL/Neon):
- Pedidos e clientes estão sob a **empresa 13**; produtos são cadastrados sob a **empresa 01**.
- Para resolver descrição/linha/unidade de um produto do pedido é preciso ir por `Liv_Diario`.
- Ao portar para o Neon, materializar essa dimensão (`dim_empresa_produto`) evita repetir o “hack”
  em cada query.

## 10. Procs, triggers e funções

- **Triggers (ativas) sobre o pedido** (Estudo 16):
  `TG_InsUpdDel_Car_Itens_Pedido_Status` (recalcula `Status_Item`/`Status_Ped`),
  `TG_Car_Pedido_Reserva`, `TG_Car_Itens_Pedido_Cancelado_Reserva`,
  travas de fechamento mensal (`*_Fechamento_Mensal`), logs (`*_Log`) e distribuição
  (`tg_Del_Distribuicao`, `tg_Del_Itens_Distribuicao`).
- **`Car_Itens_Pedido_Cancelado`** tem a trigger `TG_Car_Itens_Pedido_Cancelado_Reserva`
  (devolve reserva de estoque ao cancelar o item).
- **64 procs** referenciam `Car_Pedido`. As mais relevantes para a API:
  - Fluxo comercial: `SP_Car_AprovaPedAnalise`, `SP_Car_Pedido_Aprovacao_Financeira`,
    `SP_Car_Gera_Consiste`, `SP_Car_CorteDistribuicao`, `SP_Car_ForadeLinha`,
    `SP_Car_GeraPedidoSeparacao`, `SP_Carteira_Visualizando`, `sp_carCopiaPedidoCarteira`.
  - Faturamento/expedição: `sp_Fat_CarPedido`, `SP_GeraRomVenda`, `sp_Distribui`,
    `sp_InsereCarDistribuicao`.
  - Consulta: `SP_Car_Rel_APedido`, `sp_cfcRelSaldoPedCarteiraUni`, `SP_ProntaEntrega`,
    `SP_Rec_CarteiraEmAberto`, `sp_fluxo_ContasAReceber`.
  - Relatórios: `SRPT_PONTUALIDADEENTREGA`, `SRPT_PREVISAOFATURAMENTO`,
    `SRPT_RELPRODUTIVO`, `SRPT_RELVENDAS`.
  - Integrações/verticais: `SP_PLM_*`, `SP_FIO_PCP_*`, `SP_Tnt_*`.

## 11. Regras e recomendações para a API / ETL

1. **Somente leitura**: a nova API nunca escreve em `Car_*`; `Status_Item`, `Status_Ped` e as
   reservas são **campos calculados por trigger** — não replicar em UPDATE.
2. **Chaves**: `Empresa char(2)` + `Pedido char(8)` (padding à direita/zeros à esquerda). No Neon,
   normalizar para `text` sem padding ou manter colunas `char` equivalentes — decidir no schema
   `core`.
3. **Saldo do item** deve sempre ser derivado: `Qtde - Qtde_Romaneio - Qtde_Acerto`.
4. **Descrições**: preferir materializar dimensões (`produto`, `situacao`, `cor`, `desenho`,
   `variante`, `categoria`, `classificacao`, `vendedor`) no `core` em vez de repetir os `LEFT JOIN`
   das views.
5. **Área x produto**: usar `Liv_Diario` (`Empresa→Empresa_Produtos`) como dimensão, não como
   join por linha.
6. **Watermark sugerido** (carga incremental): `Car_Pedido.DataHora_Alteracao`/`Data_Pedido` +
   `Car_Itens_Modificados.Data/Hora` para o detalhe; `CAR_ITENS_CARTEIRA_DATA_PREVISAO_LOG.ID` para
   log de previsão.
7. **Não usar**: `Car_Pedido_Log`/`Car_Itens_Pedido_Log` (vazios), `Car_Pedido_Romaneio` (vazio),
   tabelas de distribuição/OS (vazias) e `Politica`/`Marcacao_cd`/`Status_Email` (não usados).

## 12. Gotchas encontrados

- **`VW_Car_Pedido` perde 65 pedidos** (15 734 vs 15 799) por usar `INNER JOIN Car_Itens_Pedido`
  — pedidos sem itens não aparecem.
- **`Vw_Car_Itens_Pedido` só preserva 41 224 linhas** porque `Liv_Diario` tem **1 linha por
  empresa**; se alguém inserir mais de uma linha por empresa, a view **multiplica** os itens.
- `Car_Itens_Pedido` **não tem coluna `Cliente`** (só o cabeçalho) — joins por cliente precisam
  passar por `Car_Pedido`.
- `Car_AltPosicao` tem linhas com `Empresa`/`Pedido` em branco (exceções de crédito sem pedido).
- `Car_Itens_Pedido.Tipo`: `I` 18 075 / `A` 1 390 / NULL 21 759 — não confundir com
  `Car_Itens_Modificados.Tipo` (`A`/`D`), que é auditoria.
- `Car_Romaneio.Tipo` é `V` (venda) e o vínculo real com o pedido é por
  `Car_Itens_Romaneio` (Estudo 25), não por `Car_Pedido_Romaneio` (vazia).

## 13. Próximos passos do módulo

- **Faturamento**: `Fat_Pedido` / `Fat_Itens_Pedido` / `Notas_Fiscais_Rec` (Estudos 04, 05) —
  como `Qtde_Fat`/`Vr_Unitario_Fat` do item viram NF.
- **Aprovação de crédito**: `SP_GESTOR_ANALISE_CREDITO`, `Car_AltPosicao`, `Car_MotivoReprovaCred`
  (a decodificar junto ao financeiro).
- **Preço**: fechar a cadeia `CAR_TABELA_PRECO*` (Estudo 17) com a aplicação no item.
