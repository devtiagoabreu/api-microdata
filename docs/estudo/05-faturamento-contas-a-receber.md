# Estudo 05 — Faturamento e contas a receber (módulo `Rec_*`)

Levantado em **SELECTs somente leitura** no banco `DBMicrodata_DGB`. Contém apenas estrutura,
relações e **contagens/agregados** — nenhum dado real sensível.

## 1. Visão geral

O contas a receber recebe o que foi gerado no faturamento (Estudo 04: `Fat_Pedido`) e organiza
em **documento financeiro → parcelas → baixas (recebimentos)**:

```
Fat_Pedido (NF) ──► Notas_Fiscais_Rec (cabeçalho do documento) ──► Notas_Fiscais_Parcelas (parcelas)
                                                                              │
                                              Notas_Fiscais_Vendedores_Parcelas (comissão por vendedor)
                                                                              ▼
                                                                    Rec_Baixas (recebimentos/baixas)
```

### `Notas_Fiscais_Rec` — cabeçalho do documento — 11 739 registros

- **PK:** `(Nr_Empresa_NF, Nr_Documento_NF, Serie)`.
- FKs: `Cliente_NF → Clientes_Principal(Codigo_Cliente)`, `Nr_Empresa_NF → Empresas`.
- Colunas principais: `Emissao_NF`, `Total_Parcelas_NF`, `Vr_Total_Doc_NF`, `Outros_Acrescimos_NF`,
  `Codigo_Parcelamento_NF`, `Emp_Origem`, `Baixado` (`'S'`/`'N'`), `Bloqueado`, `DataLancamento`,
  `Data_Hora`, `Usuario`, `idDocumento`.
- `Codigo_Parcelamento_NF` é um **código livre** (sem FK/cadastro no banco); nas definições é só
  carregado/agrupado, não decodificado — validar com o negócio.

### `Notas_Fiscais_Parcelas` — parcelas (desdobro do documento) — 29 885 registros

- **PK:** `(Empresa_Parcelas, Documento_Parcelas, Serie, Parcela_Parcelas)`.
- FK para o cabeçalho: `(Empresa_Parcelas, Documento_Parcelas, Serie) → Notas_Fiscais_Rec`.
- Mais FKs: `Operacao_Parcelas → Rec_Operacoes`, banco/agência/conta → `Contas_e_Agencias`.
- Colunas de vencimento/valor: `Vencimento_Parcelas`, `Vecto_Extenso_Parcelas`, `Valor_Parcelas`.
- Dados de boleto/cobrança: `Banco_/Agencia_/Nr_Conta_Age_/Operacao_Parcelas`, `Nosso_Nr_Parcelas`,
  `Bol_Fixo`, `Bol_Variavel`, `Bol_Carteira`, `Bol_Cedente`, `LinhaDigitavelPrimero..Oitavo`,
  `Porc_Multa/Valor_Multa`, `Porc_Desconto/Vr_Desconto/Vencto_Desconto`, `Tem_Baixas`.
- Flags de cobrança por e-mail: `boleto_email_enviado`, `boleto_vencido_email_enviado`,
  `boleto_protesto_email_enviado`.

### `Rec_Baixas` — recebimentos/baixas — 28 903 registros

- **PK:** `(Empresa, Documento, Serie, Parcela, Parcial)` (a coluna `Parcial` permite baixa
  rateada/lançamento parcial em uma parcela).
- Colunas principais: `Data_Baixa`, `Valor_Recebido`, `Desconto_Concedido`, `Juros_Recebidos`,
  `Valor_Liquido`, `Cod_Historico`, `Complemento`, banco/agência/conta/operação, `Tarifas`,
  `Data_Hora_Baixa`, `Usuario_Baixa`, `Maquina`, `EmpPagto`, `Controle_Recebimento`, `Bloqueado`,
  `Porc_PIS/Valor_PIS`, `Porc_COFINS/Valor_COFINS`, `VariacaoCambialPassiva/Ativa`.
- **Saldo de uma parcela** = `Valor_Parcelas − Σ(Rec_Baixas.Valor_Liquido)` da mesma
  `(Empresa, Documento, Serie, Parcela)` (regra usada pela view `Rec_EmAberto`, abaixo).

### `Rec_Operacoes` — operações de cobrança — 3 códigos

| Código | Nome |
|--------|------|
| `01` | COBRANCA |
| `02` | CARTAO DE CREDITO |
| `BL` | CARTEIRA BLU |

### Complementos

- `Notas_Fiscais_Vendedores_Parcelas` (29 886) — vínculo **parcela × vendedor** (comissão),
  usado pela view `Rec_EmAberto`.
- `Notas_Fiscais_Parcelas_Log`/`_Obs`/`_Situacao` — auditoria/observações/situações das parcelas.
- `Fnn_DocumentoParcelaBaixa` (265) — parcela com baixa por permuta/financeiro.

## 2. A view canônica "duplicatas em aberto" — `Rec_EmAberto`

É a fonte oficial de saldo em aberto (equivalente usado pelas telas/relatórios):

- Junta `Notas_Fiscais_Rec` + `Notas_Fiscais_Parcelas` (pela PK) e enriquece com
  `Notas_Fiscais_Vendedores_Parcelas` (vendedor) e `Clientes_Principal` (razão social).
- **Saldo**: `Valor = Σ(np.Valor_Parcelas) − Σ(rb.Valor_Liquido)` (baixas da mesma parcela).
- Retorna apenas linhas com `Valor > 0` (HAVING).

Equivalentes: `Rec_EmAberto_Geral`, `VW_Rec_Duplicata_Aberto`, `VW_Rec_DuplicatasEmAberto`,
`VW_Rec_Duplicata_Baixadas`, `Vw_Rec_Baixas_Qlik`, `Vw_Rec_Saldo_Qlik`, `Vw_Rec_Atrasos`,
`FN_Rec_DuplicatasEmAberto`.

## 3. Dados observados (somente contagens)

**`Notas_Fiscais_Rec`** — período `2018-07-26` a `2026-09-17`, soma de `Vr_Total_Doc_NF` ≈ **R$ 132,7 mi**:
- `Baixado`: `'S'` 11 329 · `'N'` 410.
- `Emp_Origem`: `'13'` 11 386 · `'14'` 342 · `'  '` 10 · `NULL` 1.
- `Serie`: `'1  55'` 11 738 · `'-'` 1 (o formato sugere série concatenada — validar).

**`Notas_Fiscais_Parcelas`** — vencimentos de `2018-07-26` a `2027-03-14`, soma ≈ **R$ 132,7 mi**:
- `Tem_Baixas`: `'S'` 28 863 · `' '` 21 · `NULL` 1 001.

**`Rec_Baixas`** — período `2018-08-01` a `2026-09-17`, soma `Valor_Liquido` ≈ **R$ 128,7 mi**;
por ano: 2018 R$ 1,1 mi … 2025 R$ 27,3 mi · 2026 (parcial) R$ 19,6 mi; empresas `'13'` 28 029 · `'14'` 874.

## 4. Consultas úteis para a API nova (somente leitura)

```sql
-- Saldo em aberto (já decodificado, usa a view canônica)
SELECT * FROM Rec_EmAberto WHERE Empresa = '13';

-- Parcelas com histórico de baixas
SELECT p.Empresa_Parcelas, p.Documento_Parcelas, p.Parcela_Parcelas,
       p.Vencimento_Parcelas, p.Valor_Parcelas,
       ISNULL((SELECT SUM(rb.Valor_Liquido) FROM Rec_Baixas rb
               WHERE rb.Empresa = p.Empresa_Parcelas
                 AND rb.Documento = p.Documento_Parcelas
                 AND rb.Serie = p.Serie
                 AND rb.Parcela = p.Parcela_Parcelas), 0) AS Recebido,
       p.Valor_Parcelas - ISNULL((SELECT SUM(rb.Valor_Liquido) FROM Rec_Baixas rb
               WHERE rb.Empresa = p.Empresa_Parcelas
                 AND rb.Documento = p.Documento_Parcelas
                 AND rb.Serie = p.Serie
                 AND rb.Parcela = p.Parcela_Parcelas), 0) AS Saldo
FROM Notas_Fiscais_Parcelas p
WHERE p.Empresa_Parcelas = '13';
```

## 5. Observações e próximos passos

- Não existe FK formal `Fat_Pedido → Notas_Fiscais_Rec`: a ponte faturamento × contas a receber
  é feita por procedures de geração (`SP_Rec_GeraDoc`, `SP_Rec_GeraNota`, `sp_GeraNFE_de_NFS`, ...).
  Validar com o negócio a regra exata de vinculação (NF ↔ documento).
- `Codigo_Parcelamento_NF` e o formato de `Serie` precisam de validação de negócio.
- Próximo passo: estudar as procedures de geração (`SP_Rec_GeraDoc`) para documentar a criação de
  duplicatas a partir da NF, e o módulo de **contas a pagar** (`Pag_*`).