# Estudo 31 — Contas a Pagar (`Pag_*`, `NF_Entradas`, `NFE_*`)

Aprofundamento do **contas a pagar**: entrada de NF de fornecedor, parcelas, baixas, históricos,
cheques emitidos, rateio de despesa/centro de custo, impostos, crédito de fornecedor e CNAB de
pagamento. Levantamento por `SELECT` somente leitura (estrutura, PK/FK, domínios, views, procs,
triggers e **contagens**). Complementa o [Estudo 06](./06-contas-a-pagar.md) (visão geral) e é a
ponta oposta do [Estudo 30](./30-contas-a-receber-rec.md) (AR).

## 1. Síntese

| Papel | Objeto | Linhas | Estado |
|-------|--------|-------:|--------|
| **Título a pagar** (NF entrada) | `NF_Entradas` | **8 631** | **Em uso** |
| **Parcelas / duplicatas** | `NFE_Parcelas` | **8 736** | **Em uso** |
| **Baixas / pagamentos** | `Pag_Baixas` | **8 603** | **Em uso** |
| Dicionário de históricos | `Pag_Historicos` | 8 | **Em uso** |
| Cheques emitidos × duplicata | `Pag_ChequesEmi_Duplicata` | 8 237 | **Em uso** |
| Rateio por despesa/receita | `NFE_CCustos_DespesasReceitas` | 8 591 | **Em uso** |
| Rateio por centro de custo | `NFE_CCustos_departamento` | 8 576 | **Em uso** |
| Log de alteração de parcela | `NFE_Parcelas_Log` | 3 991 | **Em uso** |
| Integração de pagamento | `Pag_Integracao` / `_Doc` | 403 / 411 | **Em uso** |
| Crédito de fornecedor | `Pag_CreditoFornecedor` | 2 | Esporádico |
| Ocorrências CNAB | `Pag_Ocorrencia` / `_Motivo` | 5 / 371 | **Em uso** |
| Layout CNAB 240 | `Pag_CNAB_Mescla_240` | 99 | **Em uso** (341) |
| Plano de despesas/receitas | `Pag_DespesasReceitas` | 91 | **Em uso** |
| Centros de custo | `Pag_CCusto_Departamento` | 21 | **Em uso** |
| Mapa despesa×CCusto padrão | `Pag_DespesasReceitas_CCustoDpto` | 28 | **Em uso** |
| Impostos retidos | `Pag_Impostos` (+ rateio) | 2 (+2) | **Em uso** |
| Tipos de fornecedor | `Pag_Tipos_Fornecedores` | 11 | Dicionário |
| Parâmetros do módulo | `Pag_Parametros` / `Pag_Diario` | 1 / 4 | **Em uso** |
| **Total** | **70 tabelas** `Pag_*`/`NFE_*`/`NF_Entradas*` | | ~40 vazias |

## 2. Fluxo do contas a pagar

```
NF do fornecedor (entrada)                         Fornecedores (VIEW s/ Clientes_Principal)
   │
   ▼
NF_Entradas          (1 título por NF)  ⇄ Empresa 13/14 (Fat_ParamEmp.Empresa_Auxiliar)
   │ divisão em parcelas
   ▼
NFE_Parcelas         (valor, vencimento, boleto/linha digitável)      └► NFE_Parcelas_Log
   │                                                          └► Pag_ChequesEmi_Duplicata (cheque)
   │ rateio da despesa
   ├─► NFE_CCustos_DespesasReceitas (1º/2º/3º nível)  ──► Pag_DespesasReceitas
   └─► NFE_CCustos_departamento     (1º..4º nível)    ──► Pag_CCusto_Departamento
   │ pagamento / CNAB
   ▼
Pag_Baixas ──► Pag_Historicos (natureza da baixa)   Pag_Integracao(_Doc) / Pag_CreditoFornecedor
   ▼
saldo = NFE_Parcelas.Valor − Σ Pag_Baixas.Valor_Liquido
VW_Pag_Titulo_Aberto / Vw_Pagar_Saldo_PBI / Pag_Saldos
```

## 3. Título e parcelas

### 3.1 `NF_Entradas` (8 631) — título a pagar

- **PK**: `Empresa char(2)` + `Documento varchar(20)` + `Serie char(5)` + `Tipo_Fornec char(1)` +
  `Fornecedor char(5)`.
- **FKs**: `(Fornecedor,Tipo_Fornec) → Clientes_Principal(Codigo,Tipo)` (2×); `Empresa →
  Empresas.Codigo_Empresas`.
- **Valor**: `Vr_Total_Parcelas` somando **R$ 115.373.959,74**; `Data_Emissao`/`Data_Entrada` de
  2018 → 2026 (1 linha legada de 2011).
- **Domínios**: `Baixado` **S = 8 514** / `N = 117`; `Servico` 0 = 8 500 / 1 = 131;
  `Tipo_Fornec` **0 = 7 259**, 9 = 624, 2 = 587, 1 = 161. `Bloqueado`, `Emp_Origem` e `Moeda`
  **~100% NULL** (não usados nesta base).
- **Impostos/encargos no título**: `IR`, `Porc_ISS`/`Valor_ISS`, `Porc_ICMS`/`Valor_ICMS`, `INSS`,
  `BC_/Porc_/Valor_ PIS/COFINS/CSLL`, `BC_PISCOFINSCSLL`, `Porc_PISCOFINSCSLL`,
  `Valor_PISCOFINSCSLL`; `Desp_Cartoraria`, `Desp_Acessorias`, `Valor_Descontos`,
  `Valor_Outras_Despesas`, `Taxa_Adm`, `Valor_Contabil`.
- Por ano de entrada (nº / valor): 2018 140/0,2M · 2019 630/2,6M · 2020 852/4,2M ·
  2021 1 036/12,6M · 2022 1 050/10,9M · 2023 1 219/14,6M · 2024 1 178/20,1M ·
  2025 1 390/29,5M · 2026 1 135/20,6M.

### 3.2 `NFE_Parcelas` (8 736) — parcelas

- **PK**: `Empresa + Documento + Serie + Tipo_Fornec + Fornecedor + Parcela char(2)`.
- **FKs**: `(Empresa,Documento,Serie,Tipo_Fornec,Fornecedor) → NF_Entradas`;
  `(Fornecedor,Tipo_Fornec) → Clientes_Principal`.
- **Campos-chave**: `Vencimento`, `Valor` (Σ **R$ 115.373.981,22**), `Tarifas`, `Referente`,
  `CodigoBarra varchar(50)`, `LinhaDigitavel varchar(100)`, `Bloqueado`, `ValorDesconto`/
  `DataDesconto`, `Operacao char(2)`, boleto (`Banco/Agencia/Digito_Agencia/Conta_Agencia/
  Digito_Conta`), `Emit_Papeleta`/`Sit_Papeleta`, `SISPag`/`Id_SISPag` (SISPag **100% N**),
  `DataEntradaParcela`, `idParcela`.
- Vencimentos **20/06/2017 → 05/02/2029**. Por ano: 2018 134 · 2019 629 · 2020 853 · 2021 1 041 ·
  2022 1 031 · 2023 1 199 · 2024 1 191 · 2025 1 388 · 2026 1 206 · 2027 41 · 2028 20 · 2029 2.
- `Sit_Papeleta` traz códigos de 6 dígitos legados (ex.: `000552`) — **não é status do título**
  (usar `NF_Entradas.Baixado` + baixas); é controle de papeleta impressa.
- **`NFE_Parcelas_Log`** (3 991, PK `ID`): auditoria de vencimento/valor (`Tipo`,
  `DataHora`, `Usuario`).

## 4. `Pag_Baixas` — baixas (pagamentos)

- **PK**: `Empresa + Documento + Serie + Tipo_Fornec + Fornecedor + Parcela + Parcial(int)`.
- **FKs**: `(Empresa,Documento,Serie,Tipo_Fornec,Fornecedor,Parcela) → NFE_Parcelas`;
  `Cod_Historico → Pag_Historicos`.
- **Colunas**: `Data_Baixa`, `Data_Hora_Baixa`, `Valor_Pago`, `Desconto_Recebido`, `Juros_Pagos`,
  `Valor_Liquido`, `Cod_Historico char(2)`, `Complemento`, banco/agência/conta
  (`Nr_Banco/Nr_Agencia/Dig_Agencia/Nr_Conta/Dig_Conta`), `Nr_Cheque`, `Usuario_Baixa`,
  `Bloqueado`, `DataLancamento`, `Id_BcoLanc`, `SisPag`/`NroPag_SISPag`,
  `VariacaoCambialAtiva/Passiva`, `Tarifa decimal(16,10)`, `idBaixa`.
- **Valores**: `Valor_Pago` Σ **R$ 111.118.508,53**; `Valor_Liquido` Σ **R$ 111.117.669,71**;
  `Tarifa` ~0. Período 2018 → 2026.
- **Baixas parciais: `Parcial > 1` = 0** (sempre cota única nesta base, diferente do AR).
- `SisPag`: NULL = 1 414 / N = 7 189.

### 4.1 Natureza da baixa (`Pag_Historicos`, 8 registros)

| Cód | Nome | Tipo | Compensa | Banco | Baixas | Valor líquido |
|-----|------|:----:|:--------:|:-----:|-------:|--------------:|
| 07 | Baixa por internet | 0 | N | N | 7 554 | 105,83M |
| 01 | Pagamento Total de Título | 1 | N | S | 584 | 0,51M |
| 06 | Baixa por Cheque | 0 | N | N | 436 | 4,66M |
| 02 | Pagamento Parcial de Título | 2 | N | S | 28 | 0,03M |
| 08 | Baixa parcial internet | 2 | N | S | 1 | 0,09M |
| 03 | Devolução Total de Título | 4 | N | N | — | — |
| 04 | Devolução Parcial de Título | 5 | N | N | — | — |
| 05 | Estorno de Lançamento | 5 | N | N | — | — |

O dicionário do CP é **próprio** (não compartilha códigos com `Rec_Historicos`): aqui **0 = baixa
operacional (internet/cheque)**, 1 = total, 2 = parcial e 4/5 = devolução/estorno.

## 5. Cheques emitidos e integração bancária

- `Pag_ChequesEmi_Duplicata` (8 237) — **PK `Empresa + Incremento`**; liga o cheque emitido ao
  título (`Documento+Serie+Tipo_Fornec+Fornecedor+Parcela+Parcial`), guarda
  `Banco/Nro_Cheque/Agência/Conta`, `Empresa_Cheque`, `Integracao`. Bancos: **001** 4 687 ·
  **237** 1 612 · **033** 1 361 · `BLU` 577. `Integracao` 100% NULL.
- `Pag_Integracao` (403) / `Pag_Integracao_Doc` (411) — cabeçalho/itens de **integração de
  pagamento** com `Cliente char(18)` (código 900006 = fornecedor interno), `Dinheiro`, `Credito`,
  `Diferenca`, `Saldo_Ant`, `Saldo_Int`, `CredCliente`, `DiferencaDias`; período 2018-09 → 2025-09.
- `Pag_CreditoFornecedor` (2; PK `Incremento`) — crédito do fornecedor por devolução (`ES` E/S),
  ligado a `Pag_Integracao`; base da view `vw_pag_CREDITO_FORNECEDOR`.

## 6. Rateio: despesa/receita e centro de custo

- `NFE_CCustos_DespesasReceitas` (8 591; PK `+ Item`) — rateio do título por
  `(Primeiro_Nivel, Segundo_Nivel, Terceiro_Nivel)` → `Pag_DespesasReceitas`, com `Valor_CCusto`
  (E_S **100% S**). **6 475 documentos** com rateio.
- `NFE_CCustos_departamento` (8 576; PK `+ ItemDespRec + Item`) — segundo nível do rateio, por
  `(1º..4º nível)` → `Pag_CCusto_Departamento`; **6 464 documentos**.
- `Pag_DespesasReceitas` (91) — **plano de despesas/receitas** em 3 níveis (`Descricao`,
  `CodAbreviado`, `E_S`, `Custo_Fixo`, `isAtivo` todos `S`).
- `Pag_CCusto_Departamento` (21) — **centros de custo** em 4 níveis (`CodAbreviado`, `Descricao`,
  datas de criação/alteração, `isAtivo` todos `S`).
- `Pag_DespesasReceitas_CCustoDpto` (28) — **mapa de rateio padrão** despesa → centro de custo
  (`Porcentagem decimal(16,6)`).
- `Pag_Impostos` (2) — retenções (`ISSQN` 2,5%, `ISS` 2,0%) com fornecedor padrão, `DiaVencto`,
  `TipoImpostoRetido`; rateio em `Pag_Impostos_CCustos_DespesasReceitas` (1) e
  `Pag_Impostos_CCustos_Departamento` (1).

## 7. CNAB de pagamento e ocorrências

- `Pag_CNAB_Banco` (1) — conta/cedente, diretórios de remessa/retorno, `Ultima_Remessa`,
  `Usar_240`, `Protesto`.
- `Pag_CNAB_Mescla_240` (99) — **layout CNAB 240** (posições/tamanhos/campos) do banco **341**
  (Itaú): `Ordem`, `Tipo_Reg`, `Segmento`, `Especie`, `Pos_Inicial/Final`, `Valor`, `Tabela`,
  `Campo`, `Tipo`, `Decimal`, `Mascara`.
- `Pag_Ocorrencia` (5) — dicionário de ocorrências por banco (237, 001, 341).
- `Pag_Ocorrencia_Motivo` (371) — motivos por ocorrência (`Codigo char(2)` + `Descricao`), ex.:
  `AA` arquivo duplicado, `BG` CGC/CPF inválido.
- `Pag_RetornoCNAB_TipoCampo` (14) — mapeia campo do retorno → significado (`00` tipo arquivo,
  `02..06` motivos, `07` data pagamento, `08` valor parcela, `11` valor pagamento, `12` título pago,
  `13` nº do pagamento).

## 8. Parâmetros e cadastros

- `Pag_Parametros` (1) — **parâmetros globais do CP** (extenso): históricos padrão de baixa por
  forma (`Hist_BaixaTotal/Parcial*` dinheiro/cheque/crédito/adiantamento), integração contábil/
  bancos, `Valor_Minimo_Autorizacao`/`Usar_Autorizacao_Pagamento`/`Codigo_Aprovador`, COMPROR,
  centro de custo em 4 níveis, `Ult_PagSaldos`/`Ult_PagTitAb`, impostos.
- `Pag_Diario` (4; PK `Empresa`) — numeração de livro/razão/página, obrigatoriedade de CC,
  conta de depósito padrão.
- `Pag_Tipos_Fornecedores` (11) — `0` Fornecedores, `1` Obrigação Social, `2` Obrigação Fiscal,
  `3` Seguros, `4` Leasing, `5` Empréstimo, `6` Financiamentos, `7` Títulos, `8` Diversos,
  `9` Outros, `A` **Impostos** (`Imposto = 'S'`). É a chave `Tipo_Fornec` de todo o módulo.
- `Fornecedores` é **VIEW** (`Clientes_Principal WHERE Tipo_Entidade <> 'C'`) — não há tabela física
  de fornecedor; `Clientes_Principal.Tipo` (0 = 1 669, 9 = 6, 2 = 3, 1 = 2, A = 1) é o
  `Tipo_Fornec` do CP.
- `Pag_Operacoes` (1, `01 TESTE`), `Pag_Ramos` (1), `Pag_HistBaixaConta` (1) — cadastros residuais.

## 9. Views (o “contrato pronto”)

| Objeto | Linhas | Conteúdo |
|--------|-------:|----------|
| `VW_Pag_Titulo_Aberto` | 133 | Título em aberto por parcela: `Valor_Saldo = Valor_Parcela − Σ Valor_Liquido`, `Dias = DateDiff(vcto, hoje)`; `HAVING Σ < Valor` |
| `Vw_Pagar_Saldo_PBI` | 133 | Idêntico + `Razao_Social` via `Fornecedores`; `HAVING Valor_Saldo > 0` |
| `vw_pagar_Baixa_PBI` | 5 945 | Baixas desde 2022 (`Data_Baixa >= 2022`), só títulos **quitados** (`HAVING saldo = 0`) |
| `Pag_Saldos` | 8 967 | **Razão** débito (`Pag_Baixas`, Σ `Valor_Liquido`) × crédito (`NF_Entradas`, Σ `Vr_Total_Parcelas`) por empresa/fornecedor/período |
| `vw_pag_CREDITO_FORNECEDOR` | 2 | Entrada×Saída de crédito de fornecedor, por fornecedor |

> Views com nome `*_Cond_Pagto` (`VW_Car_Romaneio_Cond_Pagto`, `VW_Fat_Cond_Pagto`) são de
> **condição de pagamento** (Estudos 28/29), não de contas a pagar.

## 10. Procs e triggers

- **Procs que referenciam**: `NF_Entradas` **52**, `NFE_Parcelas` **46**, `Pag_Baixas` **38**,
  `Pag_DespesasReceitas` **18**, `NFE_CCustos_DespesasReceitas` **13**. Núcleo do CP:
  - Entrada/baixa: `Ret_Lanca_Entradas`, `sp_Gerar_Pagar_SemiPronta`, `SP_Transfere_CP`,
    `SP_Pag_GeraNota`, `SP_Pag_Troca_Despesa_CC_DeptoInativo`.
  - Custo/contábil: `SP_CmT_GeraCCustoLFE`, `SP_Cont_Importa_CCusto_Lancto`,
    `SP_ContRel_CCusto_Niveis`, `sp_PagRel_CCusto_Niveis`, `SP_PRJ_CustoObra`,
    `Gera_Liv_Entrada`/`Gera_Liv_Fornecedores`.
  - Relatórios: `SP_Pag_RelBaixas`, `SP_Pag_RelTituloAb`, `SP_Pag_RelResumo_Tit_Aberto`,
    `SP_Pag_RelRazaoAuxiliar`, `SP_Pag_RelDiarioAuxiliar`, `SP_Pag_RelEntMercadoria`,
    `SP_Pag_ConferenciaPorUsuario`, `SP_Vencido_Avencer`, `SPRPT_REL_CCUSTO`,
    `SRPT_BAIXAS`, `SRPT_MOV_VENCER`, `SRPT_MOV_VENCIDOS`, `SRPT_PAGAR_RECEBER`.
  - Fluxo: `sp_fluxo_ContasAPagar(_ContaBancaria)`, `SP_Fluxo_GerarFluxoPorEmpresa`,
    `SP_ImportaPagarFluxo`, `SP_RelCompromisso`, `SP_RelProjecao`.
  - Integração/fiscal: `SP_EFD_ImportaPagarGeral`, `SP_EFD_ListaNotasPagar`,
    `SP_Liv_Prosoft_*`, `sp_liv_Dominio_BaixaParcelas*`, `SP_Gera_Lancamentos_Folhamatic`,
    `sp_GeraNFE_de_NFS(_Filial)`, `SP_Notas_CP_Problemas`.
- **Triggers** em tabelas do CP: `NF_Entradas` (`TG_INS_NF_Entradas_DtLanc`,
  `Tg_NF_Entradas_Fech_Ins/Upd/Del`, `TG_{INS,UPD,DEL}_NF_Entradas_Autorizacao`,
  `TG_Del_FOL_DeletaContasaPagar`), `NFE_Parcelas` (`Tg_NFE_Parcelas_Fech_*`),
  `NFE_CCustos` (`Tg_NFE_CCustos_Fech_*`), `Pag_Baixas` (`TIUD_Baixas`,
  `TG_INS_Pag_Baixas_DtLanc`, `Tg_Pag_Baixas_Fech_*`, `Tg_Pag_UptObsRecibo_Ins`),
  `Pag_Integracao` (`TG_INS_Pag_Integracao_DtLanc`), `Pag_Titulo_Lancamentos` (`..._Fech_*`).

## 11. Regras e recomendações para a API/ETL

1. **Saldo por parcela** = `NFE_Parcelas.Valor − Σ Pag_Baixas.Valor_Liquido`, com **`HAVING` saldo
   > 0** (regra de `VW_Pag_Titulo_Aberto`/`Vw_Pagar_Saldo_PBI`). Chave de junção:
   `Empresa + Documento + Serie + Tipo_Fornec + Fornecedor + Parcela` (**sem `Parcial`** no
   agrupamento — o saldo considera todas as baixas da parcela).
2. **`Fornecedores` é view** (`Tipo_Entidade <> 'C'`): materializar no Neon como
   `dim_fornecedor` derivada de `Clientes_Principal`, chave `(Tipo, Codigo)`.
3. **Empresa auxiliar**: aplicar a mesma `Fat_ParamEmp.Empresa_Auxiliar` (13 → 14, 01 → 02) para
   excluir duplicidade nos relatórios de CP.
4. **Históricos**: usar o dicionário **`Pag_Historicos`** (códigos próprios); `Tipo_Hist = 0` é
   baixa operacional (internet/cheque) e **conta como pagamento**.
5. **Rateio**: `NFE_CCustos_DespesasReceitas` (despesa 3 níveis) + `NFE_CCustos_departamento`
   (CC 4 níveis). O rateio é **opcional** (~75% dos títulos têm rateio).
6. **Impostos retidos**: já vêm no título (`NF_Entradas.Valor_IR/ISS/PIS/COFINS/CSLL/INSS`) e há
   cadastro `Pag_Impostos` para retenções padrão.
7. **Cheque**: `Pag_ChequesEmi_Duplicata` liga cheque emitido → parcela; `Pag_Integracao` é o
   lote de conciliação com o cliente interno 900006.
8. **Watermarks**: `Pag_Baixas.Data_Hora_Baixa`/`DataLancamento`, `NF_Entradas.Data_Hora`,
   `NFE_Parcelas_Log.DataHora`. `NF_Entradas.Data_Entrada` para carga inicial.
9. **Não usar** (vazias): `Pag_Remessa`, `Pag_Transacao`, `Pag_Pagamento`,
   `Pag_Parcelas_SISPAG`/`Pag_SisPag_*`, `Pag_CNAB_Retorno*`, `Pag_GrupoFornecedor*`,
   `Pag_Contrato`/`Pag_TipoContrato`, `Pag_Titulo_Lancamentos`, `NF_Entradas_Impostos`,
   `Pag_Recibo_Pagto*`, `Pag_Despesas*` (exceto as citadas).

## 12. Gotchas encontrados

- **`Fornecedores` não é tabela**: é `VIEW` sobre `Clientes_Principal`; `NF_Entradas` referencia
  `Clientes_Principal` diretamente. Já `Vw_Pagar_Saldo_PBI`/`vw_pagar_Baixa_PBI` usam a view.
- `NF_Entradas` e `Pag_Baixas` **não têm `Parcial` no lado das parcelas** para o saldo; o join de
  abertura ignora `Parcial` de propósito (nesta base não há `Parcial > 1`).
- Divergência mínima de total: `NF_Entradas.Vr_Total_Parcelas` = **115.373.959,74** ×
  `NFE_Parcelas.Valor` = **115.373.981,22** (Δ **R$ 21,48**) — somar pelo nível de título usa
  `NF_Entradas`; pelo nível de parcela usa `NFE_Parcelas`.
- `Pag_Saldos` é **razão por fornecedor** e usa apenas `Valor_Liquido` (débito) e
  `Vr_Total_Parcelas` (crédito): débito **111.117.669,71** × crédito **115.373.959,74**.
- `NF_Entradas.Bloqueado`, `Emp_Origem`, `Moeda` e `Pag_Baixas.Tarifa` são **efetivamente NULL/0**
  — não usar como filtro.
- `Sit_Papeleta` (`char(6)`) **não é status**; `SISPag` no CP está **100% 'N'** (SISPAG não usado,
  ao contrário do que o nome sugere).
- `Tipo_Fornec` é `char(1)` com o **alfanumérico `A` = Impostos** — ordenar/agrupar como texto.
- `NFE_Parcelas` e `NF_Entradas` têm só **3 índices cada**; consultas analíticas devem projetar
  colunas e filtrar por `Empresa`/`Vencimento` para não varrer 8 mil linhas por parcela.

## 13. Próximos passos

- **Fluxo de caixa**: `SP_Fluxo_GerarFluxoPorEmpresa`, `SP_RelProjecao`/`SP_RelCompromisso` e a
  conciliação AR (Estudo 30) × CP (este estudo) por conta bancária.
- **Financeiro bancário** (`Bco_*`/`Ch_*`/`Contas_e_Agencias`) e CNAB 240 unificado.
- **Fiscal/EFD**: `SP_EFD_ImportaPagarGeral`/`SP_EFD_ListaNotasPagar` ligando CP ao Estudo 12.
