# Estudo 24 — Endereçamento de peças (“gavetas”), base para WMS e COMEX/packing list

Levantamento de **estrutura** (tabelas, colunas, flags, views, procs e **contagens/agregados**) por
`SELECT` somente leitura. Nenhum dado sensível. Objetivo: mapear **tudo** sobre o endereço físico
das peças — que no Microdata se chama **gaveta** — e as fundações já existentes para um futuro
**WMS** e para um módulo de **comércio exterior (packing list/di)**.

## 1. Síntese

| Tema | Situação | Objetos |
|------|----------|---------|
| Endereço (gaveta) | **Em uso** — endereço é texto na peça | `Cte_Gaveta`, `Cte_GrupoGaveta`, `Cte_Peca.Gaveta` |
| Histórico de movimento de gaveta | **Em uso** | `Cte_Peca_Gaveta_Log` (107 921) via trigger |
| Operação por coletor (palm) | **Em uso** (dados correntes) | `CTE_PalmGav_Log` (213 527), `CTE_PalmGav_Cx_Log` |
| Picking/recebimento por terminal | **Parcial** | `Car_Coleta` (115), `Car_ColetaCriterioInv` |
| WMS de volumes (recebimento/expedição) | **Modelado, não usado** | `retVolumes`, `retVolumeRomaneio`, `retVolumeBaixas`, `retParam*` |
| Bloco/terminal → gaveta | **Não usado** | `CTE_BlocoGaveta` |
| Fardos/carrolões | **Estrutura pronta, vazia** | `Cte_Fardo`, `Fat_Pecas_fardo`, `Fio_Fardos`… |
| COMEX (DI/aviso) | **Em uso no recebimento de importação** | `Ret_Aviso_*`, `Fat_XML_DI(_embalagem)`, `CMT_LocalDesembaraco` |
| “Packing list” | **Dois sentidos distintos** (§8) | `SP_FAT_EDI_PACKING_LIST` (EDI cliente) × embalagem da DI |

> ⚠️ Não confundir com falsos positivos: `Car_AltPosicao` (4 801) é **histórico de status do
> pedido** (“posição” = estágio), `ENDERECO_SPED` (1 661) é **endereço de participante**
> (fiscal/cobrança/entrega), e `Deposito` (0) é uma tabela de produto/custo, não de armazém.

## 2. A “gaveta” = endereço físico da peça

### 2.1 `Cte_Gaveta` (741 linhas, 7 colunas)

| Coluna | Papel |
|--------|-------|
| `Codigo` `char(10)` | **PK lógica** do endereço |
| `Descricao` | Rótulo legível |
| `GrupoGaveta` | FK → `Cte_GrupoGaveta` (zona) |
| `Setor` | Código de setor (`003` em 739 de 741) |
| `Faz_Sugestao` `S/N` | Entra no algoritmo de sugestão de endereço |
| `Estoque_Plano` `S/N` | Área de estoque “plano” (picking) |
| `confirmarTransferencia` `S/N` | Exige confirmação ao mover |

**Código do endereço** — dois formatos coexistem:
- **Coordenada (725 de 741)**: 10 caracteres no padrão `AA.BB.CC.D`
  (ex.: `01.00.01.0`, `10.10.10.0`). São **4 níveis hierárquicos**, porém **não há metadados**
  no banco dizendo o significado de cada nível (rua/coluna/prateleira/nível) — é convenção de
  operação. No Neon, o código deve ser **decomposto em 4 colunas** com semântica explícita.
- **Nomeada (16)**: `PACKLIST`, `AVARIA 01/02/03`, `RACK 01 PQN`, `RACK 02 PQ 4`,
  `SEPARACAO 06/07`, `DEVOLUCOES`, `CONFERENCIA`, `INVENTARIO01/02`, `LOTE_MISTO`/`LM`,
  `ROMANEIOS PEDIDOS`, `9999`.

Uso das flags (agregado): `Faz_Sugestao='S'` e `Estoque_Plano='S'` em **740** de 741 (só 1 com
`Faz_Sugestao='N'`); `confirmarTransferencia='N'` em todas. Setores: `003`=739, `000`=1, `002`=1.

### 2.2 `Cte_GrupoGaveta` (9) = **zonas do armazém**

| Código | Descrição | Leitura |
|--------|-----------|---------|
| 01 / 02 / 03 | DEPÓSITO 01 / 02 / 03 | Armazéns |
| 04 | PRODUÇÃO | WIP |
| 05 | TRANSPORTE | Expedição/trânsito |
| **06** | **CANAL VERDE** | Recebimento liberado (inspeção) |
| **07** | **CANAL VERMELHO** | Recebimento retido (inspeção) |
| 08 | ETIQUETAGEM | Embalagem/etiquetagem |
| 99 | INVENTARIO | Contagem |

`Cte_GrupoGaveta` só tem `Codigo`/`Descricao` — é a “zona” do WMS.

### 2.3 Ocupação atual (agregados)

- `Cte_Peca`: **297 044** peças (Situacao `001`), **653 gavetas distintas**, **108 860 sem gaveta**.
- Por grupo (join peça→gaveta→grupo): **DEPÓSITO 01 = 62 510 peças / 649 gavetas**;
  INVENTARIO = 8. Os demais grupos não têm peças.
- **`PACKLIST` sozinha concentra 125 661 peças** (13 produtos) — e **não pertence a nenhum grupo**
  (`GrupoGaveta` = NULL). É a **área de *staging* da importação/recebimento**, não um endereço
  hierárquico.
- Top endereços coordenados ocupados: `007` (2 597), `001` (1 060), `10.10.10.0` (402),
  `10.10.01.0` (439), `01.01.01.0` (330)…

### 2.4 A peça carrega o endereço

`Cte_Peca` (Estudo 19) tem, além do endereço: `Gaveta`, `Nro_Rolo_Origem` (NULL = rolo primário;
preenchido = peça derivada de rolo), `Sublote`, `Situacao`, `Aviso`/`Item_Aviso` (217 avisos
ligados), `Num_Etq_Aux` (etiqueta), `CodAcond`, `Tear`, `Nro_Rolo`/`Nro_Peca`.
**`Nro_Fardo`/`Carrolao` estão 100 % vazios** (297 044 sem fardo e sem carrolão) — não há
agrupamento em fardos hoje.

**Rastreabilidade de movimento** — `Cte_Peca_Gaveta_Log` (**107 921**):
`Empresa, Nro_Rolo, Nro_Peca, Situacao, Item, Data_Hora, Gaveta_Anterior, Gaveta_Atual`,
mantido pela trigger `TG_DELINSUPT_Cte_Peca_Gaveta_Log`. **É o ledger de movimentação de endereço.**

## 3. Operação por coletor (palm) — o WMS que já roda

`CTE_PalmGav_Log` (**213 527**) — movimentos feitos no coletor:
`ID_Empresa, ID_PalmGav, Nro_Rolo, Nro_Peca, Flag_Tipo, Data_Hora, Operador,
Gaveta_Origem, Gaveta_Destino, terminal`. Dados **correntes** (período 12/06/2025 → 17/09/2026).

- `terminal`: **01 = 131 774**, **02 = 81 753** (dois coletores ativos).
- `Flag_Tipo`: **G = 130 720**, **V = 82 807** (G/V distinguem o tipo de operação; não há
  documentação no banco — validar com a operação).
- Principal `Gaveta_Destino`: **`PACKLIST` (38 654)** — confirma que o coletor é usado sobretudo
  para dar entrada/mover no *staging* de importação.
- `CTE_PalmGav_Cx_Log` (0) — versão por **caixa de fios** (não usada).

Outros objetos de coleta:
- `Car_Coleta` (115) / `Car_Coleta_Log` (0): coleta de peças para pedido — `Coleta, Seq, Etiqueta,
  Tipo, Pedido, Metros, Quilos, Terminal, Critica_OK, Critica, Tinturaria, Lote,
  Ordem_Separacao, Rolo_Coletado, Peca_Coletada`.
- `Car_ColetaCriterioInv` (0): coleta por inventário (`Terminal, Gaveta, Produto, Situacao, Cor,
  Desenho, Variante, Categoria, SomenteCru, SomenteTinto`).
- `Car_Romaneio_Coleta` (0) / `Car_Itens_Romaneio_Coletado` (0) / `Cte_RomaneioColetor_Itens` (0):
  separação por romaneio/terminal (`OrigemColeta`, `Quantidade_Coletada`).
- `CTE_BlocoGaveta` (0): `Empresa, Terminal, CodigoBloco, CodigoGaveta` — **mapeamento
  terminal → bloco → gaveta** planejado e não usado (útil para direcionar put-away por coletor).
- `Vw_Pecas_Nao_Coletadas`: peças não baixadas nem coletadas, join com descrições de gaveta,
  situação, cor, desenho, variante e categoria (base pronta para tela de coleta por inventário).
- `VW_CTE_Mov_Fios_SaldoGav`: saldo de fios por gaveta (usa `Cte_Gaveta.Setor`/`Codigo`).

## 4. Picking / endereçamento para atender pedido

- **`uspEnderecamentoParaAtenderPedidoGeral`** (usado pela API legada, Estudo 20) — para cada
  item do pedido seleciona rolos de `Cte_Peca` com `Nro_Rolo_Origem IS NULL`, **sem** baixa em
  `CTE_Baixa`, ordenando por **`Gaveta, Tear DESC, Nro_Rolo DESC`** e devolvendo, por item,
  `Gavetas`, `Rolos`, `Qtde_Pecas`, `Total_Metros`, `Sublote`. É a **regra de picking atual**.
  Relacionados: `uspEnderecamentoParaAtenderPedido(_Master)`, `uspColetaEnderecamento`,
  `uspLocalizarEstoquePorPedido`, `SP_GESTOR_PAINEL`, `VW_GESTOR`, `VW_GESTOR_PCP`
  (estes últimos usam `Faz_Sugestao` para sugerir endereço).
- `SP_Car_Gera_RomTransf`, `SP_CTE_ConsEst_Pecas/Fardos/Fios/Tintur`, `SP_Consulta_Peca` também
  leem `Cte_Gaveta`.
- No `DBProDash`: `uspEnderecamentoParaAtenderPedido*`, `uspColetaEnderecamento*`,
  `uspLocalizarEstoquePorPedido`, `uspRetornaSolicitacaoCarga`, `uspSolicitacaoCargaMoven`
  (Estudo 21).

## 5. Modelo de volumes (WMS de recebimento/expedição) — pronto, não usado

- **`retVolumes` (0)**: `volumeId, empresa, documento, serie, fornecedor, tipoFornecedor, data,
  empProd, produto, produtoReferenciado, qtde, vrUnitario, volumeIdOrigem, dataHora, itemDocto,
  lote, **gaveta**, nroLancto` → volume de recebimento **já com endereço (gaveta)**.
- `retVolumeRomaneio` (0): volumes de expedição por romaneio/cliente/destino.
- `retVolumeBaixas` (0): baixa de volume por operador/setor (`setor`, `dataHora`).
- Parâmetros: `retParamGrupoVolumes`, `retParamGrupoGavVolumes` (**grupo gaveta** p/ volume),
  `retParamDestinoVolumes`, `retParamBaixaAutoVolumes`.
- `PCP_Volume_Romaneio` (0): volume/lote/código de barra por pedido (com trigger
  `TG_INS_PCP_Volume_Romaneio`); `PCP_Inventario_Volume` (0).
- Views: `vw_RetVolumeSaldos`, `vw_RetVolumeRomaneio` (romaneio/volumes — branch “tcs31”, 2017).

> Nada disso tem linhas: o desenho de **WMS de volumes por romaneio** existe, mas a operação
> ficou na **peça** (`Cte_Peca.Gaveta`) + **coletor** (`CTE_PalmGav_Log`).

## 6. Fardos / carrolões / etiquetas

- `Cte_Fardo` (0): `Empresa, Nro_Fardo, Data_Entrada, Qtde, Metros, Peso, Operador, Data_Hora`.
- `Fat_Pecas_fardo` (0) / `Cfc_Pecas_fardo` (0) / `Tnt_Pecas_Fardo` (0): peças por fardo.
- `Fat_Param_FreteFardos` (0): frete por tipo de fardo (dentro/fora) — insumo de frete.
- Etiquetas: `SP_CFC_Imp_EtiquetaFardo`, `sp_Cte_ImpressaoEtiquetaFardos`, `SP_Fat_Embalagem_Etiqueta`,
  `SP_Fat_Embalagem*`, `SP_PCP_Etiqueta_Embalagem`, `SP_PCP_GeraRomaneio_Embalagem`,
  `VW_CTE_Campos_Layout_Embaladora`; `FNC_GerarEAN13` (código de barras).
- Fios (yarn, módulo vazio): `Fio_Fardos`/`Fio_Fardo_OP`/`Mistura_Fardo*` e triggers de fardo.
- `Car_Itens_Romaneio_Coleta`, `Model_PCP_PalletEmbalagens_{Dados,Titulos}` (0) — pallet/embalagem.

## 7. COMEX / importação — endereço, aviso e DI

### 7.1 Aviso de recebimento (base do receiving de importação)

- **`Ret_Aviso_Recebimento`** (218): `Empresa, Aviso, Tipo_Fornecedor, Fornecedor, Nr_NFE, Serie,
  Data_Receb/Data_Hora_Receb, Tipo, Operador, Codigo_Moeda, Data_Cambio, Revisado,
  MoedaVrAduaneiro, **DataRegistroDI, Path_XML, Arquivo_XML**, Historico,
  **IdLocalDesembaraco, Processo, Chave_Acesso, VrAFRMM, VrATAERO, Vr_Frete**, Status,
  Empresa_Fat, Facionista, StatusColeta, Data_Lancamento`.
- **`Ret_Aviso_ItensRecebimento`** (2 083): `…, Qtde, Metros, Peso, **Peso_Bruto**, QMP,
  Vr_Unitario, **Vr_Moeda_Estrangeira, Vr_Unitario_Compra**, Vr_Total, Grade, Impostos
  (IPI/ICMS/PIS/COFINS), **Embalagem**, **Qtde_Rolos**, Categoria, Desenho, Variante, Sublote?,
  **Fk_PCP_Acondicionamento**, produtoReferenciado, StatusColeta`.
  → **Contém os campos típicos de packing list**: embalagem, quantidade de volumes (rolos) e
  peso bruto.
- **Local de desembaraço** `CMT_LocalDesembaraco` (2): `ITAJAI/SC` e `NAVEGANTES/SC` (marítimo).
  3ª parte do vínculo: `Ret_Aviso_Recebimento.IdLocalDesembaraco`.
- Conciliação aviso↔pedido: `Ret_Aviso_Itens_Pedido_Atend` (2 083) e views
  `vw_Ret_Aviso_Itens_Pedido_Atend(_Ant)` (Estudo 20).

### 7.2 DI (Declaração de Importação)

- **`Fat_XML_DI` (1, 87 colunas)** — cabeçalho da DI, incluindo:
  `armazenaRecintoAduaneiroCodigo/Nome`, `armazenamentoSetor`, **`canalSelecaoParametrizada`**
  (canal verde/amarelo/vermelho do despacho), `caracterizaOperacao*`, `cargaDataChegada`,
  `cargaNumeroAgente`, `cargaPaisProcedencia*`, **`cargaPesoBruto`, `cargaPesoLiquido`**,
  `cargaUrfEntrada*`… (carga = carga marítima).
- **`Fat_XML_DI_embalagem` (1)**: `id, idEmpresa, idDI, **codigoTipoEmbalagem, nomeEmbalagem,
  quantidadeVolume**` → **packing list estruturado da DI** (tipos/quantidade de volumes).
- `Fat_XML_DI_armazem` (0): `idDI, nomeArmazem` (armazém do recinto alfandegário).
- Itens de DI (produto/imposto): `Fat_Itens_Pedido_DI` + `_Adic` (2 473) e `Liv_EntProd_DI` +
  `_Adic` (2 427) (Estudo 20). `CMT_ParamCFOPEmbalagem` (0).

> O volume de dados de `Fat_XML_DI` é baixo (1 linha) — o **recebimento de importação vigente
> é operado pelo `Ret_Aviso_*` + `Liv_XML`**, com o `Fat_XML_DI` guardando o detalhe aduaneiro
> quando preenchido.

### 7.3 “Packing list” — dois significados (importante)

1. **Packing list de importação** = campos de embalagem/peso/volumes de `Fat_XML_DI_embalagem`
   + `Ret_Aviso_ItensRecebimento` (`Embalagem`, `Qtde_Rolos`, `Peso_Bruto`) — **é o que serve ao
   módulo de comércio exterior**.
2. **`SP_FAT_EDI_PACKING_LIST`** (nomenclatura enganosa) = **packing list de EDI do cliente**
   (automotivo), lendo `Fat_Pedido`/`Fat_Itens_Pedido_Kanban`/`..._Ran` e `PCP_Clientes_EDI`,
   retornando `Numero_Kanban`, `Embalagens_kanban`, `Numero_Ran`, `Qtde_Ran`, `Expedidor`,
   `Doca`, `Ponto_Consumo`, `Pacote` — **não** é packing list de importação.
   Tabelas do EDI: `Fat_Itens_Pedido_Kanban` (0, tem `Deposito`/`Embalagens`),
   `Fat_Itens_Pedido_Kanban_Embalagem(_Vazia)` (0, pallets vazios).

### 7.4 Onde a importação “aterrissa” no estoque

A peça importada entra e, via coletor, é posicionada em **`PACKLIST`** (a gaveta *staging*),
que hoje concentra **125 661** peças. Os canais de inspeção **CANAL VERDE/VERMELHO** (grupos 06/07)
e os objetos de qualidade (`SIC_Disposicao`, `CTE_Disposicao`, `SIC_Lote_Inspecao*`) existem mas
estão **vazios** — a inspeção/liberação não é registrada no ERP.

## 8. Lacunas e recomendações para WMS + COMEX no Neon

Modelo atual: **endereço = string** na peça, sem hierarquia formal; movimento registrado em dois
logs (`Cte_Peca_Gaveta_Log`, `CTE_PalmGav_Log`). Para o WMS/COMEX no Neon, recomenda-se:

1. **Dimensão de endereço normalizada**: `address(id, zone_id, warehouse_id, level1..level4,
   code, type, picking, sugerivel, confirmar_transferencia)` — decompor `AA.BB.CC.D` em 4 níveis
   com nomes acordados (ex.: rua/coluna/nível/posição) e mapear as gavetas nomeadas
   (`PACKLIST`, `AVARIA`, `SEPARACAO`, `CONFERENCIA`, `INVENTARIO`…) como **tipos lógicos**.
2. **Zonas** (`zone`) a partir de `Cte_GrupoGaveta` (depósitos, produção, transporte, canais
   verde/vermelho, etiquetagem, inventário).
3. **Estoque por endereço** (`stock_by_location`) como fato derivado de `Cte_Peca` + `CTE_Baixa`
   (regra “peça em aberto”, Estudo 19), com quantidade e dimensões por endereço.
4. **Movimentação** (`stock_movement`) unificando `Cte_Peca_Gaveta_Log` (trigger) e
   `CTE_PalmGav_Log` (coletor) — `from_address`, `to_address`, `operator`, `terminal`, `at`,
   `type`. Portar as flags `G`/`V` após validar o significado.
5. **Operação de coletor** (`wms_task`): origem em `Car_Coleta`/`CriterioInv`/`RomaneioColetor`,
   com `terminal`/`operator`, conferência (`Critica_OK`) e status.
6. **Volumes/lotes (SSCC)**: reativar o desenho `retVolumes*`/`PCP_Volume_Romaneio` para
   volume→gaveta e **fardos** (`Cte_Fardo` + `Fat_Pecas_fardo`), com etiqueta/EAN
   (`FNC_GerarEAN13`).
7. **COMEX**: materializar `Ret_Aviso_Recebimento` (com `IdLocalDesembaraco`, `Processo`, II),
   `Ret_Aviso_ItensRecebimento` (packing list: embalagem/volumes/peso) e `Fat_XML_DI` +
   `Fat_XML_DI_embalagem` (packing list aduaneiro); modelar `duimp/DI`, `packing_list` e
   `packing_list_volume` como entidades próprias (hoje não há tabela de packing list de import).
8. **Não confundir** com `SP_FAT_EDI_PACKING_LIST` (EDI Kanban do cliente) nem com `ENDERECO_SPED`.

## 9. Objetos-chave deste estudo

- Endereço/gaveta: `Cte_Gaveta`, `Cte_GrupoGaveta`, `Cte_Peca.Gaveta`, `Cte_Peca_Gaveta_Log`,
  `CTE_BlocoGaveta`, `Cte_Gaveta_MPAuxiliares`, `Vw_Pecas_Nao_Coletadas`, `VW_CTE_Mov_Fios_SaldoGav`.
- Coletor/WMS: `CTE_PalmGav_Log`, `CTE_PalmGav_Cx_Log`, `Car_Coleta`, `Car_ColetaCriterioInv`,
  `Car_Romaneio_Coleta`, `Cte_RomaneioColetor_Itens`, `retVolumes*`/`retParam*`,
  `PCP_Volume_Romaneio`, `PCP_Inventario_Volume`.
- Picking: `uspEnderecamentoParaAtenderPedidoGeral`, `SP_GESTOR_PAINEL`, `VW_GESTOR(_PCP)`.
- Fardos/etiquetas: `Cte_Fardo`, `Fat_Pecas_fardo`, `Fat_Param_FreteFardos`,
  `SP_CFC_Imp_EtiquetaFardo`, `sp_Cte_ImpressaoEtiquetaFardos`, `FNC_GerarEAN13`.
- COMEX: `Ret_Aviso_Recebimento`, `Ret_Aviso_ItensRecebimento`, `CMT_LocalDesembaraco`,
  `Fat_XML_DI`, `Fat_XML_DI_embalagem`, `Fat_XML_DI_armazem`, `Fat_Itens_Pedido_DI`,
  `Liv_EntProd_DI`, `SP_FAT_EDI_PACKING_LIST` (EDI cliente).
