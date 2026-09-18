# Estudo 30 — Contas a Receber (`Rec_*`, `Notas_Fiscais_*`)

Aprofundamento do **contas a receber**: título, parcelas/duplicatas, baixas, históricos, comissão,
CNAB/cobrança, crédito e integração contábil. Levantamento por `SELECT` somente leitura (estrutura,
PK/FK, domínios, views, procs, triggers e **contagens**). Complementa o
[Estudo 05](./05-faturamento-contas-a-receber.md) (visão geral) e fecha a ponta AR do
[Estudo 29](./29-faturamento-nf.md) (faturamento/NF).

## 1. Síntese

| Papel | Objeto | Linhas | Estado |
|-------|--------|-------:|--------|
| **Título AR** (por NF) | `Notas_Fiscais_Rec` | 11 739 | **Em uso** |
| **Duplicatas** (parcelas) | `Notas_Fiscais_Parcelas` | 29 885 | **Em uso** |
| Comissão por parcela | `Notas_Fiscais_Vendedores_Parcelas` | 29 886 | **Em uso** |
| Log de alteração de parcela | `Notas_Fiscais_Parcelas_Log` | 176 | **Em uso** |
| **Baixas/recebimentos** | `Rec_Baixas` | **28 903** | **Em uso** |
| Dicionário de históricos | `Rec_Historicos` | 19 | **Em uso** |
| Remessas CNAB | `Rec_Remessa` | 25 872 | **Em uso** |
| Ocorrências de retorno CNAB | `Rec_RetornoOcorr` | 56 539 | **Em uso** |
| Dicionário de ocorrências | `Rec_Ocorrencia` | 342 | **Em uso** |
| Motivos de rejeição | `Rec_Motivo` / `REC_CNABRet_CodIrreg` | 482 / 53 | **Em uso** |
| Transações bancárias da parcela | `Rec_Transacao` | 1 019 | **Em uso** |
| Parâmetros CNAB por conta | `Rec_CNAB_BcAgCc` | 3 | **Em uso** |
| Cliente × banco | `Rec_ClienteBanco` | 1 834 | **Em uso** |
| Vendedores | `Rec_Vendedores` | 77 | **Em uso** |
| Regras de comissão | `Rec_Comissoes` | 462 | **Em uso** |
| Metas de vendedor | `Rec_MetaVendedor` | 27 | **Em uso** |
| Grupos p/ limite de crédito | `Rec_Grupos_IntCh` / `_Clientes` | 43 / 108 | **Em uso** |
| Parâmetros do módulo | `Rec_Parametros` / `Rec_ParamEmp` | 1 / 5 | **Em uso** |
| Log integração PEFIN | `Rec_Integracao_Log` / `_Dup_Log` | 4 / 4 | **Em uso** |
| Dicionários PEFIN | `Rec_NaturezaOperacaoPEFIN` / `Rec_MotivoBaixaPEFIN` | 51 / 26 | **Em uso** |
| Erros PEFIN | `Rec_ErrosPEFIN` | 192 | **Em uso** |
| Cobrança automática (dias) | `Rec_EnvCobAutomaticaDia` | 35 | **Em uso** |
| **Total** | **144 tabelas** `Rec_*`/`Notas_Fiscais_*` | | ~metade vazia (verticais/PEFIN) |

## 2. Fluxo do contas a receber

```
Fat_Pedido (NF)                                   (Estudo 29)
   │ geração do título
   ▼
Notas_Fiscais_Rec            (1 título por NF)  Emp_Origem 13 (DGB) / 14 (auxiliar)
   │ divisão em parcelas
   ▼
Notas_Fiscais_Parcelas       (duplicatas: valor, vencimento, banco, boleto)
   │                                                        └► Notas_Fiscais_Vendedores_Parcelas (comissão)
   │ CNAB / caixa / banco
   ▼
Rec_Baixas ──► Rec_Historicos (natureza da baixa)     Rec_Transacao (dados bancários)
   │                                                        (parcial: Parcial 1..n)
   ▼ saldo = Valor_Parcelas − Σ Valor_Liquido (exclui histórico tipo 6)
VW_Rec_Duplicata_Aberto / Rec_EmAberto / FN_Rec_DuplicatasEmAberto
```

Remessa/retorno bancário: `Rec_Remessa` (enviadas) `⟷ Rec_RetornoOcorr` (ocorrências de retorno)
com dicionário em `Rec_Ocorrencia`/`Rec_Motivo` e numeração em `Rec_CNAB_BcAgCc`.

## 3. Título e parcelas

### 3.1 `Notas_Fiscais_Rec` (11 739)

- **PK**: `Nr_Empresa_NF char(2)` + `Nr_Documento_NF varchar(20)` + `Serie char(5)`.
- **FKs**: `Cliente_NF → Clientes_Principal.Codigo_Cliente` (2×), `Nr_Empresa_NF → Empresas`.
- **Domínios**: `Baixado` **S = 11 329** / `N = 410`; `Emp_Origem` **13 = 11 386** / **14 = 342**.
- **Valor**: `Vr_Total_Doc_NF` somando **R$ 132,76 mi**; `Total_Parcelas_NF` **1..31** (moda 1 =
  4 954, 3 = 3 542, 4 = 968, 5 = 912…); `Emissao_NF` 2018-07 → 2026-09.
- Por ano (nº / valor): 2018 228/1,5M · 2019 735/4,6M · 2020 961/7,5M · 2021 1 390/13,2M ·
  2022 1 504/14,2M · 2023 1 765/18,9M · 2024 1 834/26,4M · 2025 1 941/27,0M · 2026 1 381/19,5M.

### 3.2 `Notas_Fiscais_Parcelas` (29 885) — duplicatas

- **PK**: `Empresa_Parcelas + Documento_Parcelas + Serie + Parcela_Parcelas`.
- **FKs**: `(Empresa,Documento,Serie) → Notas_Fiscais_Rec`; `(Banco,Agencia,DigAge,Conta,DigCon) →
  Contas_e_Agencias`; `Operacao_Parcelas → Rec_Operacoes`.
- **Campos-chave**: `Vencimento_Parcelas`, `Valor_Parcelas`, `Despesas_Parcelas`,
  `Outros_Acresc_Parcelas`, `Juros_por_Dia_Parcelas`, `Porc_Desconto`/`Vr_Desconto`/`Vencto_Desconto`,
  `Porc_Multa`/`Valor_Multa`, `Nosso_Nr_Parcelas`, `Banco/Agencia/Conta/Operacao` (boleto),
  `Tem_Baixas`, `Bloqueado`, `Inc_Parcela`, `Id_Parcela`/`idParcela`, `Cliente`, `Nota_Debito`.
- **Boletos/linha digitável**: `Bol_Fixo`, `Bol_Variavel`, `Bol_Carteira`, `Bol_Cedente`,
  `Bol_Impresso` e `LinhaDigitavel*` (8 campos), além de flags de e-mail
  (`boleto_email_enviado`, `boleto_vencido_email_enviado`, `boleto_protesto_email_enviado`).
- **Domínios**: `Tem_Baixas` **S = 28 863** / NULL = 1 001 / `''` = 21; `Valor_Parcelas` somando
  **R$ 132,76 mi**; vencimento **26/07/2018 → 14/03/2027** (48 parcelas em 2027 = cauda normal).
- Por ano de vencimento: 2018 426 · 2019 1 920 · 2020 2 204 · 2021 3 013 · 2022 3 160 · 2023 4 083 ·
  2024 4 496 · 2025 5 425 · 2026 5 110 · 2027 48.

### 3.3 `Notas_Fiscais_Vendedores_Parcelas` (29 886) e log

- **PK**: `Empresa_NF_Vendedores + Doc_NF_Vendedores + Serie + Parcela_NF_Vendedores +
  Vendedor_NF_Vendedores`; guarda `Valor_Comissao_NF_Vend(_S)`, `Porc_Comissao(_S)`,
  `Tipo_Comissao_NF_Vend`. É a **comissão por parcela** (base para pagamento de vendedor).
- **`Notas_Fiscais_Parcelas_Log`** (176): auditoria de alteração de vencimento/valor
  (`Vencto_Anterior/Atual`, `Valor_Anterior/Atual`, `Usuario`, `Sistema`) — ligada pelo parâmetro
  `Rec_Parametros.Gravar_Log_AltParcelas`.

## 4. `Rec_Baixas` — baixas (recebimentos)

- **PK**: `Empresa + Documento + Serie + Parcela + Parcial(int)`.
- **FKs**: `(Empresa,Documento,Serie,Parcela) → Notas_Fiscais_Parcelas`; `Cod_Historico →
  Rec_Historicos`. `Parcial` permite **baixas parciais** (PK composta).
- **Colunas**: `Data_Baixa`, `Data_Hora_Baixa`, `Valor_Recebido`, `Desconto_Concedido`,
  `Juros_Recebidos`, `Valor_Liquido`, `Tarifas`, `Cod_Historico`, `Complemento`, banco/agência/conta
  (`Banco`, `Agencia`, `DigAge`, `Conta`, `DigCon`, `Operacao`), `Usuario_Baixa`, `Maquina`,
  `Controle_Recebimento`, `IdCredito`/`DataCredito`, `DataLancamento`, PIS/COFINS
  (`Porc_PIS`, `Valor_PIS`, `Porc_COFINS`, `Valor_COFINS`) e variação cambial
  (`VariacaoCambialPassiva/Ativa`).
- **Valor recebido**: `Valor_Liquido` somando **R$ 128,75 mi**; período 01/08/2018 → 17/09/2026.
- Por ano (nº / líquido): 2018 478/1,1M · 2019 1 877/4,2M · 2020 2 173/7,1M · 2021 2 995/13,4M ·
  2022 3 149/11,6M · 2023 4 051/18,8M · 2024 4 482/25,7M · 2025 5 393/27,3M · 2026 4 305/19,6M.
- **Baixas parciais**: só **4** linhas com `Parcial > 1` (recebimento quase sempre em cota única).
- `Controle_Recebimento` preenchido em **11 227** linhas; `EmpPagto` e `Bloqueado` **100% NULL**
  (campos não usados nesta base).
- `Rec_ParamBCOCC_Rec` (473 646, **sem PK**) é um histórico/snapshot de parâmetros por empresa/banco/
  agência/conta — usar com cautela (pode não ser dimensional).

### 4.1 Natureza da baixa (`Rec_Historicos`, 19 registros)

| Cód | Nome | Tipo | ND | Contab | Banco | Baixas | Valor líquido |
|-----|------|:----:|:--:|:------:|:-----:|-------:|--------------:|
| 88 | Recebimento Total CNAB | 1 | N | S | S | 22 063 | 93,58M |
| 01 | Recebimento Total de Duplicata | 1 | N | S | S | 6 314 | 32,21M |
| 03 | Devolução Total de Duplicata | 3 | N | S | N | 313 | 2,09M |
| 06 | Recebimento Cartório | 1 | S | S | S | 103 | 0,19M |
| 02 | Recebimento Parcial Duplicata | 2 | N | S | S | 48 | 0,27M |
| 13 | protestada e paga | 1 | — | — | S | 47 | 0,12M |
| 89 | Recebimento Parcial CNAB | 2 | N | S | S | 6 | 0,013M |
| 04 | Devolução Parcial de Duplicata | 4 | N | S | N | 5 | 0,008M |
| 96 | ACERTO | 1 | — | — | S | 2 | 0,0007M |
| 91 | DESCONTO DUPLICATA | 4 | N | N | N | 1 | 0,0001M |
| 05 | Estorno de Lançamento | 5 | N | S | N | 1 | 0,27M |

Outros códigos cadastrados mas sem uso: `07` (Recebimento Juros), `08`/`09` (Cheque terceiro),
`15` (Baixa falta pagto), `16` (Protestada), `17` (Mercadoria roubada), `90` (Cheque),
`92` (Baixa por falta de pagamento).

**Regra central do saldo**: em abertura/atraso **excluir `Tipo_Hist_Historicos = '6'`** (e, em
`Vw_Rec_Atrasos`, também `3,4,5`). O `Tipo` classifica: **1** total, **2** parcial, **3** devolução
total, **4** devolução parcial/desconto, **5** estorno, **6** juros.

## 5. Comissão e vendedores

- `Rec_Vendedores` (77) — PK `Codigo_Vendedores char(3)`; dados comerciais + fiscais do vendedor.
  **Ativo** S = 28 / N = 49; todos `Comissionado = 'C'`. Tem `idParticipante → Fnn_Participante`
  (entidade unificada, Estudo 27), `Grupo_Venda → Rec_Grupos_Vendedores`, cidade/UF.
- `Rec_Comissoes` (462) — PK `Vendedor_Comissoes + Tipo_Comissoes`; `E_ou_S_Comissoes`
  (**A** = ambos 460, **E** entrada 1, **S** saída 1), `Porcentagem_Comissoes(_S)`, `Dias_Atraso`,
  `Inativo`; `idParticipanteComissao → fnn_ParticipanteComissao`.
- `Rec_Vendedores_Pagto` (1) — comissão específica por condição de pagamento.
- `Rec_MetaVendedor` (27) — metas `Valor/Metros/Peso` por empresa/vendedor/data.
- `Rec_AtrasoComissao` (3) — faixas de atraso × percentual de comissão.
- A comissão efetiva é o cruzamento `Fat_Vend_Pedido` (Estudo 29) ×
  `Notas_Fiscais_Vendedores_Parcelas` × `Rec_Comissoes`, gerado por
  `SP_Rec_Gerar_Comissao_Vendedor`/`SP_Fat_PagtoComissao`.

## 6. CNAB, bancos e cobrança

- `Rec_CNAB_BcAgCc` (3) — conta bancária do cedente e `UltimaRemessa`.
- `Rec_Transacao` (1 019) — dados bancários da parcela: PK
  `Empresa+Documento+Serie+Parcela+Transacao`; `Operacao` (01 = 617, `''` = 360, `BL` = 30, 02 = 12),
  `Nosso_Nro`, endereço de cobrança (`Bol_*`), `Despesas_Parcelas`; período 10/08/2018 → 17/09/2026.
- `Rec_Remessa` (25 872) — PK `Empresa+Documento+Serie+Parcela+Data`; `Vr_Parcela`, `Vr_Gerado`
  (**R$ 108,99 mi**), `Nome_Arquivo` (**1 222 arquivos**), `Seq_Remessa`; por ano 2018 426 · 2019
  1 704 · 2020 1 660 · 2021 2 536 · 2022 2 903 · 2023 3 683 · 2024 4 112 · 2025 5 188 · 2026 3 660.
- `Rec_RetornoOcorr` (56 539) — retorno do banco: `Ocorrencia`, `Data`, `Codigo_Motivo`,
  `Vr_Despesa`, banco/agência/conta/`Nosso_Nro`. Top ocorrências: **02** (entrada confirmada)
  23 972 · **06** (liquidação) 21 963 · **05** 5 049 · **72** 1 615 · 10 679 · 19 652 · 23 606.
  Por ano (crescente): 2019 2 218 → 2025 12 077 → 2026 11 080.
- `Rec_Ocorrencia` (342) — dicionário por banco (341 81, 756 55, 237 40, 033 39, 422 33…),
  `Situacao = 'N'` em todas.
- `Rec_Motivo` (482) — motivo por banco+ocorrência; `REC_CNABRet_CodIrreg` (53) — códigos de
  irregularidade; `REC_CNABRet_CodIrreg`.
- `Rec_ParamEmp` (5) — 1 por empresa (01, 02, 13, 14): contas de integração de dinheiro/depósito,
  históricos padrão, `CNABRet_Parc`, `CalcularJurosJungidos`, `CompensarBaixa_BCO`, `Ult_Recibo`.

## 7. Crédito, grupos e cadastros

- `Rec_Grupos_IntCh` (43) / `Rec_Grupos_IntCh_Clientes` (108) — grupos de clientes para
  **limite de crédito** (controla limite do grupo, `isControlarGrupo`).
- `Rec_ClienteBanco` (1 834) — PK `Codigo_Cliente + Banco` (bancos do cliente).
- `Rec_ErrosPEFIN` (192) + `Rec_NaturezaOperacaoPEFIN` (51) + `Rec_MotivoBaixaPEFIN` (26) —
  dicionários de integração **PEFIN** (ERP externo).
- `Rec_Integracao_Log` (4) / `Rec_Integracao_Dup_Log` (4) — auditoria da integração (cliente,
  encargos, valores, CNPJ, Status).
- `Rec_EnvCobAutomaticaDia` (35) — regras de **cobrança automática** por dia da semana
  (`ID`/`ID_Empresa`, `Dia_Semana`, `Enviar_Email`).
- `Rec_ClienteVendedorLog` (106) — auditoria de troca de vendedor/tipo de comissão do cliente.
- `Rec_Fechamento_Campos_Alterados` (67) — campos auditados no fechamento mensal do AR.

## 8. Parâmetros e configuração

- `Rec_Parametros` (1) — **parâmetros globais do AR**, extensíssimo: históricos padrão de baixa
  (`Hist_BaixaTotal/Parcial*` por forma: dinheiro/cheque/depósito/cartão/recibo), juros/multas,
  comissão (`Calc_Comissao_Recebido`, `ReCalc_Comissao`), CNAB (`CNABUltimaRemessa`, `NaoReenviarCNAB`,
  `ConsiderarValorTotal_CNAB`), controle (`Gravar_Log_AltParcelas`, `Fechamento_por_Dia`,
  `Bloq_Dig_JurosBaixa`), e-mails (`Email_Contas_a_Receber`), PIS/COFINS na baixa
  (`PisCofins_Nabaixa`), etc.
- `Rec_Diario` (1 por empresa) — numeração sequencial de livro/razão/página.
- `Rec_Conceitos` (5) — conceitos de atraso (faixas inicial/final).
- `Rec_Operacoes` (3) — operações de cobrança; `Rec_TipoMovimento`/`Rec_TipoPagamento`/
  `Rec_TipoCredito` — dicionários pequenos.

## 9. Views e função (o “contrato pronto”)

| Objeto | Linhas | Conteúdo |
|--------|-------:|----------|
| `VW_Rec_Duplicata_Aberto` | 1 016 | Duplicata em aberto: `Valor_Parcela − Σ Valor_Liquido`, `Dias`, juros/desconto, banco/operação, `idDocumento`/`idParcela`; `UNION` com `Sdo_Rec_Duplicata_Aberto` (0) |
| `VW_Rec_DuplicatasEmAberto` / `Rec_EmAberto` / `Rec_EmAberto_Geral` / `Vw_Rec_Saldo_Qlik` | 1 016 | Equivalentes (mesma regra) |
| `VW_Rec_Duplicata_Baixadas` | 28 872 | Baixadas: valor, Σ recebido, Σ juros, Σ desconto, maior data (por título/parcela) |
| `FN_Rec_DuplicatasEmAberto(@Data_Retroativa)` | TVF | Duplicatas abertas **até uma data** (posição histórica); mesma regra da view |
| `Vw_Rec_Baixas_Qlik` / `vwPnRecBaixas` | 28 425 / 28 903 | Baixas (Qlik / por data) |
| `Rec_Saldos` | 18 919 | **Razão** débito (`Notas_Fiscais_Rec`) × crédito (`Rec_Baixas`, exclui tipo 6) por cliente/período |
| `Vw_Rec_Atrasos` | 27 719 | Atraso por baixa (dias); exclui históricos 3/4/5/6, empresas auxiliares e operações em `Com_Ope_NSelDupl` (vazio) |
| `Vw_Rec_Prazo` | 2 755 | Maior prazo concedido por cliente (`Clientes_Informacoes`, `Rec_Movtos_DF`, NF, CCD) |
| `Vw_Rec_Compras` | 11 741 | Histórico de compras por cliente |
| `Vw_Rec_Inf_Comerciais` | 1 681 | Resumo comercial do cliente (1ª/última/maior compra) |
| `Vw_Rec_Cheques` | 1 681 | Cheques em aberto via `Ch_Cheques` (**tabela vazia** → view só com zeros) |
| `VW_MDireta_Rec` | 29 852 | Recebimentos “modo direto” |
| `Fn` | | `FN_REC_SaldoDuplicataRepagamento` (saldo p/ repagamento) |

## 10. Procs e triggers

- **Procs que referenciam**: `Rec_Baixas` **81**, `Notas_Fiscais_Parcelas` **119**,
  `Notas_Fiscais_Vendedores_Parcelas` **34**, `Rec_Comissoes` **37**, `Rec_Transacao` **9**,
  `Rec_Remessa` **2**. Núcleo do AR:
  - Baixa/estorno: `SP_Rec_BaixasOperacoes`, `SP_Rec_Estorno_Baixa`, `TIUD_BaixasRec` (trigger),
    `SP_Rec_FechamentoDia`, `sp_FechGeral`, `SP_Exclui_MovtosCR`.
  - Documentos: `SP_Rec_GeraDoc(_porCliente)`, `SP_Rec_GeraNota`, `SP_Rec_AlteraDuplicata`,
    `SP_Rec_ExcluiDoc`, `SP_Gera_NotaDebito`.
  - Comissão: `SP_Rec_Gerar_Comissao_Vendedor`, `SP_Rec_RelComissaoEntrada`,
    `SP_REC_RELCOMISSAOVENDOP`, `SP_Rec_FretesEmpresa`, `SP_Rel_PPR_Comissao`.
  - Cobrança/CNAB: `SP_Rec_RelRemessa`, `SP_Rec_ConsGer_Dup_EmAberto(_GC)`,
    `SP_Rec_RelTransacoesBaixas`, `SP_Orc_PalmCobranca`.
  - Relatórios/gestão: `SP_REC_RelValoresEmAberto(Analitico)`, `SP_Rec_RelDupAberto_NL`,
    `SP_Rec_RelListagemBaixas`, `SP_Rec_RelEntradas`, `SP_Rec_Acumulo`,
    `SP_Rec_ConsGer_Pagtos_Atrasados_Duplicatas`.
  - Fluxo/contábil: `sp_fluxo_ContasAReceber(_ContaBancaria)`, `SP_Fluxo_GerarFluxoPorEmpresa`,
    `SP_Liv_Gera_Contimatic_Finan`, `SP_Liv_Gera_Finan_Folhamatic`, `SP_Gera_Integralizacao_Contabil`.
  - Bloqueio de crédito: `SP_Bloqueio`, `SP_BLOQUEIO_GERAL`, `SP_Bloqueio_GrupoCliente`,
    `SP_BLOQUEIO_INTERNET`, `SP_BLOQUEIO_LOJ`.
- **Triggers** em tabelas `Rec_*`: `Rec_Baixas` (`TIUD_BaixasRec`, `TG_INS_Rec_Baixas_DtLanc`,
  `Tg_Rec_Baixas_Fech_Ins/Upd/Del`), `Rec_Transacao` (`Tg_Rec_Transacao_Fech_Ins/Del/Upd`),
  `Rec_EnvCobAutomaticaDia` (`..._Integridade`), `Rec_Integracao`
  (`TG_INS_Rec_Integracao_DtLanc`). Sobre `Notas_Fiscais_*`: ver Estudo 29.

## 11. Regras e recomendações para a API/ETL

1. **Saldo por parcela** = `Valor_Parcelas − Σ Rec_Baixas.Valor_Liquido`, considerando **apenas
   baixas não-estorno** (excluir `Rec_Historicos.Tipo_Hist_Historicos = '6'`; em atraso excluir
   também 3,4,5). É a regra de `VW_Rec_Duplicata_Aberto`/`FN_Rec_DuplicatasEmAberto`/`Rec_Saldos`.
2. **Posição histórica**: usar `FN_Rec_DuplicatasEmAberto(@Data)` para “como estava em tal data”
   (filtra `Emissao_NF <= @Data` e `Data_Baixa <= @Data`).
3. **Empresa auxiliar**: excluir `Fat_ParamEmp.Empresa_Auxiliar` nos relatórios de prazo/atraso
   (13 → auxiliar **14**; 01 → 02). `Notas_Fiscais_Rec.Emp_Origem` distingue 13 (DGB) de 14.
4. **Baixa parcial** existe (`Parcial`), mas raríssima (4 casos) — não assumir 1:1 parcela↔baixa.
5. **CNAB**: `Rec_Remessa` = enviadas, `Rec_RetornoOcorr` = retornos; casar por
   `Documento+Serie+Parcela+Banco`, enriquecer com `Rec_Ocorrencia`/`Rec_Motivo`.
6. **Comissão**: título → parcela (`Notas_Fiscais_Vendedores_Parcelas`) → regra (`Rec_Comissoes`);
   parâmetros de recálculo em `Rec_Parametros`.
7. **Watermarks**: `Rec_Baixas.Data_Hora_Baixa`/`DataLancamento`;
   `Notas_Fiscais_Rec`/`_Parcelas` não têm carimbo de alteração confiável → usar
   `Notas_Fiscais_Parcelas_Log` e `Rec_Fechamento_Campos_Alterados` para CDC.
8. **Não usar** (vazias): `Rec_Cheques*`, `Rec_Integracao*` (exceto Log), `Rec_Recibo_Pagto*`,
   `Rec_Sensus*`, `Rec_CargaRetorno*`, `Rec_Grupos_Cidades/Ramos/Regioes`, `Rec_Movtos_DF` (crediário),
   `Rec_PagtoComissoes`, `Rec_HistoricoComissao`.

## 12. Gotchas encontrados

- `Rec_Baixas` **não tem** coluna de "empresa pagadora" útil (`EmpPagto` 100% NULL) nem `Bloqueado`
  usado; a empresa vem de `Documento`/`Serie`.
- `Valor_Liquido` **não** é o valor do título: a identidade exata (verificada no agregado) é
  **`Valor_Liquido = Valor_Recebido − Juros_Recebidos + Desconto_Concedido − Tarifas`**. Ou seja,
  `Valor_Recebido` é o caixa cobrado (inclui juros pagos pelo cliente) e `Valor_Liquido` é o que
  **abate o título**. Para caixa use `Valor_Recebido`; para quitar a parcela use `Valor_Liquido`.
- `Rec_Historicos.Tipo_Hist_Historicos = '6'` (juros) **não** abate o título — se somado, o saldo
  fica errado; foi exatamente o bug citado no cabeçalho de `FN_Rec_DuplicatasEmAberto`
  (“Estava duplicando registros”).
- `Rec_ParamBCOCC_Rec` (473 646) é **a maior tabela do AR e não tem PK** — provável tabela de
  trabalho/histórico, não dimensional.
- `Vw_Rec_Cheques` retorna 1 linha por cliente **sempre zerada** porque `Ch_Cheques` está vazia
  (módulo de cheques não usado).
- `Rec_RetornoOcorr` tem **quase 2×** o volume de `Rec_Remessa` (56 539 × 25 872): um retorno
  pode gerar várias ocorrências.
- Várias colunas de dinheiro são `decimal(16,4)`; a soma aberta pela API deve arredondar só no fim.
- `Rec_Vendedores` inclui vendedores **inativos** (49 de 77) — filtrar `Ativo` nos relatórios ativos.

## 13. Próximos passos

- **Fluxo de caixa / contábil**: aprofundar `Fluxo_Caixa` + `SP_Fluxo_GerarFluxoPorEmpresa` e a
  integração contábil (Estudo 23).
- **Compras/CP (`Pag_*`)**: a outra ponta do financeiro.
- **Financeiro bancário**: `Bco_*`/`Ch_*`/CNAB de pagamento (integração com o AR aqui mapeada).
