# Estudo 06 — Contas a Pagar (módulo `Pag_*` / `NF_Entradas`)

Levantado em **SELECTs somente leitura** no banco `DBMicrodata_DGB`. Contém apenas estrutura,
relações e **contagens/agregados** — nenhum dado real sensível.

## 1. Visão geral

O contas a pagar segue o mesmo desenho do contas a receber (Estudo 05), mas nas **entradas**
(compras de fornecedor). Fluxo:

```
NF de entrada (compra/importação)
   ▼
NF_Entradas (cabeçalho do título a pagar) ──► NFE_Parcelas (parcelas) ──► Pag_Baixas (pagamentos)
                                                                   │         └──► Pag_ChequesEmi_Duplicata (cheques)
                                                                   └──► CNAB: Pag_Transacao / Pag_Remessa / Pag_Ocorrencia
```

- O **fornecedor é uma entidade de `Clientes_Principal`** identificada por `(Tipo, Codigo)`
  (índice único `Ind_Fornecedores`), onde `Tipo` é decodificado por `Pag_Tipos_Fornecedores`.
- A tabela `Liv_EntFat` do livro fiscal de entradas tem apenas 3 registros: o CP "de verdade"
  hoje vive em `NF_Entradas`/`NFE_Parcelas`.

## 2. Modelo de dados

### `NF_Entradas` — cabeçalho do título a pagar — 8 631 registros

- **PK:** `(Empresa, Documento, Serie, Tipo_Fornec, Fornecedor)`.
- FKs: `(Tipo_Fornec, Fornecedor) → Clientes_Principal(Tipo, Codigo)`.
- Colunas: `Data_Entrada`, `Data_Emissao`, `Total_Parcelas`, `Vr_Total_Parcelas`, `Baixado`
  (`'S'`/`'N'`), `Cod_Parcelas`, `Portador`, `Referente`, `Emp_Origem`, `Bloqueado`,
  `DataLancamento`, e tributos/despesas: `IR`, `Porc_/Valor_ISS`, `Porc_/Valor_ICMS`,
  `Desp_Cartoraria`, `Desp_Acessorias`, `Valor_Contabil`, `BC_/Porc_/Valor_PIS/COFINS/CSLL`,
  `Valor_INSS`, `Taxa_Adm`, `Valor_Descontos`, `Valor_Outras_Despesas`, `Id_Contrato`, `Servico`,
  `Moeda`, `DataCambio`, `idDocumento`.

### `NFE_Parcelas` — parcelas — 8 736 registros

- **PK:** `(Empresa, Documento, Serie, Tipo_Fornec, Fornecedor, Parcela)`.
- FKs: `(Empresa, Documento, Serie, Tipo_Fornec, Fornecedor) → NF_Entradas`; fornecedor →
  `Clientes_Principal(Tipo, Codigo)`.
- Colunas: `Vencimento`, `Vecto_Extenso`, `Valor`, `Sit_Papeleta`/`Emit_Papeleta`, `Tarifas`,
  `Referente`, `CodigoBarra`, `Bloqueado`, `ValorDesconto`/`DataDesconto`, `Operacao`,
  banco/agência/conta + `LinhaDigitavel`, `SISPag` (flag), `DataEntradaParcela`, `Id_SISPag`,
  `idParcela`.
- `NFE_Parcelas_Log` (3 991) — auditoria de alterações.

### `Pag_Baixas` — pagamentos (baixas) — 8 603 registros

- **PK:** `(Empresa, Documento, Serie, Tipo_Fornec, Fornecedor, Parcela, Parcial)`.
- FKs: `(Empresa, Documento, Serie, Tipo_Fornec, Fornecedor, Parcela) → NFE_Parcelas`;
  fornecedor → `Clientes_Principal(Tipo, Codigo)`; `Cod_Historico → Pag_Historicos`.
- Colunas: `Data_Baixa`, `Valor_Pago`, `Desconto_Recebido`, `Juros_Pagos`, `Valor_Liquido`,
  `Cod_Historico`, `Complemento`, dados do cheque (`Nr_Cheque`, banco/agência/conta),
  `Data_Hora_Baixa`, `Usuario_Baixa`, `Bloqueado`, `DataLancamento`, `Id_BcoLanc`,
  `SisPag`/`NroPag_SISPag`, `VariacaoCambialAtiva/Passiva`, `Tarifa`, `idBaixa`.
- **Saldo da parcela** = `NFE_Parcelas.Valor − Σ(Pag_Baixas.Valor_Liquido)` (idêntico ao padrão REC).

### `Pag_ChequesEmi_Duplicata` — cheques emitidos — 8 237 registros

- Identifica o cheque usado na baixa: `Banco`, `Nro_Cheque`, agência/conta + kit
  `(Documento, Serie, Tipo_Fornec, Fornecedor, Parcela, Parcial)`, `Integracao`,
  `Empresa_Cheque`.

### Tabelas de apoio / integração

- `Pag_Historicos` — históricos de pagamento:
  `01` Pagamento Total · `02` Pagamento Parcial · `03` Devolução Total · `04` Devolução Parcial ·
  `05` Estorno de Lançamento · `06` Baixa por Cheque · `07` Baixa por Internet ·
  `08` Baixa parcial internet.
- `Pag_Tipos_Fornecedores` — tipo de fornecedor (preenche `Tipo_Fornec`):
  `'0'` Fornecedores · `'1'` Obrigação Social · `'2'` Obrigação Fiscal · `'3'` Seguros ·
  `'4'` Leasing · `'5'` Empréstimo · `'6'` Financiamentos · `'7'` Títulos · `'8'` Diversos ·
  `'9'` Outros.
- `Pag_Operacoes` (1 registro: `'01'` "TESTE"), `Pag_Ocorrencia` (5) e `Pag_Ocorrencia_Motivo`
  (371) — ocorrências de retorno CNAB por banco.
- `Pag_Transacao` (0), `Pag_Remessa` (0), `Pag_CNAB_Retorno_240` (0) — integração CNAB/SISPAG.
- `Pag_Integracao` (403) / `Pag_Integracao_Doc` (411) — integração contábil/bancária.
- `Pag_Titulo_Lancamentos` (0), `Pag_Pagamento` (0), `Pag_Recibo_Pagto*` (0) — suporte.

`Clientes_Principal.Tipo` atual (distribuição): `'0'` 1 669 (Fornecedores) · `'9'` 6 (Outros) ·
`'2'` 3 (Obrig. Fiscal) · `'1'` 2 (Obrig. Social) · `'A'` 1.

## 3. Dados observados (somente contagens)

- `NF_Entradas`: 8 631 títulos, período `2011-11-19` → `2026-09-17`, soma `Vr_Total_Parcelas` ≈
  **R$ 115,4 mi**; `Baixado`: `'S'` 8 514 · `'N'` 117; `Empresa`: `'13'` 8 236 · `'14'` 395.
- `NFE_Parcelas`: 8 736 parcelas, vencimento `2017-06-20` → `2029-02-05`, soma ≈ **R$ 115,4 mi**.
- `Pag_Baixas`: 8 603 pagamentos, período `2018-06-11` → `2026-09-15`, soma ≈ **R$ 111,1 mi**;
  por histórico: `07` (Baixa por Internet) 7 554 · `01` (Total) 584 · `06` (Cheque) 436 ·
  `02` (Parcial) 28 · `08` 1. Por ano (soma `Valor_Liquido`): 2021 R$ 12,8 mi … 2025 R$ 26,8 mi ·
  2026 (parcial) R$ 19,1 mi.
- Cheques emitidos (`Pag_ChequesEmi_Duplicata`): 8 237.

## 4. Consultas úteis para a API nova (somente leitura)

```sql
-- Títulos a pagar com saldo (espelha a lógica "em aberto")
SELECT n.Codigo_Cliente, c.Razao_Nome_Cliente, p.Documento, p.Serie, p.Parcela,
       p.Vencimento, p.Valor,
       ISNULL((SELECT SUM(b.Valor_Liquido) FROM Pag_Baixas b
               WHERE b.Empresa = p.Empresa AND b.Documento = p.Documento
                 AND b.Serie = p.Serie AND b.Tipo_Fornec = p.Tipo_Fornec
                 AND b.Fornecedor = p.Fornecedor AND b.Parcela = p.Parcela), 0) AS Pago,
       p.Valor - ISNULL((SELECT SUM(b.Valor_Liquido) FROM Pag_Baixas b
               WHERE b.Empresa = p.Empresa AND b.Documento = p.Documento
                 AND b.Serie = p.Serie AND b.Tipo_Fornec = p.Tipo_Fornec
                 AND b.Fornecedor = p.Fornecedor AND b.Parcela = p.Parcela), 0) AS Saldo
FROM NFE_Parcelas p
INNER JOIN Clientes_Principal c
        ON c.Tipo = p.Tipo_Fornec AND c.Codigo = p.Fornecedor
WHERE p.Empresa = '13';
```

## 5. Observações e próximos passos

- `Tipo_Fornec` é o mesmo conceito do `Clientes_Principal.Tipo` (o `Ind_Fornecedores`);
  `Pag_Tipos_Fornecedores` dá a descrição. Cuidado ao cruzar `Cliente` (recebíveis = `Codigo_Cliente`)
  com `Fornecedor` (`(Tipo, Codigo)`) — são colunas diferentes da mesma tabela.
- `Pag_Operacoes` tem só "TESTE" e `Liv_EntFat` está praticamente vazia — confirmar com o negócio
  se há operação/legado ainda em uso antes de expor em endpoints.
- Próximo passo: procedures de geração do CP (`SP_Transfere_CP`, `sp_Gerar_Pagar_SemiPronta`,
  `Gera_Ret_NFEntrada`) e a integração CNAB (`Pag_Transacao`/`Pag_Remessa`/`Pag_RetornoCNAB_TipoCampo`).