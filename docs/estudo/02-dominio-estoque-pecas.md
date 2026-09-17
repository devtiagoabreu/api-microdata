# Estudo 02 — Domínio de estoque de peças/rolos de tecido

> Recorte do banco que a API legada usa para sugestão de rolos de tecido para atender pedidos.
> Levantamento feito **somente com leitura** em 17/09/2026.

## Conjunto de objetos

| Objeto | Tipo | Papel |
|---|---|---|
| `Cte_Peca` | tabela | Estoque físico de peças/rolos de tecido |
| `CTE_Baixa` | tabela | Registro de baixa (saída) de peças/rolos |
| `Produtos_Tecidos` | tabela | Cadastro de produtos tecidos (ficha técnica/grade) |
| `Vw_Car_Itens_Pedido` | view | Itens de pedidos de venda com saldo a faturar |
| `uspEnderecamentoParaAtenderPedidoGeral` | procedure | Sugere rolos em estoque para atender um pedido |

## `Cte_Peca` — estoque de peças/rolos

A tabela guarda cada **peça (rolo) de tecido** em estoque: localização de endereçamento
(`Gaveta`, `SubLote`), características (`Produto`, `Cor`, `Desenho`, `Variante`), medidas
(`Metros`, `Peso`, `Largura`) e origem (`Nro_Rolo_Origem`).

- Chave de negócio (join com `CTE_Baixa` e consultas): `Empresa` + `Situacao` + `Nro_Rolo` + `Nro_Peca`.
- Possui **104 colunas**. Abaixo, as mais relevantes para a API (usadas no legado e na procedure):

| Coluna | Tipo | Observação |
|---|---|---|
| `Empresa` | char(2) | Empresa (não nulo) |
| `Situacao` | char(3) | Situação/estado do estoque (não nulo) |
| `Nro_Rolo` | char(10) | Número do rolo (não nulo) |
| `Nro_Peca` | char(3) | Número da peça dentro do rolo (não nulo) |
| `Metros` | decimal(16,4) | Metragem (não nulo) |
| `Peso` | decimal(16,4) | Peso (não nulo) |
| `EmpProd` | char(2) | Empresa do produto (usado no join com `Produtos_Tecidos`) |
| `Produto` | char(6) | Código do produto (não nulo) |
| `Categoria` | char(2) | Categoria (não nulo) |
| `Largura` | char(8) | Largura |
| `Data_Entrada` | smalldatetime | Data de entrada (não nulo) |
| `Nro_Rolo_Origem` / `Nro_Peca_Origem` | char(10)/char(3) | Preenchidos quando o rolo/peça é derivado de outro (recorte/transformação); `NULL` = item original |
| `Tear` | char(6) | Tear (usado como `Rolo_Packlist` no legado) |
| `Cor` | char(5) | Cor (não nulo) |
| `Desenho` | char(5) | Desenho (não nulo) |
| `Categoria_Tinto` | char(2) | Categoria de tinto |
| `SubLote` | char(20) | SubLote/localização — **dimensão de endereçamento** |
| `Gaveta` | char(10) | Gaveta/localização física — **dimensão de endereçamento** |
| `Num_Etq_Aux` | varchar(25) | Etiqueta auxiliar |
| `Variante` | char(5) | Variante do desenho |
| `Bloqueado` | char(1) | `N` default; indica peça bloqueada |
| `Lote_Interno` | char(10) | Lote interno (exposto no legado) |
| `Aviso` | char(6) | Nº do aviso (ordem de tingimento) |
| `Data_Hora` | datetime | Timestamp |

### Regra de estoque disponível

Um rolo/peça é considerado **em estoque disponível** quando:

```sql
Cte_Peca.Nro_Rolo_Origem IS NULL            -- não é derivado
AND CTE_Baixa.Empresa IS NULL                -- não tem baixa (LEFT JOIN de CTE_Baixa)
```

Essa regra aparece no endpoint `GET /dados` e na `uspEnderecamentoParaAtenderPedidoGeral`.

## `CTE_Baixa` — baixas de peças/rolos

| Coluna | Tipo | Observação |
|---|---|---|
| `Empresa` | char(2) | Chave (não nulo) |
| `Situacao` | char(3) | Chave (não nulo) |
| `Nro_Rolo` | char(10) | Chave (não nulo) |
| `Nro_Peca` | char(3) | Chave (não nulo) |
| `Data_Saida` | smalldatetime | Data da baixa (não nulo) |
| `Romaneio` | char(6) | Romaneio de saída |
| `Tipo` | char(1) | Tipo de baixa |
| `Corte_Altera` | char(1) | Indica corte/alteração |
| `Observacao` | char(50) | Observação |
| `Bloqueado` | char(1) | `N` default |
| `Nr_Lancamento_CFC` | char(10) | Lançamento de confecção |

Uso: em consulta de disponibilidade, `LEFT JOIN CTE_Baixa` e filtro `CB.Empresa IS NULL`
identifica peças **sem baixa** (ainda em estoque).

## `Produtos_Tecidos` — cadastro de tecidos

| Coluna | Tipo | Observação |
|---|---|---|
| `Empresa` | char(2) | Chave (não nulo) |
| `Produto` | char(6) | Chave (não nulo) |
| `Linha` | char(3) | Linha do produto (usada no legado — endpoint `GET /dados`) |
| `Descricao_Reduzida` | char(30) | Descrição |
| `Gramatura`, `Largura_Cru`, `Largura_Acabado`, `Peso`, `Titulo` | decimal | Características técnicas |
| `CF_Cru`, `CF_Estampada`, `CF_Outros` | char(15) | CFOPs |
| `Custo_Cru`, `Custo_Estampado`, `Custo_Outros`, `Custo_Remessa` | decimal(19,10) | Custos |
| `Situacao` | char(3) | Situação do produto |
| `Inativo` | char(1) | Flag de inativação |

Join de negócio: `Produtos_Tecidos.Empresa = Cte_Peca.EmpProd AND Produtos_Tecidos.Produto = Cte_Peca.Produto`.

## `Vw_Car_Itens_Pedido` — itens de pedido com saldo

View que expõe itens de pedidos (`Car_Itens_Pedido`) com descrições dos domínios e o saldo
a faturar. Colunas principais:

| Coluna | Tipo | Observação |
|---|---|---|
| `Empresa` | char(2) | não nulo |
| `Pedido` | char(8) | não nulo |
| `Item` | int | não nulo |
| `Produto` | char(6) | não nulo |
| `Situacao`, `Cor`, `Desenho`, `Variante`, `Categoria`, `largura` | char | códigos |
| `Qtde`, `Vr_unitario`, `Vr_Total`, `Qtde_Romaneio`, `Qtde_Acerto`, `Qtde_Saldo` | decimal | quantidades |
| `*_Descricao` | char | descrições (Produto, Situação, Cor, Desenho, Categoria, Variante) |

**Definição (como está no banco):**

```sql
CREATE VIEW dbo.Vw_Car_Itens_Pedido AS
SELECT CI.Empresa, CI.Pedido, CI.Item, CI.Produto, CI.Situacao, CI.Cor, CI.Desenho,
       CI.Variante, CI.Categoria, CI.largura, CI.Qtde, CI.Vr_unitario, CI.Vr_Total,
       CI.Qtde_Romaneio, CI.Qtde_Acerto,
       (CI.Qtde - CI.Qtde_Romaneio - CI.Qtde_Acerto) AS Qtde_Saldo,
       P.Descricao AS Produto_Descricao, S.Descricao AS Situacao_Descricao,
       C.Descricao AS Cor_Descricao, D.Descricao AS Desenho_Descricao,
       CT.Descricao AS Categoria_Descricao, V.Descricao AS Variante_Descricao
FROM Car_Itens_Pedido CI
INNER JOIN Liv_Diario LV ON (LV.Empresa = CI.Empresa)
LEFT JOIN Produtos        P  ON (P.Empresa = LV.Empresa_Produtos AND P.Codigo = CI.Produto)
LEFT JOIN Car_Situacoes   S  ON (S.Codigo = CI.Situacao)
LEFT JOIN Car_Cores       C  ON (C.Codigo = CI.Cor)
LEFT JOIN Car_Desenhos    D  ON (D.Codigo = CI.Desenho)
LEFT JOIN Car_Categorias  CT ON (CT.Codigo = CI.Categoria)
LEFT JOIN Car_Variante    V  ON (V.Codigo = CI.Variante)
```

> Observação: o saldo é derivado — `Qtde_Saldo = Qtde - Qtde_Romaneio - Qtde_Acerto`.

## `uspEnderecamentoParaAtenderPedidoGeral`

Procedure de **sugestão de endereçamento**: dado um pedido, percorre os itens com saldo e
sugere rolos/peças em estoque (endereçados por `Gaveta`) suficientes para atender o saldo.

- Parâmetro: `@Pedido char(8)`.
- Fontes: `Vw_Car_Itens_Pedido` (itens/saldo) e `Cte_Peca`/`CTE_Baixa` (disponibilidade).
- Lógica: rolos disponíveis ordenados por `Gaveta, Tear DESC, Nro_Rolo DESC`; soma acumulada
  de metros (`SUM(Metros) OVER (ORDER BY RowNum)`); pega o conjunto cuja soma acumulada
  `<= @Saldo` (tolerância de 0,01). Para cada item, agrupa `Sublote` (mínimo), agrega
  `Gavetas` e `Rolos` concatenados (com zero-pad pela esquerda) e totaliza `Qtde_Pecas`/`Total_Metros`.

**Colunas de resultado:** `Produto`, `Cor`, `Qtde_Item`, `Qtde_Saldo`, `Sublote`, `Gavetas`,
`Rolos`, `Qtde_Pecas`, `Total_Metros`.

O texto completo da procedure está preservado no legado em
[`docs/legado/oraculum/src/database/uspEnderecamentoParaAtenderPedidoGera.sql`](../legado/oraculum/src/database/uspEnderecamentoParaAtenderPedidoGera.sql)
(confere com a definição atual no banco).

### Consumo pela API legada

| Endpoint | Chamada |
|---|---|
| `GET /sugestao-rolos/{pedido}` | `EXEC uspEnderecamentoParaAtenderPedidoGeral @pedido` → JSON |
| `GET /pdf/sugestao-rolos/{pedido}` | mesmo `EXEC`, gera PDF de cartões de separação |

> A procedure usa `CURSOR` + `FOR XML PATH` para concatenação. Para a nova API, é candidata a
> reescrita em **set-based** ou consulta direta, reduzindo latência e custo no banco de produção.

## Roteiro da API nova (a partir deste domínio)

1. Expor disponibilidade de rolos com os mesmos critérios de `Cte_Peca`/`CTE_Baixa`.
2. Expor itens de pedido com saldo via `Vw_Car_Itens_Pedido`.
3. Endpoint de sugestão de endereçamento (equivalente à procedure) em SQL puro.
4. Endpoint com catálogo/descrições (`Produtos_Tecidos`, `Car_Cores`, `Car_Desenhos` etc.).