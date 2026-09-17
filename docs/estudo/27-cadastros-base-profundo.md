# Estudo 27 — Cadastros base (detalhado): entidades, produtos, empresas, geografia e auxiliares

Aprofundamento **tabela por tabela** dos cadastros fundamentais. Estrutura obtida por
`INFORMATION_SCHEMA`/`sys` (somente leitura). Tipos com `!` = `NOT NULL`.

> Correção estrutural: **todas as 5 003 tabelas estão no schema `dbo`**. O schema `microdata`
> contém **uma única view** (`microdata.Empresas`) usada para *row-level security* (ver §10).
> Não há cópia dupla de dados.

---

## 1. Modelo de entidade unificado (`Clientes_Principal`)

O ERP **não** tem tabelas separadas de cliente e fornecedor: tudo é uma **entidade** em
`Clientes_Principal`, discriminada por `Tipo_Entidade`.

**PK:** `Codigo_Cliente char(18)` (o próprio CGC/CNPJ/CPF; entidades estrangeiras usam
`00.000.000/...`).

### Colunas (104)
Identificação: `Codigo_Cliente`, `Razao_Nome_Cliente char(50)`, `CGC_Cliente char(18)`,
`Tipo_Entidade char(1)`, `Tipo char(1)`, `Codigo char(5)`, `RG_ou_Inscricao_Cliente char(18)`,
`Insc_Estadual varchar(14)`, `Inscricao_Municipal varchar(15)`, `CNPJ_Entrega char(18)`,
`IdEstrangeiro varchar(20)`, `IndicadorIE int`, `Produtor_Rural char(1)`,
`indContribPrevidenciaria char(1)`, `CNOCliente varchar(18)`, `Suframa` (via EFD).
Endereço (3 blocos: normal/cobrança/entrega): `Endereco_Cliente char(50)`, `Bairro_Cliente`,
`Cidade_Cliente char(35)`, `Estado_Cliente char(2)`, `Cep_Cliente char(10)`,
`Complemento_Cliente`, `Numero_Cliente`, `Pais_Cliente int`, e idem `_Cobranca_`/`_Entrega_`.
Contato: `DDD1/Fone1/Ramal1`, `DDD2/Fone2/Ramal2`, `DDD_Fax/Fone_Fax`, `Contato1/2`,
`EMail_Cliente char(255)`, `Site_Internet_Cliente`, `whatsapp varchar(20)`.
Dados: `Estado_Civil_Cliente`, `Sexo_Cliente`, `Fundacao_ou_Nascimento`.
Comercial: `Ramo_Cliente char(40)`, `Regiao_Cliente char(40)`, `Banco_Cliente char(3)`,
`Ag_Cliente`, `Conta_Cliente`, `Operacao_Cliente char(2)`, `Conceito_Cliente char(1)`,
`Limite_Credito_Cliente decimal(16,4)`, `Validade_Limite`, `UsuarioAprovouLimite`,
`DataAprovouLimite`, `Cod_Fiscal_Cliente`, `Valorizacao_Aviso`, `TipoTabelaPreco int`,
`Credito_SIMRec`, `Credito_SIMPag`, `Prazo_Rec_Merc int`.
Bloqueio/SPC: `Cliente_Bloqueado char(1)`, `Inativo char(1)`, `Situacao_SPC_Cliente`,
`Data_Consulta_SPC`, `Informante_SPC_Cliente`, `Necessita_Garantia`, `BloquearConsignacao`,
`LiberarAmostra bit`, `GerarTagEAN`.
Fiscal/regime: `Regime_Tributario int` (FK), `indContribPrevidenciaria`.
Transporte: `Transportadora char(3)`, `Redespacho char(3)`, `Usar_Regiao_Fiscal`.
Cheques: `ChProprio`, `ChTerceiro`, `Boleto`, `CCorrente`.
Integração/auditoria: `Codigo_Aux decimal`, `Data_Cadastro_Cliente`, `Enviado_Arquivo`,
`Email_Fatura`, `Usuario…`, `Ult_Atualizacao datetime`, **`idParticipante int`** (FK
`Fnn_Participante`, §4), `alerta_cd`, `obs_ped_cd`, `serasa_*`, `sint_*`, `novo`,
`ultima_atualizacao_dt`.

### FKs declaradas (14)
`Banco_Cliente→Bancos` · `Cidade/Cidade_Cobranca/Cidade_Entrega→Cidades` ·
`Estado/…→Estados` · `Conceito_Cliente→Rec_Conceitos` · `Operacao_Cliente→Rec_Operacoes` ·
`Ramo_Cliente→Rec_Ramos` · `Regiao_Cliente→Rec_Regioes` · `Regime_Tributario→Regime_Tributario`
· `TipoTabelaPreco→Cfc_TipoTabelaPreco` · `idParticipante→Fnn_Participante`.

### Índices (principais)
`PK_Clientes_Principal(Codigo_Cliente)` · `Ind_Fornecedores` **único**(Tipo,Codigo) ·
`Ind_Razao_Cliente(Razao_Nome_Cliente)` · `Cli_Cid(Codigo_Cliente,Cidade_Cliente)` ·
`IX_CLIENTES_PRINCIPAL(Razao…,Cidade,Estado,Regiao,Cliente_Bloqueado,Codigo)`.

### Distribuições (1 681 entidades)
- `Tipo_Entidade`: **C=1 022** (cliente), **A=341** (ambos), **F=318** (fornecedor).
- `Tipo`: `0`=1 669 · `9`=6 · `2`=3 · `1`=2 · `A`=1 (classificação interna do fornecedor).
- `Inativo`: N=1 357 · S=193 · NULL=131. `Cliente_Bloqueado`: N=1 141 · NULL=540.
- `Regime_Tributario`: NULL=1 654 (não informado) · 3=22 · 1=4 · 2=1.

### Views de entidade
- **`Entidades`** (e o sinônimo `View_Entidades`): `FULL/LEFT UNION` de
  `Clientes_Principal` (C) com uma fonte `F` de fornecedor legada, via `ISNULL(C.x,F.x)`.
- **`Fornecedores`**: `Clientes_Principal P LEFT JOIN Clientes_Informacoes I`
  **`WHERE Tipo_Entidade <> 'C'`**, expõe `Tipo`, `Codigo` (=CGC), nome/endereço/contatos.

### Tabelas satélites (1:1 ou 1:N)
| Tabela | Linhas | PK | Papel |
|--------|-------:|----|-------|
| `Clientes_Informacoes` | 1 649 | `Cliente` | Nome fantasia, 1ª/maior compra, maior atraso, cond. pagto/desconto/comissão, PIS/COFINS NFSE, `Figura_Fiscal`, `ContribuinteICMS`, `Consumidor_Final`, convênio/contrato, `Indice_Tabela` |
| `Clientes_Outros` | 1 602 | `Codigo_Cliente_Outros` | Dados pessoais (pai/mãe, nascimento, referências), `Email_Nfe` |
| `Clientes_Conjuge` | 1 602 | `Codigo_Cliente_Conjuge` | Cônjuge (nome, CPF, trabalho, salário) |
| `Clientes_Contatos` | 1 209 | `Codigo char(6)` | Contatos por departamento (`Departamento→Rec_DepEmpresa`) |
| `Clientes_Situacao` | 733 | (`Codigo_Cliente`,`Item`) | Histórico de consultas SPC/Serasa |
| `Clientes_Vendedores` | 1 647 | (`…`,`Vendedor`) | Vínculo cliente×vendedor + `TipoComissao`/`Data_Vinculacao` |
| `Clientes_Obs_EFD` | 5 044 | `Incremento` | Histórico de endereço/dados do cliente p/ EFD (motivo, data) |
| `Clientes_Observacoes` | 155 | `Codigo_Cliente` | Texto livre + papeleta |
| `Clientes_Prosoft` | 49 | `Cliente` | Complemento contábil (CNAE, RG órgão, Cod_IBGE) |
| `ENDERECO_SPED` | 1 661 | `Cliente` | Endereços fiscal/cobrança/entrega no padrão SPED + lat/long |
| `Rec_ClienteBanco` | 1 834 | (`Codigo_Cliente`,`Banco`) | Bancos do cliente |
| `cliente_email` | 28 | (—) | E-mails adicionais (`cli_cd`,`email_seq`,`email`) |
| `Clientes_DespesasReceitas` | 3 | `IdClienteDespesas` | Rateio por níveis contábeis |

---

## 2. Lookups do cadastro

| Tabela | Linhas | PK | Descrição |
|--------|-------:|----|-----------|
| `Rec_Conceitos` | 5 | `Nota_Conceitos char(1)` | Conceito A–E por faixa de atraso (0–5 / 6–15 / 16–31 / 32–90 / 91–9999) |
| `Rec_Operacoes` | 3 | `Cod_Operacao_Operacoes char(2)` | Operação de crédito (comercial, etc.) |
| `Rec_Ramos` | 2 | `Nome_Atividade_Ramos char(40)` | Ramo de atividade (DIVERSOS, FIAÇÃO) |
| `Rec_Regioes` | 1 | `Nome_Regiao_Regioes char(40)` | Região + prazo de entrega + tabela de frete |
| `Regime_Tributario` | 3 | `ID int` | Regime (1/2/3 — Simples/Presumido/Real) |
| `Cfc_TipoTabelaPreco` | 3 | `Codigo int` | Tipo de tabela de preço do cliente |
| `STATUS_CADASTROCLIENTE` | 40 | `CODIGO varchar(3)` | Status de cadastro (usado por fluxo de aprovação) |
| `Rec_DepEmpresa` | 2 | `Codigo char(2)` | Departamentos (contatos) |

---

## 3. Grupos de cliente

- **`Rec_Grupos_IntCh` (43)** — grupo econômico: `Codigo_Grupo char(3)`, `Descricao_Grupo`,
  `Cliente_Principal char(18)`, `Dicionario`, `LimiteDeCreditoTotalGrupo`, `isControlarGrupo`.
- **`Rec_Grupos_IntCh_Clientes` (108)** — liga clientes ao grupo (crédito consolidado).
- `Rec_MetaVendedor` (27), `Rec_Vendedor_Obs` (9) — metas/observações.

---

## 4. Participante financeiro (`Fnn_Participante`) — modelo novo

A entidade do ERP (`Clientes_Principal.idParticipante`) aponta para um **participante
financeiro** (`Fnn_Participante`, **131 linhas**):

`idParticipante int` · `idContaCorrente` · `idCondicaoPagamento` · `indPessoa char(1)` ·
`indFrete` · flags `isCliente/isFornecedor/isFuncionario/isTransportadora/isEmitente/
isVendedor/isConsumidorFinal/isDonodoCheque` · `isAtivo` · `isBloqueado` · `observacao text` ·
`usuario` · `ultimaAlteracao`.

> É a base do módulo financeiro novo (`Fnn_*`); o cadastro comercial (`Clientes_Principal`)
> é espelhado/pertencente a ele por `idParticipante`.

---

## 5. Produtos

**PK:** (`Empresa char(2)`, `Codigo char(6)`). Total **64** (empresa **01 = 56**, **13 = 8**).

### `Produtos` — colunas (62)
`Descricao char(50)`, `Descr_Reduzida`, `DescricaoFiscal varchar(120)`, `Unidade char(4)`,
`Unidade_Comercial`, `Unidade_Compra`, `Cod_ClassFisc char(15)` (NCM/classificação fiscal),
`Cod_NCM char(8)`, `EX_TIPI`, `CEST`, `Genero`, `FamiliaBTS`, `Composicao_1..4`,
**`Secao/Grupo/Subgrupo char(3)`** (→ `Ret_SubGrupos`), `Linha`, `Sit_Trib char(3)`,
`Tributacao`, `Tipo_Produto char(1)`, `Grupo_Fiscal int` (→ `Fig_GrupoFiscal`),
`Cod_Produtos_Servicos` (→ `Produtos_Servicos`), `Grupo_Contabil`, `Id_GruposArvore`,
`Id_InfoAuxiliar`, `Id_Liv_ProdutosOrigem`, `COD_FAB` (→ `Ret_Fabricantes`),
`CustoBruto/CustoLiquido/PercentualDeducaoCusto`, `Porc_Despesa_Producao/Revenda`,
`Estoque_Minimo/Maximo`, `Lucro`, `Comissao`, `ICMS_Compra`, `ControleLotes`,
`ControleLotes_Saldo`, `Limitar_Saldo_Lote`, `Lote_Minimo_Compra`, `Qtde_Multipla_Compra`,
`MultiploOPPlanoMestre`, medidas físicas (`Diametro/Espessura/Espessura2/Comprimento`),
balança (`Balanca`, `Codigo_Balanca`, `Prazo_Validade`), `inativo`, `Bloquea_fat_ind`.

**FKs:** `Empresa→Empresas` · `Secao/Grupo/Subgrupo→Ret_SubGrupos` · `Grupo_Fiscal→Fig_GrupoFiscal`
· `Cod_Produtos_Servicos→Produtos_Servicos` · `COD_FAB→Ret_Fabricantes` ·
`Id_GruposArvore→Grupos_Arvore` · `Id_InfoAuxiliar→Produto_InfoAuxiliar`.

### Classificação (seção → grupo → subgrupo)
`Ret_Grupos` **(5)**: `PK(Secao,Codigo)` — ex.: 001 GERAL, 002 TECIDOS, 003 FIOS, 004 FIBRAS.
`Ret_SubGrupos` **(5)**: `PK(Secao,Grupo,Codigo)` — ex.: 003/050/051 "16/1" (título de fio).
`Ret_Fabricantes` **(0)**: `COD_FAB char(3)`. `Ret_Depositos` **(0)**.

### Tabelas por tipo de produto
| Tabela | Linhas | PK | Conteúdo |
|--------|-------:|----|----------|
| `Produtos_Tecidos` | 62 | (Empresa,Produto) | **Têxtil**: gramatura, larguras cru/acabado, batidas, título, trama/urdume, torção, `Custo_Cru/Estampado/Outros`, fator de quebra, `Metros_por_Peca`, limites de tolerância, `Unidade_Pacote`, `Tipo_Fardo`, `Produto_Origem`, `Residuo` |
| `Produtos_Fios` | 23 | (Empresa,Produto) | Fiação: `Titulo`, `Torcao`, `Processo`, `TPM`, `Residuo` |
| `Produtos_Servicos` | 239 | `Cod_Produtos_Servicos` | Serviços (código, nível, % tributos federal/estadual/municipal, retenção PIS/COFINS) |
| `Produtos_Tipo_Item` | 12 | `Cod_Produtos_Tipo_Item` | Tipo de item SPED: 00 Revenda, 01 MP, 02 Embalagem, 03 Em processo, 04 Acabado, 05 Subproduto, 06 Intermediário, 07 Uso/consumo, 08 Imobilizado, 09 Serviço, 10 Outros insumos, 99 Outras |
| `Produtos_Fornecedores` | 28 | (Empresa,Cod_Produto,Tipo_Fornecedor,Fornecedor) | Fornecedores do produto (principal, ICMS/IPI, crédito IPI, EAN) |
| `Produtos_Precos` | 2 | (Empresa,Produto,Data) | Preço/custo histórico por data (básico, caixa, unidade, margem, PIS/COFINS) |
| `Produtos_FichaTecFisc` | 5 | (Id_Empresa,Id) | Ficha técnica fiscal (código concatenado) |
| `Produtos_Cod_Concat_EFD` | 364 | (Empresa,Cod_Produto,Codigo_Concatenado) | Cadastro fiscal concatenado (tipo item, descrição, NCM, unidade, tributos, CEST, COTEPE) |
| `Produtos_Grama_Sit` | 22 | (Empresa,Produto,Situacao,Desenho) | Gramatura/largura/tratamento por situação e desenho (têxtil) |
| `Produtos_Tec_CodBarras` | 11 | — | Códigos de barras de tecidos |
| `produto_filtro_estoque_valido` | 90 | — | Filtro de estoque válido |
| `Produto_Observacoes` | 2 | — | Observações do produto |

Vazias (estrutura apenas): `Produtos_Classificacao(s)`, `Produtos_Composicao`,
`Produtos_CurvaABC`, `Produtos_Custos`, `Produtos_MP_NFE`, `Produtos_Similares`, `Produtos_Kit`.

---

## 6. Empresas

**`Empresas` (5)**, PK `Codigo_Empresas char(2)`, colunas (62): razão/nome fantasia, endereço,
CGC, inscrições, `Regime_Trib char(1)`, `Regime_Apuracao int`, `ID_Liv_RegimeTributacao`,
indicadores PIS/COFINS (`IND_NAT_PJ_PISCOFINS`, `IND_ATIV_PISCOFINS`), `Perfil_PAF`,
`cId_CSC`/`Cod_CSC` (NFC-e), `CodigoPais`, `ObrigaEntregaECD`, `GERAR_SPED_CONT_PREVID`,
`Id_Empresa int` (ID interno dos módulos novos), titulares 1/2 (+CPF/fone/email), contador,
`Registro_Microdata`, `Porc_Administrativa`, `EmpGrdePorte`.

Cadastradas: **01** PRO MODA TEXTIL (SP, demo) · **02** MICRODATA DEMONSTRAÇÃO · **03** NOTA DE
DÉBITO · **13** **DGB COMÉRCIO IMPORTAÇÃO E EXPORTAÇÃO** (SC, real) · **14** DEMONSTRAÇÃO.
Ou seja, a operação real é a empresa **13**.

Tabelas de parâmetro por empresa: `configuracao_empresas` (2), `Empresas_Obs_SN` (0),
`Empresas_PISCOFINS` (0), `Empresas_Grupos(_Itens/_SPED)` (0).

---

## 7. Geografia

| Tabela | Linhas | PK | Conteúdo |
|--------|-------:|----|----------|
| `Cidades` | 5 574 | `Cidade_Cidades char(35)` | cidade, `UF_Estado`, `Codigo_Municipio`, `Cod_IBGE`, `Cod_SIAFI`, `Cod_GIA`, `Cod_ZFM`, `Nome_IBGE` |
| `Cidade_CodMunicipio` | 5 560 | (`Estado`,`Cidade char(7)`) | município por código (IBGE) |
| `CIDADE_SPED` | 5 571 | `ID int` | cidade no padrão SPED (`CODMUN`, lat/long) |
| `Estados` | 29 | `UF_Estado char(2)` | UF + `Codigo_DOPUF`, `CodEstado`, flags PAF/EFD (`N1810`,`N1820`) |
| `UF_CodEstado` | 28 | `Codigo char(2)` | UF + nome |
| `Paises` | 244 | `Codigo int` | país + `CodigoIntegracao` (Siscomex) |
| `EFD_PAISES` | 242 | — | país p/ EFD |

---

## 8. Auxiliares comerciais

| Tabela | Linhas | PK | Conteúdo |
|--------|-------:|----|----------|
| `Transportadoras` | 250 | `Codigo char(3)` | nome/fantasia, endereço, CGC, placa/UF, `RNTC`, `tipo` (T/A), `Tipo_Frete`, `Inativo` |
| `Rec_Vendedores` | 77 | `Codigo_Vendedores char(3)` | vendedor: CGC, endereço, comissão/IRRF/INSS, `Ativo`, `Loja`, `Grupo_Venda`, flags de alçada (`MaxDesconto`, `AprovaStatusSuspenso`, `Gerente`, `Diretor`), `idParticipante` |
| `Condicoes_Pagto` | 362 | `Codigo_Pagto char(2)` | descrição, fator, `Inativo`, `idMeioPagamento` |
| `Condicoes_Pagto_Parcelas` | 1 334 | (`Codigo_Pagto_Parcelas`,`Incremental_Pagto_Parc`) | parcela: `Tipo_Pagto_Parcelas`, `Dias_Pagto_Parcelas`, `ID_Meio_Pagamento` |
| `Bancos` | 14 | `Nr_Bco_Bancos char(3)` | banco, `LayoutFactoringCadastro`, `IdBanco` |
| `CNAB_Banco` | 15 · `CH_Bancos` 9 · `fnn_Banco` 14 (e `fnn_BancoInstrucao` 166) | — | layouts/instruções bancárias |

---

## 9. Segurança / multi-empresa

- `SIS_UsuarioEmpresa` (68) + `Usuarios` definem o acesso por empresa.
- `Usuario_EmpresaPadrao` (0), `usuario_empresa` (1), `SIS_EmpresaPadrao_Usuario` (9),
  `grupo_usuario` (3)/`grupo_usuario_menu` (140), `perfil_usuario` (16).
- **`microdata.Empresas`** é uma **view de segurança**:
  `SELECT * FROM dbo.Empresas WHERE EXISTS (… SIS_UsuarioEmpresa × Usuarios WHERE
  UPPER(U.Nome_Usuario)=UPPER(SUSER_NAME())) OR NOT EXISTS (…)`.
  Ou seja, quem consulta com um login tem `Empresas` filtrado pelas empresas do usuário — um
  mecanismo de *row-level security* amarrado ao login do banco. A nova API deve **replicar esse
  filtro** explicitamente (por parâmetro de usuário), não depender do schema `microdata`.

---

## 10. Observações para o porte/uso

1. **Entidade única**: modelar `clientes_principal` como `entities` com flags/tipo
   (`C`/`A`/`F`), mais 1:1 `entity_info`, `entity_other`, `entity_spouse`, 1:N `entity_contact`,
   `entity_seller`, `entity_status`, `entity_bank` e o endereço SPED.
2. **`Codigo_Cliente` = documento** (CNPJ/CPF) — usar como chave natural; chaves numéricas
   internas são `Codigo`/`Tipo` (fornecedor) e `idParticipante` (financeiro).
3. **Produto** é chave (`Empresa`,`Codigo`); o **tipo do produto** está separado em
   `Produtos_Tecidos`/`Fios`/`Servicos`; a **classificação fiscal** vive em
   `Produtos_Cod_Concat_EFD` + `Fig_GrupoFiscal`.
4. **Catálogo pequeno nesta base** (64 produtos) — muito é tratado como "peça" em `Cte_Peca`
   (Estudo 19), com produtos “sombra”/concat para o fiscal.
5. **Lookups mínimos** (ramos, regiões, operações, conceitos ≤ 43 linhas) — replicar como
   tabelas de domínio no destino.
6. O cadastro está fortemente **acoplado ao financeiro novo** via `idParticipante`/`Fnn_*` e ao
   **fiscal** via `Figura_Fiscal`/`Grupo_Fiscal`/`Regime_Tributario`.
