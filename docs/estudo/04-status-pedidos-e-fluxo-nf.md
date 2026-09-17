# Estudo 04 — Status dos pedidos e jornada até a nota fiscal

Levantado em **SELECTs somente leitura** no banco `DBMicrodata_DGB`. Não contém valores reais
de sensíveis, apenas contagens, estruturas e lógica extraída de views/triggers/procedures.

## 1. Decodificação dos status do pedido

Não existe cadastro próprio de status de pedido: a interpretação está espalhada em views e no
trigger que mantém os campos. As "fontes da verdade" encontradas:

- `VW_Car_Pedido` — decode oficial usado pela carteira web.
- `VW_RB_Car_Pedido_Status` — complemento (define os 4 tipos de status dos pedidos).
- `TG_InsUpdDel_Car_Itens_Pedido_Status` — trigger que calcula `Status_Item`/`Status_Ped`.

### `Car_Pedido.Status` — status de aprovação (workflow comercial/financeiro)

Interpretado pela `VW_Car_Pedido` e pela `VW_RB_Car_Pedido_Status`:

| Status | Significado (VW_Car_Pedido) | Significado (VW_RB_Car_Pedido_Status) |
|--------|------------------------------|----------------------------------------|
| `'1'` | Em Análise | Análise Financeira |
| `'2'` | Aprovado | Aprovado |
| `'3'` | Cancelado | Cancelado |
| `'4'` | (else → Programado) | Análise Comercial |
| `NULL`/outro | Programado | — |

- A `VW_RB_Car_Pedido_Status` é explícita: não há cadastro de status, os tipos são fixos
  `1=Análise Financeira, 2=Aprovado, 3=Cancelado, 4=Análise Comercial`.
- A `VW_Car_Pedido` cobre apenas `1/2/3` e usa `Programado` como fallback (por isso o `'4'`
  aparece como "Programado" nela — tratar `'4'` como **Análise Comercial** é o mais coerente).

### `Car_Itens_Pedido.Status_Item` — situação do item (mantida por trigger)

Trigger `TG_InsUpdDel_Car_Itens_Pedido_Status` (dispara em INSERT/UPDATE/DELETE de
`Car_Itens_Pedido`) recalcula:

```sql
status_Item = CASE WHEN (p.qtde_acerto > 0)
                     OR (p.qtde - (faturado + p.qtde_acerto)) <= 0 THEN 'E' ELSE '' END
```

- `''` — item **aberto** (ainda há saldo a atender).
- `'E'` — item **encerrado** (atendido por completo).

O componente `faturado` é: soma de `Car_Itens_Romaneio.Qtde` do item (romaneios `Tipo IN ('V','F')`)
que já estão ligados a uma `Fat_Pedido` **emitida** (`Flag_Emitido` presente), ou cuja
classificação do pedido seja especial `Class_Especial = 'O'` (não há classificação 'O' nos dados
atuais de `Car_Classificacoes`; todas estão como `'N'`). Ou seja: **um item só "fecha" quando o que
foi romaneado vira NF emitida (ou acerto de estoque)**.

### `Car_Pedido.Status_Ped` — encerramento do pedido (mantida pelo mesmo trigger)

```sql
Status_Ped = CASE WHEN EXISTS(item com IsNull(Status_Item,'') = '') THEN '' ELSE 'E' END
```

- `''` — pedido **aberto** (existe ao menos um item com `Status_Item = ''`).
- `'E'` — pedido **encerrado** (todos os itens com `Status_Item = 'E'`).
- É o campo usado para filtrar pedidos "em aberto" nas views (
  `VW_Car_Pedido_Aberto`: `P.Status <> 3 AND IsNull(Status_Ped,'') <> 'E'`).

### `Car_Pedido.Tipo_Pedido` — tipo do pedido (parâmetro da empresa)

Decodificado pela `VW_FAT_TipoPedido`, lendo `Fat_Parametros.Tipo_Pedido_1..5`:

| Código | Descrição atual (Fat_Parametros) |
|--------|----------------------------------|
| `'1'` | Vendas |
| `'2'` | Retorno |
| `'3'` | (não cadastrado) |
| `'4'` | Outros |
| `'5'` | (não cadastrado) |

### Distribuição atual (somente contagens)

`Car_Pedido` (15 799 pedidos, Empresa '13'):

- `Status`: `'2'` Aprovado 12 762 · `'3'` Cancelado 2 969 · `'1'` Em Análise/Análise Financeira 47 · `'4'` Análise Comercial 21.
- `Status_Ped`: `''` 9 170 · `'E'` 6 564 · `NULL` 65.
- `Tipo_Pedido`: `'1'` Vendas 15 784 · `'4'` Outros 13 · `'2'` Retorno 2.

## 2. Jornada do pedido: venda → romaneio → NF (SIMFatura)

```
Car_Pedido (venda)
   │  itens: Car_Itens_Pedido (Qtde, Qtde_Romaneio, Qtde_Acerto)
   ▼
Car_Romaneio ──itens──► Car_Itens_Romaneio (rolos/peças reais do estoque)
   │  Tipo 'V'/'F' (hoje só 'V'), Empresa_Pedido/Pedido = pedido de origem
   │  Empresa_NF/Pedido_NF = pedido do SIMFatura
   ▼
Fat_Pedido (NF) ──► Notas_Fiscais_Rec / Notas_Fiscais_Parcelas (financeiro)
```

### `Car_Romaneio` (cabeçalho do romaneio) — 14 596 registros, PK `(Empresa, Romaneio, Tipo)`

Colunas-chave: `Romaneio char(6)`, `Tipo` (`'V'` venda / `'F'` faturamento; nos dados atuais só `'V'`),
`Empresa_Pedido/Pedido` (pedido da carteira de origem), `Cliente`, `Data_Rom`, `Empresa_NF/Pedido_NF`
(pedido gerado no SIMFatura), `Status`, `Bloqueado`, `Status_Geracao`, `Nota_Fiscal`, peso bruto/líquido.
FKs: `Cliente → Clientes_Principal`, `Empresa → Empresas`.

### `Car_Itens_Romaneio` (itens/peças do romaneio) — 274 402 itens, PK `(Empresa, Romaneio, Tipo, Incremento)`

Pontos de ligação:
- `Nro_Peca` (rolo/peça física — conecta ao domínio de estoque do Estudo 02, `Cte_Peca`; hoje
  **270 549 peças distintas** romaneadas), `Id_PCP_Estoque`, `Codigo_Barra`.
- `Empresa_Pedido/Pedido/Nro_Item_Pedido` → devolve o item do `Car_Itens_Pedido`.
- `Produto/Situacao/Cor/Desenho/Categoria/Variante` (FKs formais para as tabelas de descrição) e
  `Qtde/Fardo/Item_Fatura` etc.

### `Fat_Pedido` (pedido/nota no SIMFatura) — 12 653, PK `(Empresa, Pedido)`

A **nota fiscal** faturada: `Nr_Nota`, `Serie`, `Data_Emissao`, `Data_Nota`, `Data_Saida`,
`Vr_Nota`, `Flag_Emitido` (contagem atual: `'1'` 12 633 emitida · `'0'` 19 · `'2'` 1), `dh_Emissao`,
`VersaoXML`/chaves/eventos NFe (tabelas `Fat_Pedido_NFeEv_*`, `Fat_Pedido_Dados_NFE`).

Dimensão do fluxo (contagens):
- **12 472** pedidos da carteira com romaneio (`Car_Romaneio.Empresa_Pedido/Pedido` distintos).
- **11 395** pedidos SIMFatura ligados (`Car_Romaneio.Empresa_NF/Pedido_NF` distintos);
  `Fat_Pedido` com `Nr_Nota` preenchido: **12 634**.

### Views que confirmam o desenho

- `VW_CarPedidosRomaneioNF` — junta romaneio + itens + pedido + NF, trazendo descrições
  (situação/cor/desenho/categoria) e peças, pesos e valores.
- `VW_Pedido_Nota_Emissao_Faturamento` — do item do pedido até `Nr_Nota` (com `didiff = Data_Emissao − Data_Entrega`),
  usando `INNER JOIN` em tudo quando `fp.Nr_Nota <> ''`.

### Fluxo financeiro pós-NF

`Fat_Pedido` alimenta `Notas_Fiscais_Rec` (11 739) e as parcelas em
`Notas_Fiscais_Parcelas` (29 885) — a ponte do faturamento para o contas a receber
(módulo `Notas_Fiscais_*` / `Rec_*`).

## 3. Consultas úteis para a API nova (somente leitura)

```sql
-- Pedidos em aberto para atendimento (mesma regra das views oficiais)
SELECT P.Empresa, P.Pedido, P.Cliente, P.Data_Pedido
FROM Car_Pedido P
WHERE P.Status <> '3' AND IsNull(P.Status_Ped, '') <> 'E';

-- Jornada completa de um pedido até a NF
SELECT cr.Romaneio, cir.Nro_Peca, cir.Produto, cir.Qtde,
       fp.Nr_Nota, fp.Serie, fp.Data_Emissao
FROM Car_Romaneio cr
INNER JOIN Car_Itens_Romaneio cir
        ON cir.Empresa = cr.Empresa AND cir.Romaneio = cr.Romaneio AND cir.Tipo = cr.Tipo
LEFT JOIN Fat_Pedido fp ON fp.Empresa = cr.Empresa_NF AND fp.Pedido = cr.Pedido_NF
WHERE cr.Empresa_Pedido = '13' AND cr.Pedido = '00012345';

-- Pedido com status decodificado (equivale à VW_Car_Pedido)
SELECT Empresa, Pedido, Status AS Status_id,
       CASE Status WHEN '1' THEN 'Em Análise' WHEN '2' THEN 'Aprovado'
                   WHEN '3' THEN 'Cancelado' WHEN '4' THEN 'Análise Comercial'
                   ELSE 'Programado' END AS Status_Desc,
       CASE Status_Ped WHEN 'E' THEN 'Encerrado' ELSE 'Em Aberto' END AS Atendimento
FROM Car_Pedido;
```

## 4. Observações e próximos passos

- `Status_Ped` e `Status_Item` **não são colunas de digitação**: são calculadas pelo trigger
  `TG_InsUpdDel_Car_Itens_Pedido_Status` a partir do romaneio × emissão de NF. Qualquer endpoint
  de "pedidos em aberto" deve respeitar essa lógica.
- Confirmar com o negócio o significado de `Class_Especial = 'O'` (não aparece nos dados atuais)
  para documentar o trigger com precisão total.
- Próximo passo: detalhar as tabelas `Notas_Fiscais_Rec`/`Notas_Fiscais_Parcelas` para fechar o
  domínio de faturamento/contas a receber.