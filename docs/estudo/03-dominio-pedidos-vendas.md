# Estudo 03 — Pedidos e itens de venda (`Car_*`)

Levantado em **SELECTs somente leitura** no banco `DBMicrodata_DGB`. Não contém valores reais
de produção, apenas estrutura, relações e contagens.

## Visão geral do domínio

Os pedidos de venda vivem no módulo `Car_` (carteira/vendas) e são divididos em **cabeçalho**
(`Car_Pedido`), **itens** (`Car_Itens_Pedido`) e **vendedores do pedido** (`Car_Vend_Pedido`),
com tabelas pequenas de descrição para produto/situação/cor/desenho/categoria/variante.

Padrão geral do ERP: chaves **empresa + número** (`Empresa char(2)` + `Pedido char(8)`), e os
campos são `char(4)/char(8)` com espaço à direita (sem trim no fonte).

## Modelo de dados

### `Car_Pedido` — cabeçalho do pedido

- **Chave primária:** `(Empresa, Pedido)`.
- **~99 colunas.** Grupos de campos:
  - Identificação: `Empresa`, `Pedido`, `Data_Pedido`, `Data_Entrega`, `Seu_Pedido`, `Contato`, `Pedido_Representante`, `Pedido_Ecommerce`.
  - Cliente/entrega: `Cliente` (FK → `Clientes_Principal.Codigo_Cliente`), `ClienteEntrega`, `Cliente_Triangulo`, `Local_Entrega`, `End1_/End2_Entrega`, `End1_/End2_Cobranca`, `Endereco_Entrega`.
  - Transporte/redespacho: `Cod_Transp`, `Des_Transp`, `Cod_Redesp`, `Des_Redesp`, `Frete_Conta`, `Vr_Frete`, `Redespacho_Conta`.
  - Pagamento/cobrança: `Cond_Pagto`, `Cond_Pagto_Extenso`, 2 blocos de banco/agência/conta/operação (`Banco_1..2`, `Agencia_1..2`, `Conta_1..2`), flags `Cobranca_`, `Cheque_`, `Pagto_`, `VerObs_`. `cond_cd` (smallint) é um id opcional de condição de pagamento.
  - Valores/descontos: `Porc_Desc`, `Porc_Acresc`, `Vr_Frete`.
  - Comissão: `Porcentagem_Comissao`, `Prazo_Medio`.
  - Comercial/gestão: `Classificacao`, `Status`, `Status_Ped`, `Status_Pedido` não existe; `SPro/SSit/SCor/SDes/SCat/SLarg/SVariante` (flags "sugerido"); `Tipo_Pedido`, `Tipo_Pedido_Comercial`, `LinhaProduto`, `Tipo_Comercializacao`, `PercRentabilidadeGeral`, `Bloqueado`, `validado_gestor`, `aprovado`, flags de aprovação comercial (`dt_ultima_aprov_comerc`), `MotivoReprova`/`DescricaoReprova`, `Politica`, `pedido_origem` (`ped_orig_nu`), `Pedido_Urgente`, `Aceita_Pedido_Parcial`, `Entregas_Futuras`, `Modalidade_Ent_Princ/Detal`, `regra_negocio`, `marcacao_cd`, `alerta_cd` (dimensionamentos das aprovações).
  - Auditoria: `Usuario`/`Usuario_Alt` (int), `DataHora_Alteracao`, `Usuario_Criacao`.
- **FKs declaradas:** `Cliente → Clientes_Principal(Codigo_Cliente)`; `Empresa → Empresas(Codigo_Empresas)`; `usu_cd → usuario(usu_cd)`; `tp_orig_ped_cd → tipo_orig_ped(tp_orig_ped_cd)`.

### `Car_Itens_Pedido` — itens do pedido

- **Chave primária:** `(Empresa, Pedido, Item)`; `Item` é inteiro sequencial por pedido.
- **FK:** `(Empresa, Pedido) → Car_Pedido`; também FK para `Car_Cores_Fornec` (cor + tipo/fornecedor do beneficiamento).
- **~84 colunas.** Grupos:
  - Produto/composição: `Produto char(6)` (FK conceitual → `Produtos`), `Situacao char(3)`, `Cor char(5)`, `Desenho char(5)`, `Categoria char(2)`, `Variante char(5)`, `Largura`, `Produto_Cliente`, `Unid`/`Unid_Fat`/`Qtde_Fat`/`Vr_Unitario_Fat`.
  - Quantidades/preços: `Qtde`, `Vr_Unitario`, `Vr_Unitario2`, `Vr_Total`, `Vr_Desconto`, `Porc_Desconto`, `desc_porc`, `acres_porc`, `Vr_Unit_Servico`, `Vr_Unit_Prod_Aplicado`.
  - **Atendimento (chave para sugestão de rolos):** `Qtde_Romaneio` e `Qtde_Acerto` (default `0.00`). Em conjunto com `Qtde`, definem o **saldo pendente**: `Qtde_Saldo = Qtde - Qtde_Romaneio - Qtde_Acerto` (mesma lógica da `Vw_Car_Itens_Pedido`, ver Estudo 02).
  - Comissão: `Comissao`, `ComissaoS`, `perc_comissao`, `comissao_original`, `comissaos_original`, `comissao_manual`, `Tipo` (tipo de comissão), controle de aprovação (`AprovadoComercialRentabilidade`, `MotivoReprovaRentabilidade`).
  - Fiscal/custo: `Indice1..3`, `PercImpostos`, `CustoProduto`, `Peso_Padrao`, `Nro_Unidades`, `PercRentabilidade`, `tabela de preço` (`cod_tab_preco`, `val_tabela_preco`, `dif_val_tabela_preco`, `dif_perc_tabela_preco`, `aprovado_comercial`).
  - Beneficiamento/terceirização: `Tipo_Fornec`, `Fornecedor`, `Produto`, fronteira com `Car_Cores_Fornec`.
  - Data/entrega: `Data_Entrega`, `DtEntrega`, `Data_Previsao_Fabril`, `estoque_*` (referência a um pedido de estoque que atendeu o item), `Liberado`, `Grupo_Item`.

### `Car_Vend_Pedido` — vendedores por pedido

- **Chave primária:** `(Empresa, Pedido, Vendedor)`; FK `(Empresa, Pedido) → Car_Pedido`.
- Colunas: `Vendedor char(3)` (vínculo conceitual → `Rec_Vendedores.Codigo_Vendedores`, **sem FK declarada**), `Tipo_Comissao`, `Porc_Comissao`, `Porc_ComissaoS`.
- Um pedido pode ter **vários vendedores** (comissão rateada), daí ser tabela separada.

### Tabelas de descrição (pequenas)

| Tabela | Chave | Principal uso |
|--------|-------|---------------|
| `Produtos` | `(Empresa, Codigo char(6))` | catálogo de produtos/artigos de venda |
| `Car_Situacoes` | `Codigo char(3)` | situação do item (fiação/engomagem/etc.) |
| `Car_Cores` | `Codigo char(5)` | cores (com RGB p/ visual) |
| `Car_Desenhos` | `Codigo char(5)` | desenhos/estampas |
| `Car_Categorias` | `Codigo char(2)` | categorias de peça (retalho, mts inicial/final) |
| `Car_Variante` | `Codigo char(5)` | variantes do produto |

## Mestres relacionados

### `Clientes_Principal` — cliente (cabeçalho)

- **Chave primária:** `Codigo_Cliente char(18)`; índice único alternativo `(Tipo, Codigo)`.
- **~106 colunas**: razão/nome, bancos (obs.: `Banco_Cliente`, `Operacao_Cliente`, `Conta_Cliente`, `Ag_Cliente`...), endereços (geral/cobrança/entrega), fiscal (`CGC_Cliente`, `Insc_Estadual`, `CNAE`), limites (`Limite_Credito_Cliente`, `Validade_Limite`), status (`Cliente_Bloqueado`, `Situacao_SPC_Cliente`, `Inativo`), tabela de preço (`TipoTabelaPreco`).
- Complementos usando o mesmo código: `Clientes_Informacoes`, `Clientes_Outros`, `Clientes_Conjuge`, `Clientes_Contatos`, `Clientes_Contabil` (~1.650 clientes no total).

### `Rec_Vendedores` — vendedor

- **Chave primária:** `Codigo_Vendedores char(3)` (77 vendedores/dados atuais).
- Colunas relevantes: `Nome_Vendedores`, `CGC_Vendedores`, `Comissionado`, `MaxDesconto`, `Ativo`, `Gerente`, `Diretor`, `Login`, `Grupo_Venda`, `Interno_Externo`, `Loja`.
- `Vendedor_x_Cod` relaciona `Vendedor char(3)` → seção/grupo/subgrupo de produtos (não é FK formal).

## Dados observados (contagens — sem valores sensíveis)

- `Car_Pedido`: **15 799 pedidos**, período 2018-07-30 a 2026-09-17; todos com `Empresa = '13'`.
  - `Tipo_Pedido`: `'1'` 15 784; `'2'` 2; `'4'` 13.
  - `Status_Ped`: `' '` 9 170; `'E'` 6 564; NULL 65.
  - `Status`: `'2'` 12 762; `'3'` 2 969; `'1'` 47; `'4'` 21.
- `Car_Itens_Pedido`: **41 224 itens** (média ≈ 2,6 itens/pedido).
- `Car_Vend_Pedido`: 15 769 linhas vendedor-pedido.

> Os códigos de `Status`/`Status_Ped`/`Tipo_Pedido` **ainda não foram decodificados**: o passo
> seguinte é cruzar com o que o legado/ERP interpreta (ex.: status de aprovação comercial,
> situação de faturamento) antes de expor em endpoints.

## Consultas úteis para a API nova (somente leitura)

```sql
-- Cabeçalho com cliente e vendedores
SELECT p.*, c.Razao_Nome_Cliente
FROM Car_Pedido p
LEFT JOIN Clientes_Principal c ON c.Codigo_Cliente = p.Cliente
WHERE p.Empresa = '13' AND p.Pedido = '00012345';

-- Itens com saldo pendente de atendimento (mesma lógica da Vw_Car_Itens_Pedido)
SELECT *
FROM Vw_Car_Itens_Pedido
WHERE Empresa = '13' AND Pedido = '00012345';

-- Vendedores do pedido
SELECT vp.*, v.Nome_Vendedores
FROM Car_Vend_Pedido vp
LEFT JOIN Rec_Vendedores v ON v.Codigo_Vendedores = vp.Vendedor
WHERE vp.Empresa = '13' AND vp.Pedido = '00012345';
```

## Próximos passos sugeridos

1. Decodificar os domínios `Status_Ped`/`Status`/`Tipo_Pedido` junto ao ERP/legado.
2. Mapear a jornada do pedido até a nota fiscal (`Notas_Fiscais_*`) e o romaneio
   (`Qtde_Romaneio`), fechando o fluxo `pedido → sugestão de rolos → expedição → NF`.
3. Definir a primeira versão de endpoints GET sobre esse domínio.