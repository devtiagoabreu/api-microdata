# Estudo 17 — Cadastros comerciais ativos (preço, condições, comissões, bancos)

Levantado com **SELECTs somente leitura** (catálogo + contagens + agregados de flags). Sem dados reais.

## 1. Mapa

| Domínio | Tabelas (linhas) |
|---------|------------------|
| **Tabela de preço** | `CAR_TABELA_PRECO` (9) + `_DIA` (55), `_PRODUTO` (18), `_PRODUTO_VALOR` (104), `_REGIAO` (20), `_VENDEDORES` (8), `car_tabela_preco_figura` (40), `CAR_TABELA_PRECO_CLIENTE` (**0**), `Car_Tabela_Preco_Controle_ID` (1) |
| **Condições de pagamento** | `Condicoes_Pagto` (362), `Condicoes_Pagto_Parcelas` (1334) |
| **Comissões** | `Rec_Comissoes` (462), `Rec_AtrasoComissao` (3), `campanha_comissao*` (1 cada) |
| **Vendedores** | `Rec_Vendedores` (77), `Clientes_Vendedores` (1647), `Notas_Fiscais_Vendedores_Parcelas` (29 886), `Rec_MetaVendedor` (27), `Rec_Grupos_Vendedores` (1) |
| **Transporte/região** | `Transportadoras` (250), `Rec_Regioes` (1), `Fig_RegiaoFiscal` (5), `Fig_RegiaoFiscal_UF` (28), `car_valores_fretes_estados` (**0**) |
| **Meio/forma de pagamento** | `Meio_Pagamento` (23), `Fat_Pedido_FormaPagto` (12 289), `Liv_{Sai,Ent,XML}_FormaPagto` |
| **Bancos / cheques / CNAB** | `Bancos` (14), `CH_Bancos` (9), `CNAB_Banco` (15), `Rec_ClienteBanco` (1834), `Bco_Lancamentos` (10 864), `Cheques_Emitidos` (2 361), `Cheques_Emitidos_DebitoCC` (7 774), `Pag_ChequesEmi_Duplicata` (8 237), `CNAB_Mescla` (933), `CNAB_Retorno` (62) |

## 2. Tabela de preço (motor de preço)

`CAR_TABELA_PRECO` (9): `EMPRESA char(2)`, `COD_TABELA char(5)`, `DESCRICAO`, `DT_VIGENCIA`, `ATIVO`
(**7 ativas / 2 inativas**), `CLASSIFICACAO`, `VALIDAR_NUM_DIA`, `codigo_comissao_faixa_desconto`,
`codigo_colecao`, **`tx_juros_diaria`**, `dias_carencia`. `Car_Tabela_Preco_Controle_ID` (1) controla o
próximo id.

Estrutura de valores (o preço é **por dia**):

- `CAR_TABELA_PRECO_PRODUTO` (18): chave produto/variante —
  `SITUACAO, COR, DESENHO, ID_CAR_GRUPOCATEGORIAS, VARIANTE, ID_CLASSCOR, PRODUTO, EMP_PROD`.
- `CAR_TABELA_PRECO_PRODUTO_VALOR` (104): `ID_CAR_TABELA_PRECO_PRODUTO` + `ID_CAR_TABELA_PRECO_DIA` + **`VALOR`**.
- `CAR_TABELA_PRECO_DIA` (55): `NUM_DIA` + **`PORCENTAGEM`** (juros/desconto por dia de prazo).
- `CAR_TABELA_PRECO_REGIAO` (20), `CAR_TABELA_PRECO_VENDEDORES` (8), `car_tabela_preco_figura` (40).
- `CAR_TABELA_PRECO_CLIENTE` (**0**) → vinculação tabela↔cliente **não é usada** (resolução cai em
  regras por produto/região/vendedor/figura).

### Cadeia de resolução (funções do Estudo 15)

`fnc_pesquisa_tab_preco` → delega a `fnc_pesquisa_tab_preco_mod1` / `_mod2`; `fnc_retorno_tab_preco`
(multi-statement TVF) devolve o preço detalhado. Tabelas referenciadas:

`CAR_TABELA_PRECO(_CLIENTE|_DIA|_PRODUTO|_PRODUTO_VALOR|_REGIAO|_VENDEDORES)`,
`car_tabela_preco_figura`, `Car_Cores`, `Car_Categorias`, `Car_AgrupCat`, `Car_Parametros`,
`Tnt_ClassCor`, `Clientes_Principal`, `Clientes_Informacoes`, `Condicoes_Pagto(_Parcelas)`,
`Fig_RegiaoFiscal_UF`, `fnc_calcula_juros_tab_preco`, `car_aprovadores_comerciais`,
`Car_Aprovadores_Comerciais_Tab_Preco`, `Car_Classificacoes`, `car_comissao_faixa_desconto_itens`,
`Car_ConceitoComercial`, `car_diretores_comerciais`, `car_valores_fretes_estados`,
`Rec_Grupos_Vendedores`, `Rec_Regioes`, `Rec_Vendedores`, `Ret_Unidades`, `VW_SIS_PARAMETROS`, `Empresas`.

> Várias dessas são **vazias** (aprovação/desconto/frete): `CAR_TABELA_PRECO_CLIENTE`,
> `Car_ConceitoComercial`, `car_comissao_faixa_desconto_itens`, `Car_Aprovadores_Comerciais_Tab_Preco`,
> `car_aprovadores_comerciais`, `car_diretores_comerciais`, `car_valores_fretes_estados` = 0.
> Ou seja: o preço efetivo sai de `CAR_TABELA_PRECO_PRODUTO_VALOR`/`_DIA`, com juros por condição de
> pagamento — os fluxos de aprovação/desconto/conceito não estão configurados.
> `Car_Classificacoes` = 9; `Car_ConceitoComercial` = 0.

## 3. Condições de pagamento

- **`Condicoes_Pagto`** (362; **264 ativas / 98 inativas**): `Codigo_Pagto char(2)`,
  `Descricao_Pagto`, `Recalc_Parc_NF`, `Fator`, `Cond_Pagto_Extenso`, `Flag_PAF`, `Inativo`,
  `ID_Condicoes_Pagto_Grupo`, `idMeioPagamento` (todos NULL → não associado a `Meio_Pagamento`).
- **`Condicoes_Pagto_Parcelas`** (1334): `Codigo_Pagto_Parcelas` + `Incremental_Pagto_Parc`,
  `Tipo_Pagto_Parcelas`, **`Dias_Pagto_Parcelas`** (usado no cálculo de juros/prazo médio),
  `ID_Meio_Pagamento` (NULL).
- `fnc_calcula_juros_tab_preco` usa `condicoes_pagto(_parcelas)` + `car_tabela_preco.tx_juros_diaria` +
  parâmetro `Juros_SimpComp_TabPreco` para calcular juros de tabela de preço.

> `Meio_Pagamento` (23) existe e tem `Codigo`/`Descricao`/contas contábeis, mas as condições de
> pagamento não o referenciam (campo vazio) — a ligação condição↔meio não é usada.

## 4. Comissões e vendedores

- **`Rec_Comissoes`** (462; praticamente todas ativas): `Vendedor_Comissoes char(3)`,
  `Tipo_Comissoes`, `E_ou_S_Comissoes`, **`Porcentagem_Comissoes`**, `Dias_Atraso`,
  **`Porcentagem_Comissoes_S`**, `idParticipanteComissao`, `Inativo`.
- `car_comissao_faixa_desconto_itens` (**0**) e `Campanha_Comissao*` (**1** cada) → faixas de desconto/
  campanhas não usadas.
- **`Rec_Vendedores`** (77; 49 ativos): 61 colunas (dados cadastrais + fiscais — `Comissionado`,
  `Aliq_IR`, `Porc_INSS`, `Margem_Comissao`, `Ativo`, `Login`…).
- `Clientes_Vendedores` (1647): vínculo `Codigo_Cliente_Vendedores` ↔ `Vendedor` + `TipoComissao`.
- `Rec_MetaVendedor` (27): metas por empresa/vendedor (`Valor`, `Metros`, `Peso`).
- `Notas_Fiscais_Vendedores_Parcelas` (29 886): comissão **por parcela de NF** (base do contas a receber
  por vendedor).
- `Rec_Grupos_Vendedores` (1), `fnn_ParticipanteComissao`/`fnn_ParticipanteVendedor` (462/77 — integração FNN).

## 5. Transporte e regiões

- **`Transportadoras`** (250): cadastro completo + `Tipo_Frete`, `RNTC`; coluna `Inativo` veio **toda
  NULL** (não marcada) → tratar 250 como disponíveis.
- `Rec_Regioes` (**1**) — regiões comerciais quase não usadas; `Fig_RegiaoFiscal` (5) /
  `Fig_RegiaoFiscal_UF` (28) mapeiam região fiscal↔UF (usado na tabela de preço por região).
- `car_valores_fretes_estados` (**0**) → tabela de frete por estado não configurada.

## 6. Bancos, cheques e CNAB

- **`Bancos`** (14) e **`CH_Bancos`** (9): cadastro (`Nr_Bco`, `Nome`, `idBanco`).
- **`CNAB_Banco`** (15): parâmetros de geração de remessa/retorno — `Empresa`, `Banco`, `Agencia`,
  `Carteira`, `Variacao`, `Usar_240`, `Layout`, `Ultima_Remessa`, diretórios de arquivo/retorno, etc.
  (só 1 registro em `Pag_CNAB_Banco`).
- **`Rec_ClienteBanco`** (1834): banco preferencial do cliente (cobrança).
- Movimento: `Bco_Lancamentos` (10 864), `Cheques_Emitidos` (2 361), `Cheques_Emitidos_DebitoCC`
  (7 774), `Pag_ChequesEmi_Duplicata` (8 237), `CNAB_Mescla` (933), `CNAB_Retorno` (62),
  `CNAB_RETORNO_LOG` (68).
- **`Meio_Pagamento`** (23) + **`Fat_Pedido_FormaPagto`** (12 289) / `Liv_*_FormaPagto` — forma de
  pagamento efetiva por pedido/nota.

## 7. Impacto na API (read-only)

1. **Novos cadastros a expor:** tabelas de preço (`CAR_TABELA_PRECO` + valores por dia),
   condições de pagamento, vendedores, transportadoras, bancos/meios de pagamento.
2. **Preço:** reimplementar `fnc_pesquisa_tab_preco*`/`fnc_retorno_tab_preco` exige a cadeia completa;
   como vários auxiliares estão vazios, o cálculo é basicamente
   `PRODUTO_VALOR` (por `_DIA`) + `tx_juros_diaria` × `Condicoes_Pagto_Parcelas.Dias_Pagto_Parcelas`.
3. **Comissão:** base em `Rec_Comissoes` (por vendedor/tipo/E-S) + `Clientes_Vendedores` +
   `Notas_Fiscais_Vendedores_Parcelas`.
4. **Cobrança/banco:** `Rec_ClienteBanco` + `CNAB_Banco` para geração/leitura de cobrança; movimento em
   `Bco_Lancamentos`/`Cheques_*`/`CNAB_*`.
5. **Atenção:** campos "não usados" (`idMeioPagamento`, `CAR_TABELA_PRECO_CLIENTE`, fretes por estado,
   aprovações/faixas) — a API não deve esperar dados neles.

## 8. Contagens de apoio

- Tabelas de preço: 9 tabelas-base + 9 ativas/2 inativas; 55 dias, 18 produtos, 104 valores, 20 regiões,
  8 vendedores, 40 figuras.
- `Condicoes_Pagto` 362 (264 ativas/98 inativas) · `Condicoes_Pagto_Parcelas` 1334.
- `Rec_Comissoes` 462 · `Rec_Vendedores` 77 (49 ativos) · `Clientes_Vendedores` 1647 ·
  `Notas_Fiscais_Vendedores_Parcelas` 29 886 · `Rec_MetaVendedor` 27.
- `Transportadoras` 250 · `Rec_Regioes` 1 · `Fig_RegiaoFiscal` 5 / `_UF` 28.
- `Bancos` 14 · `CH_Bancos` 9 · `CNAB_Banco` 15 · `Rec_ClienteBanco` 1834 · `Meio_Pagamento` 23.
- Vazias: `CAR_TABELA_PRECO_CLIENTE`, `Car_ConceitoComercial`, `car_comissao_faixa_desconto_itens`,
  `Car_Aprovadores_Comerciais_Tab_Preco`, `car_aprovadores_comerciais`, `car_diretores_comerciais`,
  `car_valores_fretes_estados`.
