"""Disponibilidade comercial: o que tem, o que chega e o que ja foi prometido.

O comercial nao pergunta "quanto tem de estoque", e sim "consigo entregar?". Isso e a
diferenca entre as tres fontes que esta rota junta, todas por **produto x cor**:

| Coluna | Fonte | Grao |
|---|---|---|
| `estoque` | `core.estoque_pecas_em_aberto` (warehouse local) | peca em aberto |
| `caminho` | `Cmt_Pedido` / `_Itens` / `_Itens_Entrega` (ERP) | compra com entrega futura |
| `prometido` | `Vw_Saldo_Pedido_Carteira_Qlik` (ERP) | item de pedido em aberto |

E o liquido, que e o que interessa: `livre = estoque - prometido` e
`cobertura = estoque + caminho - prometido`.

**Por que o cruzamento e em Python e nao em SQL**: o estoque vive no Postgres local
(`warehouse`) e as outras duas no ERP (SQL Server). Sao dois motores diferentes; a rota
le as tres e monta a chave `produto|cor` em memoria. O volume e pequeno (99 cores em
estoque, 68 na carteira, 6 compras em transito), entao cabe em uma passada.

**Parametros**: o warehouse usa `text()` do SQLAlchemy e aceita `:nome`; o ERP vai por
`erp.query`, que so aceita sequencia posicional. Por isso os dois SQLs usam estilos
diferentes de marcador — `?` no ERP, `:nome` no warehouse.

**Unidade**: metro nas tres fontes. Confirmado com quem usa: o estoque tem `metros`, a
carteira vende em metro, e `Cmt_Pedido_Itens.metros` esta **zerado** — a quantidade da
compra esta em `Qtde`, que e metro. Por isso o caminho usa `Qtde`, nunca `metros`.

**O que e compra em transito**: `Cmt_Pedido` (modulo de importacao, fornecedor P2B) com
`Data_Entrega` de hoje para frente e pendencia na entrega. `Ret_Aviso_Recebimento` nao
serve: e o recebimento ja efetivado, todas as datas no passado. O container e o proprio
pedido de compra (DI em `Fat_Itens_Pedido_DI`); `QtdeVolumes` esta zerado na base.

Escopo `estoque:leitura` e corte por empresa, igual as demais rotas.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from src.api.auth.escopos import ESCOPO_ESTOQUE, empresa_efetiva, exigir_escopo
from src.api.auth.usuarios import Usuario
from src.db import erp, warehouse

router = APIRouter(tags=["disponibilidade"])

_dependente = Annotated[Usuario | None, Depends(exigir_escopo(ESCOPO_ESTOQUE))]

# Estoque: uma linha por produto x cor. A soma e sobre `core.estoque_pecas_em_aberto`
# (e nao sobre `marts.estoque_saldo`) porque o mart nao tem empresa — e o corte por
# empresa precisa entrar no `where` para bater com o `/dados`.
SQL_ESTOQUE = """
select produto,
       max(prod_desc) as produto_desc,
       cor,
       max(cor_desc) as cor_desc,
       sum(coalesce(metros, 0)) as metros,
       count(*) as pecas,
       count(distinct nro_rolo) as rolos
from core.estoque_pecas_em_aberto
{onde}
group by produto, cor
order by produto, cor
"""

# Compra em transito: entrega futura e pendencia por entidade de entrega. `Qtde` e metro.
SQL_CAMINHO = """
select rtrim(i.Produto) as produto,
       rtrim(i.Cor) as cor,
       sum(isnull(e.Qtde, i.Qtde) - isnull(e.Qtde_Recebida, 0)) as metros,
       min(p.Data_Entrega) as primeira_chegada,
       max(p.Data_Entrega) as ultima_chegada,
       count(distinct p.Pedido) as pedidos
from DBMicrodata_DGB.dbo.Cmt_Pedido_Itens i
join DBMicrodata_DGB.dbo.Cmt_Pedido p
  on p.Empresa = i.Empresa and p.Pedido = i.Pedido
left join DBMicrodata_DGB.dbo.Cmt_Pedido_Itens_Entrega e
  on e.Empresa = i.Empresa and e.Pedido = i.Pedido and e.Item = i.Item
where p.Data_Entrega >= getdate()
  and isnull(e.Qtde, i.Qtde) > isnull(e.Qtde_Recebida, 0)
{onde}
group by rtrim(i.Produto), rtrim(i.Cor)
"""

# Carteira: saldo em aberto (`Qtde_Ped - Qtde_Rom - Qtde_Acerto`) por produto x cor e por
# representante. O nome do vendedor vem de `Rec_Vendedores`; o da cliente, de
# `Clientes_Principal` (a view traz o CNPJ, nao a razao social).
SQL_CARTEIRA = """
select rtrim(q.Produto) as produto,
       rtrim(q.Cor) as cor,
       rtrim(q.Vendedor) as vendedor,
       v.Nome_Vendedores as vendedor_nome,
       count(distinct q.Pedido) as pedidos,
       sum(q.Saldo) as saldo,
       sum(q.Vr_Total) as valor
from DBMicrodata_DGB.dbo.Vw_Saldo_Pedido_Carteira_Qlik q
left join DBMicrodata_DGB.dbo.Rec_Vendedores v
  on v.Codigo_Vendedores = rtrim(q.Vendedor)
where 1 = 1
{onde}
group by rtrim(q.Produto), rtrim(q.Cor), rtrim(q.Vendedor), v.Nome_Vendedores
"""


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


# Os pedidos de venda linha a linha, para o detalhe da cor: a rota principal volta
# agregado por representante; aqui vem o codigo, o cliente e as datas.
#
# `Cliente` da view e o **CNPJ** (mesmo dominio `Cliente` de `Car_Pedido.Cliente`), e o
# nome esta em `Clientes_Principal.Codigo_Cliente` — casar por `Codigo` nao acha nada,
# porque aquele e o codigo curto ('00001').
SQL_PEDIDOS = """
select rtrim(q.Empresa) as empresa,
       rtrim(q.Pedido) as pedido,
       rtrim(q.Cliente) as cliente,
       rtrim(cp.Razao_Nome_Cliente) as cliente_nome,
       rtrim(q.Vendedor) as vendedor,
       rtrim(v.Nome_Vendedores) as vendedor_nome,
       rtrim(q.Produto) as produto,
       rtrim(q.Cor) as cor,
       q.Data_Pedido as data_pedido,
       q.Data_Entrega as data_entrega,
       q.Qtde_Ped as qtde_pedido,
       q.Qtde_Rom as qtde_romaneada,
       q.Saldo as saldo,
       q.Vr_Total as valor,
       rtrim(q.Status_Pedido) as status
from DBMicrodata_DGB.dbo.Vw_Saldo_Pedido_Carteira_Qlik q
left join DBMicrodata_DGB.dbo.Rec_Vendedores v
  on v.Codigo_Vendedores = rtrim(q.Vendedor)
left join DBMicrodata_DGB.dbo.Clientes_Principal cp
  on cp.Codigo_Cliente = q.Cliente
where 1 = 1
{onde}
order by q.Data_Pedido desc, q.Pedido desc
"""


def _numero(valor: Any) -> float:
    return float(valor) if valor is not None else 0.0


def _inteiro(valor: Any) -> int:
    return int(valor) if valor is not None else 0


def _data(valor: Any) -> str | None:
    if valor is None:
        return None
    if hasattr(valor, "date"):
        return valor.date().isoformat()
    return valor.isoformat() if hasattr(valor, "isoformat") else str(valor)


def _consultar_estoque(filtros: list[tuple[str, str, Any]]) -> list[dict[str, Any]]:
    """`:nome` + dict — o warehouse vai por `text()` do SQLAlchemy.

    Cada filtro e `(condicao, nome_do_parametro, valor)`: o nome vem separado porque o
    `text()` liga pelo dicionario de parametros, e a condicao sozinha nao diz o nome.
    """
    if filtros:
        onde = "where " + " and ".join(cond for cond, _, _ in filtros)
        params = {nome: valor for _, nome, valor in filtros}
    else:
        onde, params = "", {}
    sql = SQL_ESTOQUE.replace("{onde}", onde)
    with warehouse.engine().connect() as conn:
        return [dict(linha) for linha in conn.execute(text(sql), params).mappings()]


def _consultar_erp(sql: str, filtros: list[tuple[str, Any]]) -> list[dict[str, Any]]:
    """`?` + sequencia — o `erp.query` so aceita posicional."""
    if filtros:
        sql = sql.replace("{onde}", "and " + " and ".join(cond for cond, _ in filtros))
        params = tuple(valor for _, valor in filtros)
    else:
        sql = sql.replace("{onde}", "")
        params = ()
    return erp.query(sql, params)


# Catalogo, para o nome de produto e cor que nao tem peca em estoque.
#
# `core.estoque_pecas_em_aberto` traz `prod_desc`/`cor_desc` por join, so que so chegam
# ao resultado as cores que tem peca: uma cor prometida e ainda nao comprada voltava
# com codigo em vez de nome — que e o que a tela mostrava. Aqui o nome vem do cadastro
# (`Produtos` e `Car_Cores`), que cobre as duas situacoes.
SQL_CATALOGO_PRODUTOS = """
select rtrim(p.Codigo) as codigo, rtrim(p.Descricao) as descricao
from DBMicrodata_DGB.dbo.Produtos p
where p.Codigo in ({marcadores})
"""

SQL_CATALOGO_CORES = """
select rtrim(c.Codigo) as codigo, rtrim(c.Descricao) as descricao
from DBMicrodata_DGB.dbo.Car_Cores c
where c.Codigo in ({marcadores})
"""


def _nomes(codigos: list[str], sql: str) -> dict[str, str]:
    """`codigo -> descricao`. O `IN` e montado com a quantidade de `?` que o `erp.query` aceita."""
    unicos = sorted({c for c in codigos if c})[:900]
    if not unicos:
        return {}
    linhas = erp.query(sql.format(marcadores=", ".join(["?"] * len(unicos))), tuple(unicos))
    return {
        _texto(linha["codigo"]): _texto(linha["descricao"])
        for linha in linhas
        if _texto(linha["descricao"])
    }


@router.get("/estoque-disponibilidade")
def estoque_disponibilidade(
    usuario: _dependente,
    produto: str | None = Query(None, description="Codigo do produto"),
    cor: str | None = Query(None, description="Codigo da cor"),
    representante: str | None = Query(None, description="Codigo do vendedor da carteira"),
    empresa: str | None = Query(None, description="Empresa; so o admin troca a do token"),
    so_com_falta: bool = Query(False, description="So produto/cor cujo prometido passa do estoque"),
    so_chegando: bool = Query(False, description="So produto/cor com compra em transito"),
) -> dict[str, Any]:
    """O que tem, o que chega e o que ja foi prometido, por produto x cor.

    Filtros sao todos opcionais e combinaveis. `so_com_falta` e `so_chegando` sao
    pos-filtros: so da para aplicar depois de juntar as tres fontes.
    """
    empresa_alvo = empresa_efetiva(usuario, empresa)

    # Cada fonte tem seu proprio alias, entao os filtros tambem: mesmo parametro,
    # tres listas — e assim cada SQL recebe so os marcadores que ele usa. No estoque o
    # filtro carrega o nome do parametro (o `text()` liga pelo dicionario).
    estoque_filtros: list[tuple[str, str, Any]] = []
    caminho_filtros: list[tuple[str, Any]] = []
    carteira_filtros: list[tuple[str, Any]] = []

    if empresa_alvo:
        estoque_filtros.append(("empresa = :empresa", "empresa", empresa_alvo))
        caminho_filtros.append(("p.Empresa = ?", empresa_alvo))
        carteira_filtros.append(("q.Empresa = ?", empresa_alvo))
    if produto:
        estoque_filtros.append(("produto = :produto", "produto", produto.strip()))
        caminho_filtros.append(("rtrim(i.Produto) = ?", produto.strip()))
        carteira_filtros.append(("rtrim(q.Produto) = ?", produto.strip()))
    if cor:
        estoque_filtros.append(("cor = :cor", "cor", cor.strip()))
        caminho_filtros.append(("rtrim(i.Cor) = ?", cor.strip()))
        carteira_filtros.append(("rtrim(q.Cor) = ?", cor.strip()))
    if representante:
        # So a carteira tem vendedor: estoque e compra nao tem quem prometeu nada.
        carteira_filtros.append(("rtrim(q.Vendedor) = ?", representante.strip()))

    estoque = _consultar_estoque(estoque_filtros)
    caminho = _consultar_erp(SQL_CAMINHO, caminho_filtros)
    carteira = _consultar_erp(SQL_CARTEIRA, carteira_filtros)

    por_chave: dict[str, dict[str, Any]] = {}

    def linha_de(codigo_produto: Any, codigo_cor: Any) -> dict[str, Any]:
        chave = f"{_texto(codigo_produto)}|{_texto(codigo_cor)}"
        return por_chave.setdefault(
            chave,
            {
                "produto": _texto(codigo_produto),
                "produto_desc": "",
                "cor": _texto(codigo_cor),
                "cor_desc": "",
                "estoque_metros": 0.0,
                "estoque_pecas": 0,
                "estoque_rolos": 0,
                "caminho_metros": 0.0,
                "pedidos_compra": 0,
                "primeira_chegada": None,
                "ultima_chegada": None,
                "prometido_metros": 0.0,
                "prometido_valor": 0.0,
                "pedidos_venda": 0,
                "por_representante": [],
            },
        )

    for registro in estoque:
        linha = linha_de(registro["produto"], registro["cor"])
        linha["produto_desc"] = _texto(registro["produto_desc"])
        linha["cor_desc"] = _texto(registro["cor_desc"])
        linha["estoque_metros"] += _numero(registro["metros"])
        linha["estoque_pecas"] += _inteiro(registro["pecas"])
        linha["estoque_rolos"] += _inteiro(registro["rolos"])

    for registro in caminho:
        linha = linha_de(registro["produto"], registro["cor"])
        linha["caminho_metros"] += _numero(registro["metros"])
        linha["pedidos_compra"] += _inteiro(registro["pedidos"])
        primeira = _data(registro["primeira_chegada"])
        if primeira and (linha["primeira_chegada"] is None or primeira < linha["primeira_chegada"]):
            linha["primeira_chegada"] = primeira
        ultima = _data(registro["ultima_chegada"])
        if ultima and (linha["ultima_chegada"] is None or ultima > linha["ultima_chegada"]):
            linha["ultima_chegada"] = ultima

    for registro in carteira:
        linha = linha_de(registro["produto"], registro["cor"])
        linha["prometido_metros"] += _numero(registro["saldo"])
        linha["prometido_valor"] += _numero(registro["valor"])
        linha["pedidos_venda"] += _inteiro(registro["pedidos"])
        linha["por_representante"].append(
            {
                "vendedor": _texto(registro["vendedor"]),
                "vendedor_nome": _texto(registro["vendedor_nome"]),
                "pedidos": _inteiro(registro["pedidos"]),
                "saldo": _numero(registro["saldo"]),
                "valor": _numero(registro["valor"]),
            }
        )

    saidas: list[dict[str, Any]] = []
    for linha in por_chave.values():
        linha["livre_metros"] = linha["estoque_metros"] - linha["prometido_metros"]
        linha["cobertura_metros"] = linha["caminho_metros"] + linha["livre_metros"]
        linha["falta_metros"] = max(-linha["livre_metros"], 0.0)
        linha["por_representante"].sort(key=lambda r: -r["saldo"])
        if so_com_falta and linha["falta_metros"] <= 0:
            continue
        if so_chegando and linha["caminho_metros"] <= 0:
            continue
        saidas.append(linha)

    # Nome de produto e cor para quem ainda nao tem: so o estoque traz descricao (por
    # join), e cor prometida sem peca voltava com codigo. Uma consulta no cadastro
    # resolve — e so quando falta algum, que e o caso raro.
    faltando_produto = [linha for linha in saidas if not linha["produto_desc"]]
    faltando_cor = [linha for linha in saidas if not linha["cor_desc"]]
    if faltando_produto:
        nomes = _nomes([item["produto"] for item in faltando_produto], SQL_CATALOGO_PRODUTOS)
        for linha in saidas:
            linha["produto_desc"] = linha["produto_desc"] or nomes.get(linha["produto"], "")
    if faltando_cor:
        cores = _nomes([item["cor"] for item in faltando_cor], SQL_CATALOGO_CORES)
        for linha in saidas:
            linha["cor_desc"] = linha["cor_desc"] or cores.get(linha["cor"], "")

    # Maior falta primeiro: e a pergunta que o comercial abre a tela para responder.
    saidas.sort(key=lambda linha: (-linha["falta_metros"], -linha["estoque_metros"]))

    resumo = {
        "produtos_cor": len(saidas),
        "com_falta": sum(1 for linha in saidas if linha["falta_metros"] > 0),
        "total_estoque": sum(linha["estoque_metros"] for linha in saidas),
        "total_caminho": sum(linha["caminho_metros"] for linha in saidas),
        "total_prometido": sum(linha["prometido_metros"] for linha in saidas),
        "total_falta": sum(linha["falta_metros"] for linha in saidas),
        "valor_prometido": sum(linha["prometido_valor"] for linha in saidas),
    }
    return {"resumo": resumo, "linhas": saidas}


@router.get("/estoque-disponibilidade/pedidos")
def estoque_disponibilidade_pedidos(
    usuario: _dependente,
    produto: str | None = Query(None, description="Codigo do produto"),
    cor: str | None = Query(None, description="Codigo da cor"),
    empresa: str | None = Query(None, description="Empresa; so o admin troca a do token"),
) -> dict[str, Any]:
    """Os pedidos de venda que formam o prometido de uma produto/cor, um a um.

    A rota principal volta agregado por representante; aqui vem o **codigo do pedido**,
    o cliente e as datas — o que o comercial precisa para cobrar quem prometeu, e o
    que o PDF/CSV do relatorio lista linha a linha.
    """
    empresa_alvo = empresa_efetiva(usuario, empresa)
    filtros: list[tuple[str, Any]] = []
    if empresa_alvo:
        filtros.append(("q.Empresa = ?", empresa_alvo))
    if produto:
        filtros.append(("rtrim(q.Produto) = ?", produto.strip()))
    if cor:
        filtros.append(("rtrim(q.Cor) = ?", cor.strip()))

    linhas = _consultar_erp(SQL_PEDIDOS, filtros)
    saidas = [
        {
            "empresa": _texto(linha["empresa"]),
            "pedido": _texto(linha["pedido"]),
            "cliente": _texto(linha["cliente"]),
            "cliente_nome": _texto(linha["cliente_nome"]),
            "vendedor": _texto(linha["vendedor"]),
            "vendedor_nome": _texto(linha["vendedor_nome"]),
            "produto": _texto(linha["produto"]),
            "cor": _texto(linha["cor"]),
            "data_pedido": _data(linha["data_pedido"]),
            "data_entrega": _data(linha["data_entrega"]),
            "qtde_pedido": _numero(linha["qtde_pedido"]),
            "qtde_romaneada": _numero(linha["qtde_romaneada"]),
            "saldo": _numero(linha["saldo"]),
            "valor": _numero(linha["valor"]),
            "status": _texto(linha["status"]),
        }
        for linha in linhas
        if _numero(linha["saldo"]) > 0
    ]
    saidas.sort(key=lambda linha: (linha["data_pedido"] or "", linha["pedido"]), reverse=True)
    return {
        "total": len(saidas),
        "saldo": sum(linha["saldo"] for linha in saidas),
        "valor": sum(linha["valor"] for linha in saidas),
        "pedidos": saidas,
    }


__all__ = ["router"]
