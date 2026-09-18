# Estudo 33 — Financeiro Bancário (`Bco_*`, `Contas_e_Agencias`, CNAB, `CH_*`)

Aprofundamento do **financeiro bancário**: livro de lançamentos de banco (extrato/tesouraria),
cadastro de contas e agências, parâmetros/sequências, layouts e retorno **CNAB** e o módulo de
**cheques** (`CH_*`). Levantamento por `SELECT` somente leitura. Consolida a fonte de saldo/movimento
usada pelo [Estudo 32](./32-fluxo-de-caixa.md) (fluxo de caixa) e a ponta bancária dos
[Estudos 30](./30-contas-a-receber-rec.md)/[31](./31-contas-a-pagar-pag.md) (AR/CP).

## 1. Síntese

| Papel | Objeto | Linhas | Estado |
|-------|--------|-------:|--------|
| **Livro de banco** (extrato/tesouraria) | `Bco_Lancamentos` | **10 864** | **Em uso** |
| Observações do lançamento | `Bco_Lanc_Obs` | 4 720 | **Em uso** |
| Dicionário de históricos | `Bco_Historicos` | 37 | **Em uso** |
| **Cadastro de contas/agências** | `Contas_e_Agencias` | 9 | **Em uso** (7 ativas) |
| Banco (master) | `Bancos` | 14 | **Em uso** (referência) |
| Sequências de lançamento | `BCO_IDLancamentos` | 15 | **Em uso** |
| Parâmetros / numeração | `Bco_Parametros` / `Bco_Diario` | 1 / 1 | **Em uso** |
| Layout CNAB 400 | `CNAB_Mescla` | 933 | **Em uso** (13 bancos) |
| Layout CNAB 240 | `CNAB_Mescla_240` | 472 | **Em uso** (001/033) |
| Mapeamento de retorno | `CNAB_Retorno` / `_240` | 62 / 18 | **Em uso** |
| Config CNAB por conta | `CNAB_Banco` | 15 | **Em uso** |
| Log de crítica de retorno | `CNAB_RETORNO_LOG` | 68 | **Em uso** |
| Cheques — cadastros | `CH_Bancos`/`CH_Agencias`/`CH_Motivos`/… | 9/11/12/… | Cadastro |
| **Cheques — movimento** | `CH_Cheques` / `CH_Cheques_Movtos` | **0** | **Inativo** |
| Conciliação bancária OFX | `BCO_ConciliacaoBancaria*` | 0 | **Vazia** |
| Transferências / CCusto de banco | `Bco_Lancamentos_Transf` / `Bco_Lan_CCustos_*` | 0 | **Vazias** |

> O **coração** é `Bco_Lancamentos` (+ `Bco_Lanc_Obs`); tudo o mais é cadastro, layout CNAB ou
> infraestrutura. O módulo de **cheques é inativo** (`CH_Cheques`/`CH_Cheques_Movtos` vazios),
> embora os cadastros existam.

## 2. Fluxo

```
Contas_e_Agencias (conta bancária)           Bancos (código/nome)
        │                                            │
        ▼                                            ▼
Bco_Lancamentos  ◄── Bco_Historicos (E entrada / S saída)   [[extrato/tesouraria]]
        │
        ├─ Bco_Lanc_Obs (observações; id_Parcela → título)
        ├─ BCO_IDLancamentos (última chave por conta)
        └─ Vw_Bco_SaldosBancos (saldo assinado por conta/dia)
                 │
                 ▼
        sp_fluxo_ContasBancarias / SP_SaldosExtratos / SRPT_BAN_SALDO   (Estudo 32)
                 │
                 ▼
        CNAB_Banco + CNAB_Mescla(_240) + CNAB_Retorno(_240) + CNAB_RETORNO_LOG
        (remessa/retorno de cobrança — layouts por banco)
```

## 3. `Bco_Lancamentos` (10 864) — livro de banco

- **PK** (7 colunas): `Cod_Empresas char(2)` + `Nr_Bco_Bancos char(3)` + `Nr_Age_Contas char(4)` +
  `Dig_Age_Contas char(1)` + `Nr_Conta_Contas char(10)` + `Dig_Conta_Contas char(1)` +
  `Incremento int`.
- **FKs**: conta → `Contas_e_Agencias`; `Cod_Empresas → Empresas.Codigo_Empresas`;
  `Cod_Historico → Bco_Historicos`.
- **Colunas**: `Data`, `Cod_Historico char(3)`, `Texto_1..4 char(40)`, `Valor decimal(16,4)`,
  `Nr_Cheque`, `Compensado`/`Data_Compensacao`, `Cod_Contabil`, `CCusto char(3)`, `Bloqueado`,
  `Cheques_Dep`, usuário (`Usuario`, `DataHoraGravacao`), integração (`Integracao`,
  `IntegracaoSIMPag`, `idDocumento`, `IDBaixa`), `CodIdentDeposito`, `Chave_Cheques_Movtos`,
  `idBCOConcBancaria`, `DataLancamento`.
- **Volume/valor**: Σ `Valor` = **R$ 235.805.520,83**; período **11/06/2018 → 31/12/2026**.
- **Empresas**: 13 = 9 992 (R$ 234,2M) · 14 = 871 (R$ 1,57M) · 01 = 1.
- **Históricos usados** (só 2 de 37 códigos):
  - `999` **Tipo E (entrada)** — 8 505 lançamentos / R$ 125,17M;
  - `000` **Tipo S (saída)** — 2 359 / R$ 110,63M.
- **Contas em uso**: **7** (de 9 cadastradas).
- `Compensado`: **S = 56 / N = 10 808** → a **conciliação bancária praticamente não é usada**.
- **`Bco_Lanc_Obs`** (4 720; PK `Cod_Empresas + Id_Bco_Lanc_Obs`): `Obs varchar(50)` e
  `id_Parcela int` (liga o lançamento à parcela/título).

## 4. Cadastro de contas — `Contas_e_Agencias` (9)

- **PK**: `Nr_Bco_Contas + Nr_Age_Contas + Dig_Age_Contas + Nr_Conta_Contas + Dig_Conta_Contas`.
- **FKs**: banco → `Bancos.Nr_Bco_Bancos`; cidade/UF → `Cidades`/`Estados`.
- **Colunas**: endereço, `Conta_Contabil`/`Empresa_Contabil`/`idContaContabil`,
  `Empresa`/`Empresa_R`/`EmpresaTitular`, `Inativo`, `TipoConta char(2)`, `Valor_Limite`,
  `Porc_Cobertura`, `Obs`, integração SISPAG (`SisPag_Hist_*`), `ContaDescontada`,
  `ObservacaoEmissaoCheque`, `IdAgencia`/`IdConta`, `idContaContabilTransDep`.
- **Boleto/PIX (API)**: `ParametrizacaoBoletoAPI`, `ClienteID`/`ClienteSecret`/`KeyUser`/`Scope`,
  `HomologacaoProducao`, `UsaCertificado`, `ArquivoCRT`/`ArquivoKEY`/`ArquivoPFX`, `ChavePIX`.
  ⚠️ **Campos sensíveis** (credenciais/certificado/PIX) — **nunca** copiar para o repo/Neon; tratar
  como segredo (ou omitir no `raw`).
- Contas cadastradas: `000/0000/0000000000` (placeholder, 3 empresas), `001/6624/0000030758`,
  `002`, `033/0090/0013014445`, `237/0215/0000576972`, `237/2188/0000026972`, `BLU`.
- `Bancos` (14) é o **master de bancos**; `CH_Bancos` (9) é a lista **própria** do módulo de cheques.

## 5. Parâmetros, sequências e observações

- `Bco_Parametros` (1) — `Integra_Contabilidade/Bancos`, `TipoConta`, `Foco_Data`,
  `ValidaDataLanc_Bco`/`QtdeDiasValidaDataLanc_Bco`, `IDBcoLactosTransf`, `idCod_Contabil`.
- `Bco_Diario` (1; PK `Codigo_Empresa`) — numeração de diário/razão/saldos.
- `BCO_IDLancamentos` (15) — **sequência/última chave** por conta
  (`Empresa, Banco, Agencia, Conta, IDBcoLancamento, IDBcoLancamentoObs`).
- `Bco_Lancamentos_Aux` (1; **sem PK**) — espelho com `Replicado`, `Excluido`, `Tipo`,
  `idBCOConciliacao` (staging de replicação/conciliação).
- `Bco_Exc`, `Bco_TipoConta`, `Bco_Fechamento_Mensal`, `Bco_Lan_CCustos_*` — **vazias**.

## 6. CNAB (remessa/retorno) — o contrato de arquivo

- **`CNAB_Mescla`** (933; PK `Banco, Layout, Bloco, Pos_Inicial`) — layout **CNAB 400 genérico**:
  mapeia `Pos_Inicial/Pos_Final`, `Const_Var`, `Valor`, `Tabela`, `Campo`, `Tipo`, `Tamanho`,
  `Decimal`, `Mascara`. 13 bancos (151, 237, 001, 215, 275, 347, 399, 341, 033, 291, 641…).
- **`CNAB_Mescla_240`** (472; PK + `Ordem/Tipo_Reg/Segmento/Especie`) — layout **CNAB 240**
  (bancos **001** e **033**).
- **`CNAB_Retorno`** (62) / **`CNAB_Retorno_240`** (18) — mapeamento do **retorno**: para cada
  campo, os textos que representam `Aceito`, `Rejeitado`, `Entrada_Confirmada`, `Aceito_Cartorio`,
  `Abatimento_Concedido`, `Vencimento_Alterado`.
- **`CNAB_Banco`** (15; PK `Empresa, Banco, Layout, Usar_240`) — configuração por conta/banco:
  diretórios de remessa/retorno, `Cedente`, `Codigo_Carteira`/`Cod_Cart_Banco`, `Protesto`,
  `Banco_Emite`/`Cod_Banco_Emite`, `Ultima_Remessa`/`Ultimo_LayOut`/`Ultimo_LayoutR`,
  `Voltar_Carteira`, `Grava_Juros`/`Perc_Juros`, `TAC`/`TaxaEfetiva`, `Tipos_Movtos`,
  `Historico_Total/Parcial`, `Baixa_por_NossoNum`, `Filtra_Nosso_Nr`, `Chave`.
- **`CNAB_RETORNO_LOG`** (68; PK `Id_Empresa, Id`) — log de processamento do retorno
  (`Arquivo`, `Critica`, `Orientacao`, `Usuario`, `Data_Hora`).
- As tabelas equivalentes de **remessa de AR/CP** (`Rec_Remessa`, `Pag_CNAB_*`) estão nos
  Estudos 30/31; aqui ficam os **layouts** e a **config bancária**.

## 7. Módulo de cheques (`CH_*`) — inativo

- **`CH_Cheques` (0)** e `CH_Cheques_Movtos`/`CH_Cheques_Parcelas`/`CH_Conta_Lancamentos` — **vazias**
  → o módulo de cheques **não está em uso** nesta base (coerente com `Ch_Cheques` vazia no Estudo 30
  e `Ch_Cheques` citada mas sem dados no AR).
- **Cadastros presentes**: `CH_Bancos` (9: BB, Santander, Caixa, Bradesco, Itaú, Safra, Daycoval,
  Citi, Sicredi), `CH_Agencias` (11), `CH_Motivos` (12 — motivos de devolução de cheque, ex.:
  sem fundos 1ª/2ª, conta encerrada, sustado por roubo), `CH_Parametros` (1),
  `CH_Conta_Parametros` (2 — `Ult_Cheque`/`Ult_Cheque_Movto`, senhas), `Ch_Layout_Cheques` (43 —
  layout de importação de cheques do banco **237**, layout 2, 3 blocos), `CH_Comprador` (1).
- **Triggers** existem (`Tg_CH_Cheques_Fech_*`, `Tg_CH_Cheques_Movtos_Fech_*`,
  `Tg_CH_Conta_Lancamentos_Fech_*`) mesmo sem dados.

## 8. Views e procs

| Objeto | Linhas | Conteúdo |
|--------|-------:|----------|
| `Vw_Bco_SaldosBancos` | 4 390 | **Saldo assinado** por conta/dia: `Σ(CASE H.Tipo WHEN 'E' THEN Valor ELSE −Valor END)` agrupado por conta+`Data`; também expõe `EmpBcoAgCC` (chave concatenada) |
| `VW_CHQ_EstadoChequeIntegracao` / `VW_CHQ_EstadoTipoChequeIntegracao` | 0 | Cheques × integração (vazias) |
| `Vw_Rec_Cheques` | 1 681 | AR por cheque (só zeros — Estudo 30) |

- **Procs que referenciam** `Bco_Lancamentos` **16** — principais: `Sp_Banco_Rel_Lancamentos`,
  `SP_SaldosExtratos`, `sp_fluxo_ContasBancarias(_ContaBancaria)`,
  `SP_Fl_Fech_Fin_Reg_Cx_SIMBanH_D/_M` / `_SIMBanBAC_D/_M`, `SP_Fl_Rel_FluxoporTipoConta`,
  `SP_Fl_RelContrato`, `SRPT_BAN_SALDO`, `SRPT_FLUXO_FUTURO`, `SRPT_PAGAR_RECEBER`,
  `sp_PagRel_CCusto_Niveis`, `SP_Cont_Importa_CCusto_Lancto`.
- **Procs que referenciam** `Contas_e_Agencias` **15** — inclui os importadores contábeis
  (`SP_Liv_Gera_Contimatic_Finan`, `SP_Liv_Gera_Finan_Folhamatic`, `SP_Liv_LactosFinan_SEMCON`,
  `SP_Liv_Prosoft_*`), `SP_Rec_RelRemessa`, `SP_FAT_CartaFaturamento`, `SP_FOL_RelDecFGTS`.
- **Triggers** em `Bco_Lancamentos`: `TG_INS_Bco_Lancamentos_DtLanc` e os de fechamento
  (`TG_INS/UPT/DEL_Bco_Lancamento_Fechamento_Mensal`).

## 9. Regras e recomendações para a API/ETL

1. **Saldo bancário** = `Vw_Bco_SaldosBancos` (sinal por `Bco_Historicos.Tipo`: **E = +, S = −**).
   É a base de `sp_fluxo_ContasBancarias`/`SP_SaldosExtratos` (Estudo 32).
2. **Chave da conta** (5 colunas) é usada em todo o resto: materializar `dim_conta_bancaria` no Neon
   com a chave composta concatenada (`EmpBcoAgCC`).
3. **Históricos**: `Bco_Historicos` (37), com `Tipo E/S`, `Gerar_Contabilidade`, `CContabil`,
   `Transferencia`, `ObrigaCC`, `Deposito`/`DepositoIdentificado`, `LancamentoIdentificado`.
4. **Vínculo com títulos**: via `Bco_Lanc_Obs.id_Parcela` e `Bco_Lancamentos.IDBaixa`/`idDocumento`
   — **não** há FK direta para parcela de AR/CP; a amarração é por esses campos.
5. **Compensação**: `Compensado` quase sempre `N` (56 de 10 864) → **não usar como filtro de
   conciliação**; a conciliação real (OFX) está vazia.
6. **CNAB**: layouts em `CNAB_Mescla`/`_240` (posicional) + textos de retorno em
   `CNAB_Retorno`/`_240` + config/diretórios em `CNAB_Banco`. Portar como tabelas de
   configuração (`etl`/`marts`), não como dados transacionais.
7. **Segurança**: `Contas_e_Agencias` guarda `ClienteSecret`, `KeyUser`, `Scope`, `ArquivoKEY`,
   `ArquivoPFX`, `ChavePIX` — **não replicar** para o Neon nem versionar (segredos/certificados).
8. **Cheques**: tratar o módulo como **inativo**; só os cadastros (`CH_Bancos`/`CH_Agencias`/
   `CH_Motivos`) têm conteúdo. O financeiro de cheque real está em `Pag_ChequesEmi_Duplicata`
   (Estudo 31).
9. **Watermarks**: `Bco_Lancamentos.DataHoraGravacao`/`DataLancamento`/`Data`; sem coluna de
   alteração confiável, usar os triggers de fechamento/CDC.

## 10. Gotchas encontrados

- **PK de 7 colunas** em `Bco_Lancamentos` (empresa+banco+agência+conta+incremento) — o
  `Incremento` é **sequência por conta**, não global; usar `BCO_IDLancamentos` para o último valor.
- `Bco_Lancamentos_Transf`, `Bco_Lan_CCustos_*` e toda a conciliação
  (`BCO_ConciliacaoBancaria*`) estão **vazias** — transferências/CCusto/OFX não usados.
- Só **2 históricos** (`000` saída, `999` entrada) concentram todo o movimento; os 37 cadastros
  existem para expansão.
- `Compensado='S'` em apenas **56** linhas → conciliação bancária **não operacional**.
- O valor de `Vw_Bco_SaldosBancos` é **assinado** por `Tipo` (`E`/`S`); não confundir com o `Valor`
  bruto de `Bco_Lancamentos`.
- `Bancos` (master, 14) ≠ `CH_Bancos` (módulo de cheques, 9) ≠ `CH_Agencias` (11) — **três
  listas de banco** distintas (a de `Contas_e_Agencias` referencia `Bancos`).
- Conta placeholder `000/0000/0000000000` existe para 3 empresas (sem agência/conta real) — filtrar
  `Nr_Bco_Contas <> '000'` em relatórios bancários.
- `Contas_e_Agencias` contém **campos de segredo** (PIX/certificado/API) — risco de vazamento se
  copiar a tabela inteira para o `raw`.
- Várias `varchar(-1)` (`max`) em `Contas_e_Agencias` (certificado/key) — cuidado no volume do ETL.

## 11. Próximos passos

- **Conciliação AR/CP × banco**: cruzar `Bco_Lancamentos` (`idDocumento`/`IDBaixa`/`id_Parcela`)
  com `Rec_Baixas`/`Pag_Baixas` (Estudos 30/31).
- **Estoque** (`Est_*`) ou **Fiscal/SPED** (Estudo 12) como próximo módulo de domínio.
- **Mart financeiro no Neon**: `mart_fluxo_caixa` (Estudo 32) usando `mart_saldo_bancario` desta
  ponta como saldo inicial.
