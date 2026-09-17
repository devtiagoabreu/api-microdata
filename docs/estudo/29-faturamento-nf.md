# Estudo 29 — Faturamento/Nota Fiscal (`Fat_*`, `Notas_Fiscais_*`, `Rec_*`)

Levantamento de **estrutura** (tabelas, colunas, PK/FK, índices, status, views, procs, triggers e
**contagens**) por `SELECT` somente leitura. Nenhum dado sensível. Objetivo: mapear a jornada do
pedido até a **nota fiscal**, o **livro fiscal**, a **duplicata** (contas a receber) e a **baixa**.

> Continua o [Estudo 28](./28-carteira-pedidos.md) (carteira). O lado fiscal/EFD já foi visto no
> [Estudo 18](./18-fiscal-liv-efd.md) e as contas a receber no
> [Estudo 05](./05-faturamento-contas-a-receber.md); aqui o foco é **capítulo a capítulo** do
> faturamento (`Fat_*`) com as amarrações e domínios decodificados.

## 1. Síntese

| Papel | Objeto principal | Linhas | Estado |
|-------|------------------|-------:|--------|
| **Consistência (pré-faturamento)** | `Fat_Consiste` + `_Itens_` + `_Parcelas` + `_Obs` | 11 399 / 86 295 / 29 097 / 11 392 | **Em uso** (snapshot da validação) |
| **Faturamento (cabeçalho da NF)** | `Fat_Pedido` | **12 653** | **Em uso** |
| **Itens faturados** | `Fat_Itens_Pedido` | **100 495** | **Em uso** |
| Natureza por pedido | `Fat_Nat_Pedido` | 12 651 | **Em uso** |
| Dados da NF-e | `Fat_Pedido_Dados_NFE` | 12 658 | **Em uso** |
| Forma de pagamento da NF | `Fat_Pedido_FormaPagto` | 12 289 | **Em uso** |
| Veículos (NF de veículo) | `Fat_Pedido_Dados_Veiculos` | 11 476 | **Em uso** |
| Vendedor/comissão da NF | `Fat_Vend_Pedido` | 11 852 | **Em uso** |
| Parcelas geradas no faturamento | `Fat_Parc_Pedido` | 29 868 | **Em uso** |
| **Livro fiscal de saída** | `Liv_Saidas` / `Liv_SaiProd` | 12 098 / 34 043 | **Em uso** (Estudo 18) |
| **Título a receber** | `Notas_Fiscais_Rec` | **11 739** | **Em uso** |
| Parcelas (duplicatas) | `Notas_Fiscais_Parcelas` | **29 885** | **Em uso** |
| Comissão por parcela/vendedor | `Notas_Fiscais_Vendedores_Parcelas` | 29 886 | **Em uso** |
| **Baixas (recebimento)** | `Rec_Baixas` (+ `Rec_Historicos`) | **28 903** (+19) | **Em uso** |
| Histórico NF-e | `Fat_NFe_Historico` | 161 428 | **Em uso** |
| Fila de emissão automática NF-e | `Fat_Estagio_NFe_Auto` | 12 100 | **Em uso** |
| Eventos NF-e | `Fat_NFe_Evento` / `Fat_Pedido_NFe_Eventos` | 240 / 622 | **Em uso** |
| Notas canceladas | `Fat_NF_Canceladas` | 152 | **Em uso** |
| Crédito de devolução | `Fat_Credito_DevolucaoNF` | 259 | **Em uso** |
| Recibo de comissão | `Fat_Recibo` | 893 | **Em uso** |
| Séries/numeração | `Fat_Serie` | 4 | Config |

O módulo `Fat_*` tem **302 tabelas**; boa parte é de verticais (Pneu, Kanban, Hub2b, RPS/NFS,
combustível) e está **vazia**. As colunas em negrito são as que sustentam o faturamento DGB.

## 2. Fluxo de faturamento (do pedido à baixa)

```
Car_Pedido / Car_Itens_Pedido                              (Estudo 28)
      │  consistência / crítica fiscal
      ▼
Fat_Consiste (+_Itens_Consiste,_Parcelas,_Obs)   ID_Consiste (Sistema 230 = SIMFatura)
      │  geração da NF
      ▼
Fat_Pedido (+ Fat_Itens_Pedido) ──Nosso_Pedido──► Car_Pedido.Pedido
   │        │  Fat_Nat_Pedido (natureza) · Fat_Pedido_Dados_NFE (NF-e) · Fat_Vend_Pedido
   │        ▼
   │   Liv_Saidas + Liv_SaiProd              (livro fiscal de saída / EFD)
   ▼
Notas_Fiscais_Rec ──► Notas_Fiscais_Parcelas ──► Rec_Baixas (+ Rec_Historicos)
   (título AR)          (duplicatas/vencimentos)     (recebimentos)
                    └► Notas_Fiscais_Vendedores_Parcelas (comissão)
```

## 3. `Fat_Pedido` — cabeçalho do faturamento

- **PK**: `Empresa char(2)` + `Pedido char(6)` (numeração **própria** do faturamento, diferente do
  `Car_Pedido char(8)`).
- **FKs**: `Cliente → Clientes_Principal`; `Empresa → Empresas`;
  `(Empresa, ID_Consiste) → Fat_Consiste`; `Cod_Liv_SPED_Modelo_Dcto → Liv_SPED_Modelo_Dcto`;
  `ID_Fat_Oper_Presencial → Fat_Oper_Presencial`; `IdIntermediadorPag → IntermediadorPag`.
- **Índices** (14, 1 PK): `PK_Fat_Pedido[Empresa,Pedido]`, `Ind_Nota[Empresa,Nr_Nota]`,
  `Ind_NroNota_Serie[Nr_Nota,Serie]`, `Ind_NrNota`, `Ind_Emissao[Empresa,Pedido,Data_Emissao,
  Status_Gravado,Flag_Emitido]`, `Ind_DtNota`, `Ind_EmpCliente`, `Ind_Fat_PedCli`,
  `Ind_Transfer[Empresa,Pedido_Transfer]`, `Ind_Fat_Pedido_Fat_Consiste`,
  `Ind_Fat_Pedido_Data_Manifesto`, `Emp_Ped_Cli_Dat_Flag`, `IND_Fat_Pedido_RELFISCCONTEST`,
  `Cliente`.
- **Período**: `Data_Emissao`/`Data_Nota` de **25/07/2018** a **17/09/2026**.
- **Valores**: `Vr_Nota` somando **R$ 312,7 mi**; `Qtde` 800 084; `Peso_Liquido` 35,6 mi.
- **Ligação com a carteira**: `Nosso_Pedido char(8)` → `Car_Pedido.Pedido`
  (**11 504 de 12 653**; os demais são faturamentos diretos — devolução, serviço, exportação).

### 3.1 Domínios

| Coluna | Valores | Legenda |
|--------|---------|---------|
| `Flag_Emitido` | `1` 12 633 · `0` 19 · `2` 1 | **1** = NF emitida (é o filtro das views de venda) |
| `Status_Gravado` | `S` 12 638 · `N` 15 | “Gravado” no livro/SPED |
| `Flag_Gravado` | `S` 12 262 · `N` 19 · NULL 372 | Espelho do status de gravação |
| `Ent_Sai` | `S` 12 328 · `E` 325 | **S** Saída (venda) · **E** Entrada (devolução/retorno) |
| `Tipo_Pedido` | `1` 11 862 · `4` 791 | Ver `Fat_Parametros` abaixo |
| `Frete_Conta` | `0` 7 729 · `1` 4 440 · `4` 451 · `9` 27 · `3` 6 | Conta do frete (0 = emitente, 1 = destinatário…) |
| `Consumidor_Final` | `N` 11 236 · `S` 1 057 · NULL 360 | Indicador NF-e |
| `Bloqueado` | `N` 12 653 | Nunca bloqueado |
| `Facionista` | `N` 12 293 · NULL 360 | Não é faturamento de faccionista |
| `Orcamento` | NULL 11 836 · `N` 817 | Não é orçamento |

**Legenda de `Tipo_Pedido` (do `Fat_Parametros`, não confundir com a da carteira!)**:
`Tipo_Pedido_1='Vendas'`, `Tipo_Pedido_2='Retorno'`, `Tipo_Pedido_4='Outros'` (3 e 5 vazios).
Ou seja, no faturamento: **1 = Vendas**, **2 = Retorno**, **4 = Outros**.

### 3.2 Colunas (agrupadas)

- **Identificação**: `Empresa`, `Pedido`, `Cliente`, `Cliente_Cobranca`, `Cliente_Triangulo`,
  `CNPJ_Entrega`, `Seu_Pedido`, `Nosso_Pedido`, `Nosso_Pedido2`, `Pedido_Transfer`, `Data_Emissao`,
  `Data_Nota`, `Nr_Nota`, `Serie`, `Serie_NF_Saida`, `NF_Saida`, `dh_Emissao`.
- **Totais**: `Vr_Nota`, `Soma_Itens`, `Vr_Total_Geral`, `Vr_Mercadorias`, `Vr_Despesas`,
  `Vr_Total_ItensAdic`, `Vr_Tot_DescProd`, `Vr_DescontoGeral`, `Vr_Desconto`, `Vr_Acrescimo`,
  `Vr_Frete`, `Vr_Seguro`, `Vr_MaoObra`, `Vr_MatPrima`.
- **Tributos**: `Base_ICMS`, `Vr_ICMS`, `Aliq_ICMS`, `Fator_ICMS`, `Base_IPI`, `Base_ICMS_Subst`,
  `Vr_ICMS_Subst`, `Vr_PISCOFINSCSLL`, `PORC_PISCOFINS`, `VR_PISCOFINS`, `VR_COFINS`,
  `PIS/COFINS` Suframa, e os grupos **IBS/CBS/IS** (reforma tributária: `vIBS*`, `vCBS`, `vIS`,
  `vBCIBSCBS`).
- **Frete/transporte**: `Cod_Transp`, `Des_Transp`, `Cod_Redesp`, `Des_Redesp`, `Placa_Transp`,
  `Local_Transp`, `Nr_Conhecimento_Transp` (CT-e), `Chave_Acesso_CTe`, `Emitir_Conhecimento`,
  `Despesa_Transp`, `Data_Entrega`, `dPrevEntrega`.
- **Serviço/ISS**: `Total_Servicos`, `Total_Servicos_ISS`, `Valor_ISS`, `Porc_ISS`,
  `Valor_IRRF`, `Base_IRRF`, `Nota_Cupom`, cupom fiscal (`ECF_Maquina`, `COO`).
- **Mensagens/observação**: `Cod_Mens1/2`, `Des_Mens1/2`, `Observacao text`, `Obs_OS text`,
  `Obs_Aux`.
- **SPED/fiscal**: `Cod_Liv_SPED_Modelo_Dcto`, `Natureza_Operacao`, `Classificacao`,
  `Ind_Pres`, `indIntermed`, `IdIntermediadorPag`.

## 4. `Fat_Itens_Pedido` — itens faturados

- **PK**: `Empresa + Pedido + Item(int)`; **FK** para `Fat_Pedido` e para `Fat_Itens_Consiste`
  (`(EmpresaConsiste, ID_Consiste, ID_ItensConsiste)`), além de `Fig_MotivoDesoner_ICMS`.
- **Índices** (7): `PK_Fat_Itens_Pedido[Empresa,Pedido,Item]`, `Ind_CodProd`/
  `Ind_Fat_Itens_Pedido_Cod_Produto`/`idx_Fat_Itens_Pedido_Cod_Produto`,
  `Ind_ClassFisc`, `IND_Fat_Itens_Pedido_ID_ItensConsiste`,
  `IND_Fat_Itens_Pedido_RELFISCCONTEST`.
- **Chave do produto**: `Cod_Produto char(6)` + `Situacao` + `Cor` + `Desenho` + `Variante` +
  `Categoria` + `Grade` + `Grade_Tam` + `Colecao`.
- **Base de cálculo** (`Base_Calc char(1)`): `-` 62 377 (linhas sem base / serviço — excluídas das
  views de venda) · `M` 38 085 (metros) · `Q` 26 (qtde) · `P` 7 (peso). A
  `VW_Fat_Itens_Pedido_ComQMP` converte para a unidade QMP do produto (`P`→Peso, `M`→Metros,
  senão Qtde).

### 4.1 Colunas (agrupadas)

- **Produto**: `Des_Produto`, `Cod_Produto`, `Cod_EAN_GTIN`, `Codigo_Produto_Concat`,
  `Descricao_Produto_Concat`, `Produto_Cliente`, `Unidade`, `UnidadeTributavel`,
  `QtdeTributavel`, `ValorUnitarioTributavel`, `FatorConversao`, `Redondo`.
- **Quantidades/preço**: `Qtde`, `Metros`, `Peso`, `Vr_Unitario`, `Vr_Unitario2`, `Vr_Total`,
  `Acres_Desc`, `Vr_Acrescimo`, `Vr_Desconto`, `Vr_DescontoProd`, `Vr_DescontoRateio`,
  `Preco_Tabela`, `Tabela`, `Indice`, `Vr_Indice`, `Acres_Unitario`.
- **Comissão/verba**: `Vr_Comissao`, `Comissao`, `ComissaoS`, `Premio`, `Verba`.
- **Fiscal**: `ClassFisc`, `Trib`, `NatOp`, `Seq`, `Aliq_ICMS`, `Vr_ICMS`, `Vr_BCICMS`,
  `Vr_ICMS_Subst`, `CSOSN`, `CEST`, `Regra_Fiscal`, `Regiao_Origem/Destino`, `Codigo_Grupo`,
  `CST_IBSCBS`, `idClassTribIBSCBS`, alíquotas **IBS/CBS/IS**.
- **Importação**: `Vlr_AFRMM`, `VrSiscomex`, `BC_IImp`, `Vr_IImp`, `Vr_DespAduaneira`,
  `Id_Cod_DIPAM`, `Id_Liv_ProdutosOrigem`.
- **PIS/COFINS/CSLL/INSS/IR/ISS**: pares `Porc_*`/`Vr_*` e `BC_PIS`, `BC_COFINS`.
- **Fardos/expedição**: `Fardos`, `Tipo_Fardo`.
- **Origem**: `Item_CarOrcamento` (liga ao item do orçamento), `Nosso_Pedido`,
  `Nr_Ped_Compra`/`Item_Ped_Compra`, `Ctrl_Emprest_Terceiros`, `ID_Fat_FCI`.

## 5. Satélites do faturamento

| Tabela | PK | Papel |
|--------|----|-------|
| `Fat_Nat_Pedido` (12 651) | `Empresa+Pedido+NatOp+Seq` | Natureza de operação por pedido (`Des_NatOp`, `CContabil`, `DIPI`); FK → `Liv_Natureza` |
| `Fat_Pedido_Dados_NFE` (12 658) | `Empresa+Pedido` | Dados da NF-e: emitente/destinatário/retirada/entrega/transporte, `Chave_AcessoNFe`, `Status`, `Protocolo_NFe`, `FinNFe`, `tpAmb`, `FormaEmissao`, `Emitido_Contingencia` |
| `Fat_Pedido_FormaPagto` (12 289) | `Empresa+ID` | Formas de pagamento da NF-e: `ID_Meio_Pagamento`, `ID_Cartao_Bandeira`, `Valor`, `NSU`, `CNPJPag`/`CNPJReceb` |
| `Fat_Pedido_Dados_Veiculos` (11 476) | `Empresa+Pedido` | Veículo novo vendido: `Placa`, `Montadora`, `DescrModelo`, `AnoFabricacao` |
| `Fat_Vend_Pedido` (11 852) | `Empresa_NF_Vendedores+Doc+**Parcela**+Vendedor` | Comissão por parcela (`TotalComissao`, `Porc_Comissao(S)`) |
| `Fat_Parc_Pedido` (29 868) | `Empresa+Documento+Parcela` | Parcelas projetadas no faturamento (vence., banco, agência, nosso número) |
| `Fat_Vend_Consiste` (12 828) | `Empresa+ID_Consiste+ID` | Vendedor no snapshot de consistência |

**FKs dos satélites**: `Fat_Nat_Pedido → Liv_Natureza`; `Fat_Pedido_FormaPagto → Fat_Pedido` e
`Meio_Pagamento`; `Fat_Pedido_Dados_NFE → Fat_NFe_Contingencia`, `Paises` (entrega/retirada);
`Fat_Vend_Pedido → Fat_Pedido` e `Rec_Comissoes` (vendedor/tipo).

### 5.1 `Fat_Pedido_Dados_NFE.Status`

| Valor | Qtde | Leitura |
|-------|-----:|---------|
| `1` | 12 109 | NF-e autorizada |
| `X` | 160 | Cancelada (≈ `Fat_NF_Canceladas` 152) |
| `0` | 25 | Rejeitada/não autorizada |
| NULL | 364 | Sem NF-e gerada |
| `tpAmb` | `1` 12 276 | Produção |
| `FinNFe` | `1` 12 586 · `3` 40 · `4` 32 | Normal / Ajuste / Devolução |
| `FormaEmissao` | `1` 12 214 · `6` 55 | Normal / SVC-AN |

## 6. Consistência (`Fat_Consiste*`) — o “pré-faturamento”

- `Fat_Consiste` (PK `Empresa+ID_Consiste`) é o **snapshot do pedido no momento da crítica**;
  `Fat_Pedido` guarda `ID_Consiste` (FK). `Sistema` = **230** (11 397; 2 em 170) e `Ent_Sai='S'`.
  Período 01/08/2018 → 17/09/2026 (inclusão em tempo real).
- Filhas: `Fat_Itens_Consiste` (86 295, com tributos), `Fat_Consiste_Parcelas` (29 097),
  `Fat_Consiste_Obs` (11 392, `text`), `Fat_Vend_Consiste` (12 828).
- **11 479** dos `Fat_Pedido` têm consistência ligada — a consistência é o *staging* interno da NF.
- Triggers: `TG_INSUPT_Fat_Consiste`, `Tg_Fat_DelConsiste`.

## 7. Livro fiscal (`Liv_Saidas` / `Liv_SaiProd`) — ligação

- `Liv_Saidas` (12 098, PK `Documento+Empresa+Serie`) — detalhado no
  [Estudo 18](./18-fiscal-liv-efd.md); aqui só a amarração:
  - `Documento` = `Fat_Pedido.Nr_Nota` e `Serie` = `Fat_Pedido.Serie` → **12 310** casamentos.
  - `Documento` = `Notas_Fiscais_Rec.Nr_Documento_NF` → **11 736** casamentos.
  - `COD_SIT` `1` 11 959 (regular) · `3` 135 · `6` 3 · `5` 1; `Finalidade_NF` `1` normal.
  - Naturezas top: `VENDAS` 9 709 · `(PADRAO) VENDAS` 1 711 · `REMESSA PARA DEPOSITO/ARMAZEM
    FECHADO` 399 · `REMESSA P/INDUSTR.POR CTA E ORDEM` 74 · `VENDA TRIANGULAR` 50.
- `Liv_SaiProd` (34 043) = itens fiscais por documento/produto/NatOp (`Valor_Total`, `Vr_ICMS`,
  `Cst`, `ClassFisc`, …). **Portanto**: `Fat_Itens_Pedido` é o item comercial; `Liv_SaiProd` é o
  item fiscal “oficial” para EFD/SPED.

## 8. Contas a receber (`Notas_Fiscais_*` e `Rec_*`)

- `Notas_Fiscais_Rec` (11 739) — **título** por NF (PK `Empresa+Documento+Serie`):
  `Cliente_NF`, `Emissao_NF`, `Total_Parcelas_NF`, `Vr_Total_Doc_NF`, `Codigo_Parcelamento_NF`,
  `Baixado` (`S` 11 329 / `N` 410), `Emp_Origem` (`13` 11 386 / `14` 342), `idDocumento`.
- `Notas_Fiscais_Parcelas` (29 885) — **duplicatas** (PK `Empresa+Documento+Serie+Parcela`):
  `Vencimento_Parcelas`, `Valor_Parcelas`, banco/agência/conta/operação, `Nosso_Nr_Parcelas`.
- `Notas_Fiscais_Vendedores_Parcelas` (29 886) — comissão **por parcela e vendedor**.
- `Rec_Baixas` (28 903) — **recebimentos** (PK `Empresa+Documento+Serie+Parcela+Parcial`;
  FK `(Empresa,Documento,Serie,Parcela) → Notas_Fiscais_Parcelas` e `Cod_Historico →
  Rec_Historicos`): `Data_Baixa`, `Valor_Recebido`,
  `Desconto_Concedido`, `Juros_Recebidos`, `Valor_Liquido`, `Tarifas`, `Cod_Historico`,
  `Banco/Agencia/Conta`, `IdCredito`, `DataCredito`, variação cambial.
  Período 01/08/2018 → 17/09/2026; **R$ 128,75 mi** recebidos. Histórico `88` (22 063) e `01`
  (6 314) dominam.
- `Rec_Historicos` (19) — dicionário de históricos (`Tipo_Hist_Historicos` 1..6; o tipo **6** é
  excluído da abertura em `VW_Rec_Duplicata_Aberto`).
- `Sdo_Rec_Duplicata_Aberto` — tabela de saldo anterior usada no `UNION` da view de aberto
  (**0 linhas** hoje).

### 8.1 Views de AR (o “contrato pronto”)

| View | Linhas | Conteúdo |
|------|-------:|----------|
| `VW_Rec_Duplicata_Aberto` | 1 016 | Duplicata em aberto: `Valor_Parcela − Σ Valor_Liquido`, `Dias`, `Soma_Juros`, `Soma_Desconto`, `idDocumento`, `idParcela`; `UNION` com `Sdo_Rec_Duplicata_Aberto` |
| `VW_Rec_DuplicatasEmAberto` / `Rec_EmAberto` | 1 016 | Equivalentes |
| `VW_Rec_Duplicata_Baixadas` | 28 872 | Baixas detalhadas |
| `Vw_Rec_Saldo_Qlik` | 1 016 | Saldo para Qlik |
| `Vw_Rec_Baixas_Qlik` | 28 425 | Baixas para Qlik |
| `Vw_Rec_Atrasos` | 27 719 | Atrasos/cobrança |
| `Vw_Rec_Compras` / `Vw_Rec_Inf_Comerciais` / `Vw_Rec_Cheques` | 11 741 / 1 681 / 1 681 | Inteligência de crédito |

## 9. NF-e: histórico, fila, eventos e cancelamento

- `Fat_NFe_Historico` (161 428; PK `Empresa+Pedido(char 8)+Incremento`) — **log de eventos**:
  `Chave_AcessoNFe`, `Evento`, `Mensagem`, `Observacao`, `Recibo_NFe`. `Evento` vazio 134 913 ·
  `100` 15 050 · `103` 10 032 · `135` 592 · `217` 309 · …; `Mensagem` `100` (autorização) 146 011.
- `Fat_Estagio_NFe_Auto` (12 100) — **fila de emissão automática**: `Estagio` sempre `1`,
  `Evento` `7` 8 322 / `1` 3 778, `Fila`, `Valor_Documento`, `Documento`/`Serie`.
- `Fat_NFe_Evento` (240) — dicionário de eventos (`Codigo`, `Descricao`, `Regra`, `Campo_Layout`).
- `Fat_Pedido_NFe_Eventos` (622) + `_Historico` (1 540) — eventos por nota (cancelamento, CC-e…).
- `Fat_NF_Canceladas` (152) — notas canceladas com `Justificativa_NFe`, protocolos e chave;
  por ano 2018..2026 (máx. 2025=30).
- `Fat_NFe_Contingencia` (2) / `Fat_Pedido_AutDown_NFE` (41) / `Fat_LOG_Estagio_NFe_Auto` (0) —
  contingência, download automático e log da fila de emissão.
- Outros (vazios): `Fat_NFe_Mensagens`, `Fat_NFe_Valida_XML` (24), `Fat_NFe_Eventos` (28),
  `Fat_NFSe_Historico`, `Fat_Manifesto`, `Fat_XML_DI*` (COMEX, Estudo 24).

## 10. Devolução, crédito e recibos

- `Fat_Credito_DevolucaoNF` (259) — crédito de devolução (`EmpresaDev`, `PedidoDev`, `ItemDev`,
  `Valor`, `ES`, `TipoCredito`).
- `Fat_Serie` (4) — numeração por série (`Serie` `'1  55'`, `Ult_Nota`, `Empresa`,
  `Cod_Liv_SPED_Modelo_Dcto`).
- `Fat_Recibo` (893) — recibo de comissão por vendedor/ano (`Data_Inicial/Final`, `Vr_Duplicata`,
  `Vr_Devolucao`, `Vr_Comissoes`, `Vr_Receber`).
- Devolução (vazias): `Fat_Devolucao`, `Fat_Pedidos_Dev`, `Fat_Itens_Pedido_Dev`, `Fat_Motivos_Dev`,
  `Fat_Notas_Dev` — a devolução DGB é tratada como `Ent_Sai='E'` em `Fat_Pedido` + `Fat_Credito_*`.

## 11. Views de faturamento

| View | Linhas | Conteúdo |
|------|-------:|----------|
| `Vw_Fat_Saida_Qlik` | 32 571 | **Faturamento por item** (flat): nota, item, produto, `Base_Calc<>'-'`, `Flag_Emitido='1'`, `Nr_Nota<>''`, `Data_Emissao >= 2020-01-01` e **whitelist de `NatOp`**; vendedor via `Fat_Vend_Pedido` |
| `VW_Fat_Itens_Pedido_ComQMP` | 100 495 | Item + QMP (`Peso`/`Metros`/`Qtde`) via `Liv_Diario → Produtos → Ret_Unidades` |
| `VW_FaturamentoPorProdutoEmp13` | 92 442 | Faturamento por produto (empresa 13) |
| `VW_PedFat_Prim_Aprovacao` | 114 281 | Pedido×fat × primeira aprovação |
| `VW_Pedido_Nota_Emissao_Faturamento` | 31 500 | Pedido × nota de emissão |
| `VW_Fat_Cond_Pagto` | 30 771 | Condições de pagamento aplicadas |
| `VW_Fat_Rel_Transportes` | 12 653 | Frete/transportadora, dias de entrega |
| `VW_Fat_Rel_Devolucoes` / `_PBI` | 11 | Devoluções |
| `VW_Fat_SaldosFacionista`, `VW_Fat_Devolucoes`, `vw_SIC_FAT_Transportadora` | 0 | Verticais |
| `View_VendasFat` | 1 683 | Vendas por situação/produto/mês |
| `Vw_Car_VersaoXMLPedidoFaturado` | 15 799 | Versão de XML por pedido faturado |

## 12. Procs e triggers

- **Triggers** (68 no recorte `Fat_*`/`Notas_Fiscais_*`/`Rec_*`):
  - `Fat_Pedido`: `UPT_FatPedido`, `DEL_Fat_Pedido`, `TG_UPT_Fat_Pedido_NFe`,
    `TG_Fat_SetFacionista`, `DELRomFat_Fat_Pedido`, `TG_Fat_Del_Liberar_Romaneio_Carteira`,
    `DEL_Ord_RecebPag`, `TG_DEL_Pedido_RefRetInd`, `TG_UPT_RomTransf_FatRet` e as travas
    `TG_INS/UPT/DEL_Fat_Lancamento_Fechamento_Mensal`.
  - `Fat_Itens_Pedido`: `INS_Fat_Itens_Pedido`, `UPT_Fat_Itens_Pedido`, `DEL_Fat_Itens_Pedido`,
    `Tg_CarOrc_Itens_Pedido`, `Tg_Del_Fat_Itens_Residuo_Calc` e travas de fechamento.
  - `Fat_Pedido_Dados_NFE`: `TG_UPT_Fat_Pedido_Dados_NFe`; `Fat_Estagio_NFe_Auto`:
    `TG_UPT_Fat_Estagio_NFe_Auto`; `Fat_Consiste`: `TG_INSUPT_Fat_Consiste`, `Tg_Fat_DelConsiste`.
  - **AR**: `Notas_Fiscais_Rec` (`TG_INS_Rec_Notas_Fiscais_Rec_DtLanc` + `Tg_*_Fech_*`),
    `Notas_Fiscais_Parcelas` (`TG_Rec_Id_Parcela`, `Tg_*_Log_Upt` + `Fech_*`), `Rec_Baixas`
    (`TIUD_BaixasRec`, `TG_INS_Rec_Baixas_DtLanc` + `Fech_*`), e as espelhas `*_CCD`.
- **Procs**: **244** referenciam `Fat_Pedido`, **99** `Notas_Fiscais_Rec`, **81** `Rec_Baixas`.
  Núcleo do faturamento:
  - Geração/gestão: `SP_Fat_CarPedido`, `sp_Fat_CancelaNF`, `SP_Fat_Deleta_Pedido`,
    `SP_Gera_NotaFiscal`, `SP_GeraNFE_de_NFS`, `SP_Fat_Gera_NFe_Auto_*`,
    `SP_Fat_Gera_Auxiliar`, `sp_IntegraFat`, `SP_DivideFatPedido/_Romaneio/_Orc`.
  - Comissão: `SP_Fat_PagtoComissao`, `SP_Fat_ConferePagtoComissao`, `SP_Rec_Gerar_Comissao_Vendedor`.
  - Fiscal/EFD: `SP_FAT_GERA_COD_CONCAT_EFD`, `SP_Liv_Gera_REDF`, `SP_Liv_Seleciona_REDF`,
    `SP_EFD_ListaNotasReceber`, `Gera_Liv_S`, `SP_Fat_Liv_AddItensAdicionais`.
  - Contábil/integração: `SP_Gera_Integralizacao_Contabil`, `SP_Gera_Lancamentos_Folhamatic`,
    `SP_Gera_Integra_Contab_FigCont`, `SP_HUB_EnviarInvoice`.
  - NFS/RPS: `SP_Fat_Gera_RPS`, `SP_RPS_Layout01..13`, `SP_Layout_ISS*`.
  - Relatórios: `SRPT_RELFAT*`, `SRPT_REL_NFDETAIL*`, `SRPT_RELVENDAS`, `SP_RelFaturamentoProduto`,
    `SP_COM_MAIORFATURAMENTO`, `SP_SCT_ValorFaturadoPeriodo`.
  - COMEX/importação: `SP_FAT_EDI_PACKING_LIST`, `SP_Fat_Pedido_Atualiza_Dados_DI`.

## 13. Regras e recomendações para a API/ETL

1. **Duas numerações**: `Car_Pedido.Pedido char(8)` (carteira) × `Fat_Pedido.Pedido char(6)`
   (faturamento); a ponte é `Fat_Pedido.Nosso_Pedido`. Nunca assumir igualdade de chaves.
2. **A NF “oficial” está em dois lugares**: comercial (`Fat_Pedido`/`Fat_Itens_Pedido`) e fiscal
   (`Liv_Saidas`/`Liv_SaiProd`). Para valores fiscais (EFD/SPED) usar `Liv_*`; para visão comercial
   usar `Fat_*`.
3. **Só é faturamento “de venda”** quando `Flag_Emitido='1'`, `Nr_Nota` preenchido e
   `Base_Calc<>'-'` (ver `Vw_Fat_Saida_Qlik`, que ainda aplica whitelist de `NatOp`).
4. **Título AR** = `Notas_Fiscais_Rec` (por documento/série) e **saldo** por parcela sempre
   derivado: `Valor_Parcelas − Σ Rec_Baixas.Valor_Liquido` (descontando históricos de tipo 6).
5. **Filtros de cancelamento**: cruzar `Fat_NF_Canceladas` e `Fat_Pedido_Dados_NFE.Status='X'`.
6. **Watermarks**: `Fat_Pedido.Ult_Atualizacao`/`Data_Emissao`; `Fat_Itens_Pedido.Ult_Atualizacao`;
   `Fat_NFe_Historico.Incremento`/`Data`; `Rec_Baixas.Data_Hora_Baixa`.
7. **Não usar** (vazias/verticais): `Fat_Devolucao*`, `Fat_Pneus*`, `Fat_Kanban*`, `Fat_Hub2b*`,
   `Fat_Duimp*`, `Fat_FCI*`, `Fat_Contrato*`, `Fat_Dicionario`, `Fat_Manifesto`.

## 14. Gotchas encontrados

- **Legenda de `Tipo_Pedido` muda entre módulos**: na carteira vinha de
  `Vw_Saldo_Pedido_Carteira_Qlik` (1 Vendas, 2 Pilotagem, 4 Serviço…); no **faturamento** vem de
  `Fat_Parametros` (**1 Vendas, 2 Retorno, 4 Outros**). Sempre usar a fonte do próprio módulo.
- `Fat_Itens_Pedido.Base_Calc = '-'` em **62%** das linhas (serviço/linhas sem base) — esquecer
  esse filtro **infla** o faturamento de venda.
- `Fat_Pedido.Nr_Nota` é `varchar(20)` e pode haver **mais de um `Pedido` para a mesma nota**
  (12 653 linhas × 12 272 notas distintas) — a chave da NF é `Nr_Nota+Serie`.
- A mesma `Serie` `'1  55'` aparece em `Fat_Pedido`, `Notas_Fiscais_Rec` e `Liv_Saidas`
  (série “1”, modelo “55”) — casar sempre com `Empresa`.
- `Fat_NFe_Historico.Pedido` é `char(8)` (segue o **Car_Pedido**), enquanto `Fat_Pedido.Pedido` é
  `char(6)` — não confundir os domínios ao juntar.
- `Fat_Pedido_FormaPagto` usa PK `Empresa+ID` (não o pedido) e referencia `Meio_Pagamento`/
  `Cartao_Bandeira` (Estudo 17).
- `Sdo_Rec_Duplicata_Aberto` existe (usada na view de aberto) mas está **zerada** — o saldo
  anterior já está refletido em `Notas_Fiscais_Parcelas`/`Rec_Baixas`.
- `Fat_Estagio_NFe_Auto` tem `Empresa char(2)` **e** `Id_Empresa int` (dois domínios de empresa).

## 15. Próximos passos do módulo

- **Estoque/Kardex** de saída: como `Liv_SaiProd.Qtde_Baixa` baixa `CTE_Saldos`/`Cte_Peca`
  (Estudos 09, 19) e o custo médio on-the-fly (Estudo 23).
- **Comissões**: fechar `Fat_Vend_Pedido` × `Notas_Fiscais_Vendedores_Parcelas` × `Rec_Comissoes`.
- **Devolução**: detalhar `Fat_Credito_DevolucaoNF` × `Car_Pedido` × `CTE_Baixa`.
