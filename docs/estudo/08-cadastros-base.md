# Estudo 08 — Cadastros base (clientes, fornecedores, vendedores, produtos, empresas)

Levantado em **SELECTs somente leitura**. Contém estrutura, relações e **contagens** — sem
valores reais sensíveis (apenas códigos de exemplo citados genericamente).

## 1. Visão geral

Os domínios financeiros/fiscais (estudos 03–07) gravitam em torno de poucos cadastros base:

- **`Clientes_Principal`** — abriga **cliente e fornecedor na mesma tabela** (PK `Codigo_Cliente`;
  fornecedor endereçado pelo índice único `Ind_Fornecedores` em `(Tipo, Codigo)`).
- **`Produtos`** / **`Produtos_Tecidos`** — catálogo genérico e ficha técnica do tecido.
- **`Rec_Vendedores`** — vendedores/representantes.
- **`Empresas`** — as 5 entidades legais; a operação real usa `'13'` (e `'14'`).

## 2. Modelo de dados

### `Clientes_Principal` (1 681 registros · 106 colunas)

- **PK:** `Codigo_Cliente char(18)` — normalmente o CNPJ/CPF formatado.
- **Índice único `Ind_Fornecedores`:** `(Tipo char(1), Codigo char(5))`. Linhas de **fornecedor**
  têm `Tipo` (decodificado por `Pag_Tipos_Fornecedores` — Estudo 06) e `Codigo alfanumérico de 5`
  (ex.: `"00112"`, `"HAIHO"`, `"T0219"`), mantendo o CNPJ em `Codigo_Cliente` e nome/endereço
  iguais aos de cliente. **Não existe tabela separada de fornecedores.**
  - Distribuição atual de `Tipo`: `'0'` Fornecedores (1 669; `Inativo`: 1 345 `'N'` · 193 `'S'` ·
    131 vazio) · `'1'` Obrigação Social 2 · `'2'` Obrigação Fiscal 3 · `'9'` Outros 6 · `'A'` 1.
  - Há fornecedores internacionais (ex.: China) com códigos não-CNPJ.
- Grupos de colunas:
  - **Endereços** — 3 blocos completos: cadastro, cobrança e entrega (`Endereco/Bairro/Cidade/
    Estado/Cep/Complemento/Numero/Pais`), além de `CNPJ_Entrega`.
  - **Contato** — `DDD/Fone/Ramal` x2 + fax + `whatsapp`, `EMail_Cliente`, `Site`, `Contato1/2`,
    `Sexo`, `Estado_Civil`, nascimento/fundação, `Conceito_Cliente`.
  - **Fiscal** — `CGC_Cliente`, `RG_ou_Inscricao`, `Insc_Estadual`, `Inscricao_Municipal`,
    `Regime_Tributario`, `IndicadorIE`, `Produtor_Rural`, `IdEstrangeiro`, `CNOCliente`,
    `indContribPrevidenciaria`, `Tipo_Entidade`, `Pais_Cliente` (int).
  - **Crédito/bloqueio** — `Limite_Credito_Cliente`, `Validade_Limite`, `Credito_SIMRec`,
    `Credito_SIMPag`, `UsuarioAprovouLimite`/`DataAprovouLimite`, `Cliente_Bloqueado`,
    `Situacao_SPC_Cliente`/`Data_Consulta_SPC`.
  - **Bancário** — `Banco_Cliente`, `Operacao_Cliente`, `Ag_Cliente`/`DAg_Cliente`,
    `Conta_Cliente`/`DConta_Cliente`; o cadastro contábil chegueiro
    (`ChProprio/ChTerceiro/Boleto/CCorrente`, em águas REC) e `Rec_ClienteBanco` (1 834 linhas
    `Codigo_Cliente'+Banco`) mapeiam bancos emissor boleto.
  - **Comercial** — `Regiao_Cliente`, `Ramo_Cliente`, `Transportadora`, `Redespacho`,
    `Cod_Fiscal_Cliente`, `Usar_Regiao_Fiscal`, `Necessita_Garantia`, `Inativo`, `novo`,
    `ultima_atualizacao_dt`.
- Funções de apoio: `Clientes_Situacao` (733 — consultas SPC por item/data), `Log_Clientes_SPED`
  (947) / `Log_Alteracao_Clientes_SPED` (2 867) — trilha de auditoria.

### Satélites do cliente (dados existentes)

| Tabela | Qtde | Conteúdo principal |
|--------|-----:|--------------------|
| `Clientes_Informacoes` | 1 649 | 72 cols: 1ª compra, maior faturamento, maior atraso (`Maior_Atraso_Duplic/Parc/Vcto`), `Cond_Pagto`, `Desconto`, `Comissao`, `Nome_Fantasia`, `Consumidor_Final`, `ContribuinteICMS`, distribuição `Distrib_MetrosIn/Fn`, leitura de senha p/ portal |
| `Clientes_Vendedores` | 1 647 | Vínculo cliente × vendedor: `Vendedor`, `TipoComissao`, `Data_Vinculacao` (um cliente pode ter linha por empresa/comissão) |
| `Clientes_Conjuge` / `Clientes_Outros` | 1 602 | fiança/obrigações (cadastro físico) |
| `Clientes_Contatos` | 1 209 | Pessoa de contato por cliente, difere dos contatos fixos da Principal; flags e-mail cobrança automática |
| `Rec_ClienteBanco` | 1 834 | `(Codigo_Cliente, Banco)` — bancos habilitados para boleto |
| `Rec_Grupos_IntCh_Clientes` | 108 | grupos de clientes p/ integração cheques |
| `Clientes_Prosoft` | 49 | integração Prosoft |
| `Clientes_DespesasReceitas` | 3 | contas de despesa/receita padrão do cliente |
| `Clientes_Obs_EFD` | 5 044 | observações de validação EFD |

### `Produtos` (64 · 73 colunas) — catálogo fiscal/genérico

- **PK:** `(Empresa, Codigo char(6))`. Sem FK das tabelas de venda: `Car_Itens_Pedido.Codigo_Produto`
  é **referência solta** (não há FK formal `Car_Itens_Pedido → Produtos`).
- Colunas: `Descricao`, `Descr_Reduzida`, `DescricaoFiscal` (120), `Unidade`/`Unidade_Comercial`/
  `Unidade_Compra`, `Cod_NCM`, `CEST`, `EX_TIPI`, `Genero`, `Sit_Trib`, `Secao/Grupo/Subgrupo/
  Linha`, `Grupo_Fiscal`, `Grupo_Contabil`, `Comissao`, `ICMS_Compra`, `Codigo_Aux`, `inativo`,
  `ControleLotes`, composições 1–4, `Cod_ClassFisc`.

### `Produtos_Tecidos` (62 · 94 colunas) — ficha técnica do tecido

- **PK:** `(Empresa, Produto)`; é o detalhamento têxtil do produto `Codigo` em `Produtos`.
- Colunas: `Gramatura` (cru/bruto/M2), `Largura_Cru`/`Largura_Acabado`/`Largura_Tubular` (+
  tolerâncias), `CF_Cru`/`CF_Estampada`/`CF_Outros`, `Peso`, `Nr_Batidas` (cru/acabado),
  `Metros_por_Peca`, `Rendimento`, `Fator_Quebra`/`Fator_Divisao`/`Fator_Unidade`, e os custos
  `Custo_Cru`/`Custo_Estampado`/`Custo_Outros`/`Custo_Remessa`, `Comissao_Padrao`, `Premio`,
  `Verba`, `Linha`, `Situacao`/`Situacao_Nascimento`, `Produto_Origem`, `Residuo`,
  `Fiacao`, `Trama_Urdume`, `Torcao`, `Titulo_Efetivo`, `Matricidade`, `Metros_por_Peca`,
  `Modifica_ProgTintur`, `Produto_Servico`, `Partida` etc.

### `Produtos_Servicos` (239) e afins

- Serviços cadastrados + `Produtos_Fornecedores` (28) / `Produtos_Fornecedores_Cod` (36),
  `Produtos_Filtros` (205 — filtros comerciais, com um backup `produtos_filtros_2026_07_01`),
  `Produtos_Fios` (23), `Produtos_FichaTecFisc` (5), `Produtos_Precos` (2).

### `Rec_Vendedores` (77 · 61 colunas) — vendedores/representantes

- **PK:** `Codigo_Vendedores char(3)` (usado como `Vendedor` em `Car_Vend_Pedido`, `Clientes_Vendedores`).
- Colunas: `Nome_Vendedores`, `CGC/Inscricao` (representante PJ), endereço/contato, `LOJA`,
  `Ativo`, `Interno_Externo`, `Grupo_Venda`, `Comissionado`, `Margem_Comissao`, `Acres_Unitario`,
  `Aliq_IR`, `Limite_Isento`, `Porc_INSS`, `IRRF`, `Login`/`Senha`, `Gerente`/`Diretor` e flags
  de aprovação (`AprovaAnaliseProtCredito`, `AprovaStatusSuspenso`).

### `Empresas` (5 · 124 colunas)

- **PK:** `Codigo_Empresas char(2)`. Entidades: `'13'` e `'14'` (as duas operacionais —
  `'13'` concentra ~97% das notas e títulos), `'01'` (matriz têxtil histórica), `'02'`
  (demonstração), `'03'` (nota de débito).
- Colunas: identidade completa (razão, fantasia, endereço, CNAE, CGF/IE/IM, junta),
  contador/CRC, regime tributário/apuração, `Regime_Trib`, parâmetros NFe (`Id_Empresa`,
  `cId_CSC`/`Cod_CSC`, `titular1/2*`), flags SPED/PIS-COFINS/PAF, `idConcil` (conciliação).
- Curiosidade de legado: **cada coluna aparece duplicada** em `Empresas` (bak da tabela foi
  recriada com colunas repetidas) — usar sempre a primeira ocorrência na modelagem.

## 3. Como os módulos usam o cadastro (resumo cross-estudos)

| Módulo | Chave usada | Referência |
|--------|-------------|-----------|
| Pedidos (Car) / NF saída / CR (`Notas_Fiscais_Rec`) | `Clientes_Principal.Codigo_Cliente` | Estudo 03/05 |
| CP (`NF_Entradas`/`NFE_Parcelas`) | `Clientes_Principal.(Tipo, Codigo)` = `(Tipo_Fornec, Fornecedor)` | Estudo 06 |
| Vendedor | `Rec_Vendedores.Codigo_Vendedores` via `Clientes_Vendedores`/`Car_Vend_Pedido` | Estudo 03 |
| Empresa | `Empresas.Codigo_Empresas` (`'13'` em ~97% dos títulos) | Estudos 04–07 |
| Produto | `Car_Itens_Pedido.Codigo_Produto` → `Produtos.(Empresa,Codigo)` (referência solta) + `Produtos_Tecidos` | Estudo 03 |

## 4. Consultas úteis para a API nova (somente leitura)

```sql
-- Cliente por CNPJ, nome ou cidade (padrão de busca do ERP)
SELECT Codigo_Cliente, Razao_Nome_Cliente, Cidade_Cliente, Estado_Cliente,
       CGC_Cliente, Cliente_Bloqueado, Inativo
FROM Clientes_Principal
WHERE CGC_Cliente LIKE '%<digitos>%'
   OR Razao_Nome_Cliente LIKE '%<termo>%'
   OR Cidade_Cliente LIKE '%<cidade>%';

-- Fornecedor específico (padrão CP)
SELECT Codigo_Cliente, Razao_Nome_Cliente, Tipo, Codigo
FROM Clientes_Principal
WHERE Tipo = '0' AND Codigo = '<codigo_5>';
```

> Observação: `Clientes_Principal` **não tem** coluna `Empresa` (é entidade global); o escopo por
> empresa é definido por quem a usa (títulos, produtos, vendedores têm empresa própria).

## 5. Próximos passos sugeridos

- Estudo de **Compras** (`Cmp_Pedido`/`Cmp_PedAtend`) — a raiz dos títulos a pagar (parcialmente
  referenciado no Estudo 07).
- Estudo do **estoque**: `Est_Entradas`/`Est_Saidas`, `Produtos_Estoques`, custo (`Produto_Custo*`,
  `Mov_Con` contábil) e a integração com `Liv_Entradas` (Estudo 07).