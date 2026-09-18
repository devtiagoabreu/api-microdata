# Estudo 32 — Fluxo de Caixa

Aprofundamento do **fluxo de caixa**: como o ERP projeta recebimentos, pagamentos, cheques e
saldo bancário. Diferente dos módulos anteriores, **não há tabela-fato persistida**: o fluxo é
**100% derivado sob demanda** a partir de AR, CP, bancos, cheques, compras e câmbio. Levantamento
por `SELECT` somente leitura. Complementa o [Estudo 23](./23-financeiro-contabil-custos.md)
(financeiro/contábil) e fecha o triângulo com o [Estudo 30](./30-contas-a-receber-rec.md) (AR) e o
[Estudo 31](./31-contas-a-pagar-pag.md) (CP).

## 1. Síntese

| Papel | Objeto | Linhas | Estado |
|-------|--------|-------:|--------|
| Resultado do fluxo por empresa | `Fluxo_Caixa` | 88 | **Scratch/report** (snapshot 12–16/05/2025) |
| Fluxo semanal (7 dias) | `Fluxo_Semanal` | 88 | **Scratch/report** (legado) |
| Working table do gerador | `Fluxo_Caixa_Empresa` | 0 | Scratch (`DELETE`+`INSERT` em runtime) |
| Saldo inicial (empresa×produto) | `Saldo_Inicial` | 0 | **Vazia** |
| Câmbio / correção / juros | `Dolar` | **2 066** | **Em uso** (2002 → 2026) |
| Contratos de financiamento/leasing | `Fin_*` (10 tabelas) | 1 | Só `Fin_Parametros`; restante vazio |
| Demais `Fluxo_*` (16 tabelas) | `Fluxo_Rec/Pag/ParamImp/…` | 0 | **Vazias** (verticais/importadores) |

> Não existe uma tabela `Fluxo_Caixa` dimensional nem snapshots por data. Toda projeção é
> calculada por procedures a partir das pontas AR/CP/bancos — o **“contrato” é o conjunto de
> procs**, não uma view.

## 2. Arquitetura

```
Fontes                                             Projeção (on-demand)
─────────────────────────────────────────────     ─────────────────────────────
AR  Notas_Fiscais_Parcelas / Rec_Baixas ─┐
    (+ VW_Rec_Duplicata_Aberto)          │
CP  NFE_Parcelas / Pag_Baixas ───────────┼──►  sp_fluxo_ContasAReceber
    (+ VW_Pag_Titulo_Aberto)             │      sp_fluxo_ContasAPagar
Bancos Bco_Lancamentos / Contas_e_Agencias┼──► sp_fluxo_ContasBancarias
Cheques Ch_Cheques ──────────────────────┤      sp_fluxo_Faturamento
Compras Fat_Pedido / SIMCompras ─────────┤      sp_fluxo_Resultado
Câmbio Dolar ────────────────────────────┘      SP_Fluxo_GerarFluxoPorEmpresa
                                                 SP_Fluxo_Vencimento / SP_Fl_Rel_*
                                                       │
                                                       ▼
                                        #temp tables → resultado (Fluxo_Caixa*)
```

**Parâmetros de entrada** (empresas, período, dias de graça, operações, dólar) normalmente vivem
em **tabelas temporárias de sessão** (`#tmpFluxoParametros`, `#tmpEmpresaFluxo`,
`#tmpEmpresaAuxiliarFluxo`, `#tmpEmpresaProvisaoFluxo`), criadas pelo front **antes** de chamar a
proc — ver §5.

## 3. Fontes de dados

### 3.1 Contas a receber (entrada)
- `Notas_Fiscais_Parcelas` + `Rec_Baixas` (+ `Notas_Fiscais_Rec`) e a view
  `VW_Rec_Duplicata_Aberto`. Cheques de terceiros entram por `Ch_Cheques` (módulo de cheques,
  **vazio nesta base** — ver Estudo 30).
- Empresas auxiliares excluídas via `Fat_ParamEmp.Empresa_Auxiliar` (13→14, 01→02).

### 3.2 Contas a pagar (saída)
- `NFE_Parcelas` + `Pag_Baixas` + `NF_Entradas`; opcionalmente `SIMCompras` (compras futuras via
  `Fat_Pedido`) e **provisões**.

### 3.3 Bancos e cheques
- `Bco_Lancamentos` (Estudo 33) + `Contas_e_Agencias` (saldos/limites/extratos).
- `Pag_ChequesEmi_Duplicata` (cheques emitidos × títulos, Estudo 31).

### 3.4 Câmbio, correção e juros — `Dolar` (2 066)
- Séries diárias 2002-01-21 → 2026-09-17: `Valor_Dolar`, `Valor_TR`, `Desp_Bancaria`,
  `Instrucao`, `Juros_Mes`, `Juros_CH`, `Juros_Pag`, `Juros_Fat`, `Juros_Liv`, `Juros_Orc`,
  `Juros_Recauch`, `Juros_CCD`, `Juros_Loj`.
- É a tabela de **indexadores**: cotação do dólar (conversão de títulos em moeda estrangeira
  quando `NF_Entradas.Moeda`/`Notas_Fiscais_*` usa moeda) e taxas de juros por carteira/produto.
- No gerador: `@ValorDolar = (SELECT Valor_Dolar FROM Dolar WHERE Data < @Vencimento)`; valor
  convertido = `valor / @ValorDolar`.

## 4. Procedures (o “contrato”)

| Proc | Objetivo | Entradas |
|------|----------|----------|
| `sp_fluxo_ContasAReceber(_ContaBancaria)` | Fluxo de **recebimentos** (título, empresa, parcela, empresa auxiliar, devolvidos/cheques) | `#tmpFluxoParametros`/`#tmpEmpresa*` |
| `sp_fluxo_ContasAPagar(_ContaBancaria)` | Fluxo de **pagamentos** (títulos, auxiliares, provisões, compras) | idem |
| `sp_fluxo_ContasBancarias(_ContaBancaria)` | Fluxo **bancário** (saldo/limite por conta via `Bco_Lancamentos`) | idem |
| `sp_fluxo_Faturamento` | Faturamento diário/semanal (entrada prevista) | idem |
| `sp_fluxo_Resultado(_ContaBancaria)` | **Resultado consolidado** (entradas − saídas por dia) | idem |
| `SP_Fluxo_GerarFluxoPorEmpresa` | Gerador clássico por empresa | `@Empresa, @GrupoEmpresa, @Operacoes, @DataInicio, @DataFim, @UsarDiaGraca, @ImprimeDolar, @RelacionarCheque, @SepararFornecedor, @DiasGraca` + **OUTPUT** `@ValorReceberAtraso, @ValorPagarAtraso, @ValorChequeAtraso` |
| `SP_Fluxo_Vencimento` | Fluxo resumido de CP por vencimento (usa `VW_Pag_Titulo_Aberto`) | `@D1, @D2, @SaldoTela, @ListarSabDomFer, @DiasDaGraca` |
| `SP_Fl_Rel_FluxoporTipoConta` | Fluxo por **tipo de conta** (movimento/limite/garantida) | `@DataI, @DataF, @Tp_Tab_*` |
| `SP_Fl_RelContrato` / `SP_Fluxo_Carteira` | Contratos de financiamento / carteira | `@DataI, @DataF, @Tp_Tab_*` / `@Empresa, @DtIn, @DtFn` |
| `sp_FluxoGerencial` | Fluxo gerencial por despesa/CCusto | `@DatIni, @DatFim, @Condicao, @Tipo` |
| `Fnc_Proximo_Data_Util` / `FNC_POEZEROS` / `FNC_VlParamEmpSis` | Funções de apoio (dia útil, máscara, parâmetro por empresa) | — |

> **Todas as variantes `*ContaBancaria`** repetem a mesma lógica filtrando por conta; `_D`/`_M`
> (dia/mês) são pares de fechamento (§5).

## 5. Fechamento financeiro (`SP_Fl_Fech_Fin_*`)

Família de procs que monta o **fechamento financeiro/registro de caixa** (visão diária `_D` e
mensal `_M`) com subtotais por natureza:

- Movimento de caixa: `SP_Fl_Fech_Fin_Reg_Cx_D`/`_M` → `Tmp_RegCaixa_Resultado`.
- Por despesa/centro de custo: `SP_Fl_Fech_Fin_Reg_Cx_DespCCusto_D`/`_M`
  (`Pag_Baixas` + `NF_Entradas`).
- Crédito: `SP_Fl_Fech_Fin_Reg_Cx_Credito_D`/`_M`.
- Bancos: `SP_Fl_Fech_Fin_Reg_Cx_SIMBanH_D`/`_M` (`Bco_Lancamentos`) e
  `SP_Fl_Fech_Fin_Reg_Cx_SIMBanBAC_D`/`_M`.
- Cheques: `SP_Fl_Fech_Fin_Reg_Cx_SIMCheques_D`/`_M`.
- Recebimentos: `SP_Fl_Fech_Fin_Reg_Cx_SIMRec_D`/`_M`.

Os resultados vão para tabelas **`Tmp_Fin_Reg_Cx_*` / `Tmp_RegCaixa_Resultado`** criadas
**dentro das próprias procs** (`CREATE TABLE` em runtime) → **não persistem** em `sys.tables`.

## 6. Tabelas de resultado (scratch/legado)

- **`Fluxo_Caixa`** (88) — snapshot de 12–16/05/2025 por cliente: colunas
  `Receber`, `Pagar`, `Cheque`, `Pagar_Outros`, `SIMCompras`, `CREDIARIO`, `Carteira`,
  `Pagar_COMPROR`, `Bancos` (somas do snapshot: Receber 458 mil, Pagar 629 mil).
- **`Fluxo_Semanal`** (88) — projeção em `Dia1..Dia7`+`Outros`, `Rec_Pag` R=67/P=21
  (legado; nenhuma proc atual referencia).
- **`Fluxo_Caixa_Empresa`** (0) — working table de `SP_Fluxo_GerarFluxoPorEmpresa`
  (`DELETE` + `INSERT` a cada execução), com `(Empresa, Data, Descricao, Receber, Pagar,
  Cheque, Pagar_Outros)`.
- As demais 16 `Fluxo_*` (recorrências `Fluxo_Rec/Pag`, importadores `Fluxo_ParamImp*`,
  `Fluxo_*CCusto`) estão **vazias**.

> Todas são **voláteis**: não servem de fonte para ETL. O ETL deve recalcular o fluxo.

## 7. Regras e recomendações para a API/ETL

1. **Recalcular, não copiar**: o fluxo não tem tabela-fato. No Neon, criar **marts** de projeção
   (`mart_fluxo_caixa`) via ETL a partir de AR/CP/bancos/cheques, com a mesma semântica:
   `Receber` (AR em aberto por vencimento) − `Pagar` (CP em aberto) + movimento bancário.
2. **Fontes canônicas**: usar as views-contrato
   `VW_Rec_Duplicata_Aberto` (Estudo 30) e `VW_Pag_Titulo_Aberto` (Estudo 31) como entradas de
   AR/CP — é o que `SP_Fluxo_Vencimento`/`SP_Fl_Rel_FluxoporTipoConta` já fazem.
3. **Dia útil / dia de graça**: replicar `Fnc_Proximo_Data_Util` e `@DiasGraca` (parâmetro em
   `SP_Fluxo_GerarFluxoPorEmpresa`/`SP_Fluxo_Vencimento`); o calendário vem de
   `Fnc_Proximo_Data_Util`, não de tabela.
4. **Câmbio/juros**: joinar `Dolar` por `Data < vencimento` (última cotação anterior) para
   títulos em moeda e para correção; taxas de juros por carteira (`Juros_CCD`, `Juros_Loj`, …).
5. **Cheques**: `Ch_Cheques` está vazia → a parcela "Cheque" do fluxo é 0 nesta base
   (não confundir com `Pag_ChequesEmi_Duplicata`, que é cheque *emitido* no CP).
6. **Empresa auxiliar/provisão**: o gerador separa `#tmpEmpresaFluxo`,
   `#tmpEmpresaAuxiliarFluxo` e `#tmpEmpresaProvisaoFluxo`; manter as 3 categorias no mart.
7. **Não portar** as procs de UI (`sp_fluxo_*` sem parâmetros): dependem de `#temp` de sessão;
   reimplementar em SQL/Python.
8. **Watermarks**: usar `Rec_Baixas.Data_Hora_Baixa`, `Pag_Baixas.Data_Hora_Baixa`,
   `Bco_Lancamentos.Data` — o fluxo em si não guarda data de geração.

## 8. Gotchas encontrados

- `sp_fluxo_*` **não têm parâmetros declarados** — o “contrato” real é um conjunto de tabelas
  temporárias de sessão (`#tmpFluxoParametros`, `#tmpEmpresaFluxo`, …). Não são chamáveis
  diretamente pela API sem montar o contexto.
- `SP_Fluxo_GerarFluxoPorEmpresa` **grava em `Fluxo_Caixa_Empresa`** (não em `Fluxo_Caixa`),
  limpando a tabela a cada execução — é estado compartilhado/volátil.
- `Tmp_Fin_Reg_Cx_*`/`Tmp_RegCaixa_Resultado` são **criadas dentro das procs** — não existem como
  tabelas no catálogo (não há history para CDC).
- `Fluxo_Caixa`/`Fluxo_Semanal` são **snapshots antigos** (mai/2025) e `Fluxo_Semanal` não é
  sequer referenciada por nenhuma proc atual — tratar como legado, não como fonte.
- `Saldo_Inicial` (saldo inicial por empresa×produto) e todas as `Fluxo_*` de recorrência/importação
  estão **vazias** — o saldo inicial do fluxo não está materializado.
- `Dolar` é indexador **genérico** (dólar + TR + juros por carteira) — não é só cotação; `Juros_*`
  cobre cheques/pag/fat/loja/CCD.
- Módulo `Fin_*` (financiamentos/leasing) está **vazio** (só `Fin_Parametros`) — não é fonte de
  fluxo nesta base.

## 9. Próximos passos

- **Estudo 33 — Financeiro bancário** (`Bco_Lancamentos`, `Bco_Historicos`,
  `Contas_e_Agencias`, CNAB 240): a fonte de saldo/movimento usada pelo fluxo.
- **Conciliação**: cruzar `Bco_Lancamentos` × `Pag_Baixas`/`Rec_Baixas` (baixas × extrato).
- **Mart de fluxo no Neon**: somar AR/CP por vencimento + saldo bancário atual como saldo inicial.
