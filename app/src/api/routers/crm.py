"""Documentos do ERP para o CRM (dgbcomex): pedidos de venda e faturamentos para vincular.

O CRM precisa **vincular** pedidos e notas do ERP a uma pessoa/oportunidade. A API do CRM
(dgbcomex) nao fala com o ERP: ela fala com esta API, que le a carga do ERP no warehouse local
(schema `raw`) e devolve documentos (e nao itens) prontos para busca e selecao.

Fontes:

- **pedido de venda**: `raw.car_pedido` (cabecalho) + `raw.car_itens_pedido` (itens);
- **faturamento (nota)**: `raw.fat_pedido` (cabecalho) + `raw.fat_itens_pedido` (itens).

Detalhe que importa para o CRM: no ERP o campo `cliente` **e o CNPJ** do cliente
(`Clientes_Principal.Codigo_Cliente`), entao o filtro `cnpj` casa direto com o cadastro do
CRM sem passar por nome.

Escopos: pedidos exigem `estoque:leitura` (mesmo do WMS, que le a mesma tabela) e faturamentos
exigem `faturamento:leitura` (mesmo do detalhe de faturamento do BI).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from src.api.auth.escopos import (
    ESCOPO_ESTOQUE,
    ESCOPO_FATURAMENTO,
    empresa_efetiva,
    exigir_escopo,
)
from src.api.auth.usuarios import Usuario
from src.db import erp, warehouse
from src.etl import delta_erp

router = APIRouter(tags=["crm"])

_estoque = Annotated[Usuario | None, Depends(exigir_escopo(ESCOPO_ESTOQUE))]
_faturamento = Annotated[Usuario | None, Depends(exigir_escopo(ESCOPO_FATURAMENTO))]


def _texto(valor: Any) -> str | None:
    """Texto do ERP vem com espaco no fim (colunas char) -> strip e None quando vazio."""
    if valor is None:
        return None
    if not isinstance(valor, str):
        return str(valor)
    limpo = valor.strip()
    return limpo or None


def _data(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)[:10]


def _numero(valor: Any) -> float:
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def _paginacao(total: int, pagina: int, por_pagina: int) -> dict[str, Any]:
    return {
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total_paginas": (total + por_pagina - 1) // por_pagina if total else 0,
    }


PEDIDOS_NAO_CANCELADOS = "(p.status is null or p.status <> '3')"
PEDIDOS_NAO_FATURADOS = (
    "not exists (select 1 from raw.fat_pedido f "
    "where f.empresa = p.empresa and f.nosso_pedido = p.pedido)"
)


def _filtros(
    *,
    busca: str | None = None,
    cnpj: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    empresa: str | None = None,
    campo_busca: str,
    campo_cnpj: str,
    campo_data: str,
    pedido_origem: str | None = None,
    condicoes_base: tuple[str, ...] = (),
) -> tuple[str, dict[str, Any]]:
    """Monta o `where` compartilhado por pedidos e faturamentos."""
    clausulas: list[str] = list(condicoes_base)
    params: dict[str, Any] = {}

    if empresa:
        clausulas.append("p.empresa = :empresa")
        params["empresa"] = empresa

    if busca:
        clausulas.append(f"(p.{campo_busca} ilike :busca or c.razao_nome_cliente ilike :busca)")
        params["busca"] = f"%{busca.strip()}%"

    if cnpj:
        # O ERP guarda o CNPJ do cliente no campo `cliente`; compara só os dígitos para
        # aceitar "12.345.678/0001-90" e "12345678000190" como o mesmo cliente.
        clausulas.append(f"regexp_replace(p.{campo_cnpj}, '[^0-9]', '', 'g') = :cnpj")
        params["cnpj"] = "".join(ch for ch in cnpj if ch.isdigit())

    if data_inicio:
        clausulas.append(f"p.{campo_data} >= :data_inicio")
        params["data_inicio"] = data_inicio

    if data_fim:
        clausulas.append(f"p.{campo_data} <= :data_fim")
        params["data_fim"] = data_fim

    if pedido_origem:
        clausulas.append("p.nosso_pedido = :pedido_origem")
        params["pedido_origem"] = pedido_origem

    where = "where " + " and ".join(clausulas) if clausulas else ""
    return where, params


# ---------------------------------------------------------------------------
# Pedidos de venda
# ---------------------------------------------------------------------------

SQL_PEDIDOS = """
select p.empresa, p.pedido, p.cliente, c.razao_nome_cliente as cliente_nome,
  p.data_pedido, p.data_entrega, p.status, p.status_ped, p.cond_pagto,
  p.pedido_representante, p.pedido_id,
  count(i.item)::int as itens,
  coalesce(sum(coalesce(i.qtde, 0)), 0) as quantidade,
  coalesce(sum(coalesce(i.vr_total, 0)), 0) as valor_total
from raw.car_pedido p
left join raw.clientes_principal c on c.codigo_cliente = p.cliente
left join raw.car_itens_pedido i on i.empresa = p.empresa and i.pedido = p.pedido
{where}
group by p.empresa, p.pedido, p.cliente, c.razao_nome_cliente, p.data_pedido,
  p.data_entrega, p.status, p.status_ped, p.cond_pagto, p.pedido_representante, p.pedido_id
order by p.data_pedido desc nulls last, p.pedido desc
limit :por_pagina offset :offset
"""

SQL_PEDIDOS_TOTAL = """
select count(*)::int as total
from raw.car_pedido p
left join raw.clientes_principal c on c.codigo_cliente = p.cliente
{where}
"""

SQL_PEDIDO_ITENS = """
select i.item, i.produto, i.situacao, i.cor, i.desenho, i.qtde, i.unid,
  i.vr_unitario, i.vr_total, i.status_item, i.data_entrega
from raw.car_itens_pedido i
where i.empresa = :empresa and i.pedido = :pedido
order by i.item
"""


def _linha_pedido(linha: dict[str, Any]) -> dict[str, Any]:
    return {
        "empresa": _texto(linha.get("empresa")),
        "pedido": _texto(linha.get("pedido")),
        "pedido_origem": _texto(linha.get("pedido")),
        "cliente_cnpj": _texto(linha.get("cliente")),
        "cliente_nome": _texto(linha.get("cliente_nome")),
        "data_pedido": _data(linha.get("data_pedido")),
        "data_entrega": _data(linha.get("data_entrega")),
        "status": _texto(linha.get("status")),
        "status_pedido": _texto(linha.get("status_ped")),
        "condicao_pagamento": _texto(linha.get("cond_pagto")),
        "representante": _texto(linha.get("pedido_representante")),
        "identificador_erp": _texto(linha.get("pedido_id")),
        "total_itens": int(linha.get("itens") or 0),
        "quantidade": _numero(linha.get("quantidade")),
        "valor_total": _numero(linha.get("valor_total")),
    }


def _itens_pedido_erp(linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "item": int(linha.get("item") or 0),
            "produto": _texto(linha.get("produto")),
            "situacao": _texto(linha.get("situacao")),
            "cor": _texto(linha.get("cor")),
            "desenho": _texto(linha.get("desenho")),
            "quantidade": _numero(linha.get("qtde")),
            "unidade": _texto(linha.get("unid")),
            "valor_unitario": _numero(linha.get("vr_unitario")),
            "valor_total": _numero(linha.get("vr_total")),
            "status": _texto(linha.get("status_item")),
            "data_entrega": _data(linha.get("data_entrega")),
        }
        for linha in linhas
    ]


@router.get("/crm/pedidos-faturados/{empresa}/{pedido}")
def detalhe_pedido_faturado(
    empresa: str,
    pedido: str,
    empresa_consultada: str | None = None,
    usuario: _estoque = None,
) -> dict[str, Any]:
    """Pedido já faturado, lido direto do ERP (o warehouse só guarda pedidos em aberto)."""
    empresa_alvo = empresa_efetiva(usuario, empresa_consultada)
    if empresa_alvo and empresa_alvo != empresa:
        raise HTTPException(status_code=403, detail="voce so acessa a empresa {empresa_alvo}")

    cabecalhos = erp.query(
        "select p.Empresa as empresa, p.Pedido as pedido, p.Cliente as cliente, "
        "c.Razao_Nome_Cliente as cliente_nome, p.Data_Pedido as data_pedido, "
        "p.Data_Entrega as data_entrega, p.Status as status, p.Status_Ped as status_ped, "
        "p.Cond_Pagto as cond_pagto, p.Pedido_Representante as pedido_representante, "
        "p.pedido_id as pedido_id from dbo.Car_Pedido p "
        "left join dbo.Clientes_Principal c on c.Codigo_Cliente = p.Cliente "
        "where p.Empresa = ? and p.Pedido = ?",
        (empresa, pedido),
    )
    if not cabecalhos:
        raise HTTPException(status_code=404, detail="Pedido nao encontrado")

    itens = _itens_pedido_erp(
        erp.query(
            "select i.Item as item, i.Produto as produto, i.Situacao as situacao, "
            "i.Cor as cor, i.Desenho as desenho, i.Qtde as qtde, i.Unid as unid, "
            "i.Vr_Unitario as vr_unitario, i.Vr_Total as vr_total, "
            "i.Status_Item as status_item, i.Data_Entrega as data_entrega "
            "from dbo.Car_Itens_Pedido i "
            "where i.Empresa = ? and i.Pedido = ? order by i.Item",
            (empresa, pedido),
        )
    )
    documento = _linha_pedido(dict(cabecalhos[0]))
    documento["total_itens"] = len(itens)
    documento["quantidade"] = sum(item["quantidade"] for item in itens)
    documento["valor_total"] = sum(item["valor_total"] for item in itens)
    return {**documento, "itens": itens}


@router.get("/crm/pedidos")
def listar_pedidos(
    busca: str | None = None,
    cnpj: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    empresa: str | None = None,
    pagina: int = 1,
    por_pagina: int = 50,
    usuario: _estoque = None,
) -> dict[str, Any]:
    """Pedidos de venda do ERP (documento), prontos para busca e selecao pelo CRM."""
    if pagina < 1:
        raise HTTPException(status_code=422, detail="pagina comeca em 1")
    por_pagina = max(1, min(por_pagina, 500))
    empresa_alvo = empresa_efetiva(usuario, empresa)
    where, params = _filtros(
        busca=busca,
        cnpj=cnpj,
        data_inicio=data_inicio,
        data_fim=data_fim,
        empresa=empresa_alvo,
        campo_busca="pedido",
        campo_cnpj="cliente",
        campo_data="data_pedido",
        condicoes_base=(PEDIDOS_NAO_CANCELADOS, PEDIDOS_NAO_FATURADOS),
    )
    with warehouse.engine().connect() as conn:
        total = int(conn.execute(text(SQL_PEDIDOS_TOTAL.format(where=where)), params).scalar() or 0)
        linhas = [
            dict(linha)
            for linha in conn.execute(
                text(SQL_PEDIDOS.format(where=where)),
                {**params, "por_pagina": por_pagina, "offset": (pagina - 1) * por_pagina},
            ).mappings()
        ]
    return {
        "paginacao": _paginacao(total, pagina, por_pagina),
        "itens": [_linha_pedido(linha) for linha in linhas],
    }


@router.post("/crm/pedidos/sincronizar")
def sincronizar_pedidos(usuario: _estoque = None) -> dict[str, Any]:
    return delta_erp.sincronizar_pedidos()


@router.get("/crm/pedidos/{empresa}/{pedido}")
def detalhe_pedido(
    empresa: str,
    pedido: str,
    empresa_consultada: str | None = None,
    usuario: _estoque = None,
) -> dict[str, Any]:
    """Cabecalho + itens de um pedido do ERP."""
    empresa_alvo = empresa_efetiva(usuario, empresa_consultada)
    if empresa_alvo and empresa_alvo != empresa:
        raise HTTPException(status_code=403, detail="voce so acessa a empresa {empresa_alvo}")
    with warehouse.engine().connect() as conn:
        cabecalho = (
            conn.execute(
                text(
                    "select p.empresa, p.pedido, p.cliente, c.razao_nome_cliente as cliente_nome, "
                    "p.data_pedido, p.data_entrega, p.status, p.status_ped, p.cond_pagto, "
                    "p.pedido_representante, p.pedido_id "
                    "from raw.car_pedido p "
                    "left join raw.clientes_principal c on c.codigo_cliente = p.cliente "
                    "where p.empresa = :empresa and p.pedido = :pedido"
                ),
                {"empresa": empresa, "pedido": pedido},
            )
            .mappings()
            .one_or_none()
        )
        if cabecalho is None:
            raise HTTPException(status_code=404, detail="Pedido nao encontrado")
        itens = [
            {
                "item": int(linha.get("item") or 0),
                "produto": _texto(linha.get("produto")),
                "situacao": _texto(linha.get("situacao")),
                "cor": _texto(linha.get("cor")),
                "desenho": _texto(linha.get("desenho")),
                "quantidade": _numero(linha.get("qtde")),
                "unidade": _texto(linha.get("unid")),
                "valor_unitario": _numero(linha.get("vr_unitario")),
                "valor_total": _numero(linha.get("vr_total")),
                "status": _texto(linha.get("status_item")),
                "data_entrega": _data(linha.get("data_entrega")),
            }
            for linha in conn.execute(
                text(SQL_PEDIDO_ITENS), {"empresa": empresa, "pedido": pedido}
            ).mappings()
        ]
    documento = _linha_pedido(dict(cabecalho))
    documento["total_itens"] = len(itens)
    documento["quantidade"] = sum(item["quantidade"] for item in itens)
    documento["valor_total"] = sum(item["valor_total"] for item in itens)
    return {**documento, "itens": itens}


# ---------------------------------------------------------------------------
# Faturamento (notas fiscais)
# ---------------------------------------------------------------------------

SQL_FATURAMENTOS = """
select p.empresa, p.pedido, p.nr_nota, p.serie, p.cliente,
  c.razao_nome_cliente as cliente_nome,
  p.data_nota, p.data_emissao, p.vr_nota, p.soma_itens, p.nosso_pedido,
  p.status_gravado, p.cond_pagto_extenso,
  count(i.item)::int as itens,
  coalesce(sum(coalesce(i.qtde, 0)), 0) as quantidade,
  coalesce(sum(coalesce(i.vr_total, 0) + coalesce(i.acres_desc, 0)), 0) as valor_total
from raw.fat_pedido p
left join raw.clientes_principal c on c.codigo_cliente = p.cliente
left join raw.fat_itens_pedido i on i.empresa = p.empresa and i.pedido = p.pedido
{where}
group by p.empresa, p.pedido, p.nr_nota, p.serie, p.cliente, c.razao_nome_cliente,
  p.data_nota, p.data_emissao, p.vr_nota, p.soma_itens, p.nosso_pedido,
  p.status_gravado, p.cond_pagto_extenso
order by p.data_nota desc nulls last, p.nr_nota desc
limit :por_pagina offset :offset
"""

SQL_FATURAMENTOS_TOTAL = """
select count(*)::int as total
from raw.fat_pedido p
left join raw.clientes_principal c on c.codigo_cliente = p.cliente
{where}
"""

SQL_FATURAMENTO_ITENS = """
select distinct i.item, i.cod_produto, i.des_produto, i.unidade, i.qtde, i.metros,
  i.vr_unitario, i.vr_total, i.acres_desc
from raw.fat_itens_pedido i
join raw.fat_pedido p on p.empresa = i.empresa and p.pedido = i.pedido
where p.empresa = :empresa and p.nr_nota = :nr_nota
order by i.item, i.cod_produto
"""

SQL_FATURAMENTOS_POR_PEDIDO = """
select p.Empresa as empresa, p.Pedido as pedido, p.Nr_Nota as nr_nota,
  p.Serie as serie, p.Cliente as cliente, c.Razao_Nome_Cliente as cliente_nome,
  p.Data_Nota as data_nota, p.Data_Emissao as data_emissao,
  p.Vr_Nota as vr_nota, p.Soma_Itens as soma_itens, p.Nosso_Pedido as nosso_pedido,
  p.Status_Gravado as status_gravado, p.Cond_Pagto_Extenso as cond_pagto_extenso,
  count(i.Item) as itens,
  coalesce(sum(coalesce(i.Qtde, 0)), 0) as quantidade,
  coalesce(sum(coalesce(i.Vr_Total, 0) + coalesce(i.Acres_Desc, 0)), 0) as valor_total
from dbo.Fat_Pedido p
left join dbo.Clientes_Principal c on c.Codigo_Cliente = p.Cliente
left join dbo.Fat_Itens_Pedido i on i.Empresa = p.Empresa and i.Pedido = p.Pedido
where {condicoes}
group by p.Empresa, p.Pedido, p.Nr_Nota, p.Serie, p.Cliente, c.Razao_Nome_Cliente,
  p.Data_Nota, p.Data_Emissao, p.Vr_Nota, p.Soma_Itens, p.Nosso_Pedido,
  p.Status_Gravado, p.Cond_Pagto_Extenso
order by p.Data_Nota desc, p.Nr_Nota desc
"""


def _linha_faturamento(linha: dict[str, Any]) -> dict[str, Any]:
    return {
        "empresa": _texto(linha.get("empresa")),
        "pedido": _texto(linha.get("pedido")),
        "nr_nota": _texto(linha.get("nr_nota")),
        "serie": _texto(linha.get("serie")),
        "cliente_cnpj": _texto(linha.get("cliente")),
        "cliente_nome": _texto(linha.get("cliente_nome")),
        "data_nota": _data(linha.get("data_nota")),
        "data_emissao": _data(linha.get("data_emissao")),
        "pedido_origem": _texto(linha.get("nosso_pedido")),
        "status": _texto(linha.get("status_gravado")),
        "condicao_pagamento": _texto(linha.get("cond_pagto_extenso")),
        "valor_nota": _numero(linha.get("vr_nota")),
        "total_itens": int(linha.get("itens") or 0),
        "quantidade": _numero(linha.get("quantidade")),
        "valor_total": _numero(linha.get("valor_total")),
    }


@router.get("/crm/faturamentos-por-pedido/{pedido}")
def faturamentos_por_pedido(
    pedido: str,
    empresa: str | None = None,
    empresa_consultada: str | None = None,
    usuario: _faturamento = None,
) -> dict[str, Any]:
    empresa_alvo = empresa_efetiva(usuario, empresa_consultada)
    if empresa_alvo and empresa and empresa_alvo != empresa:
        raise HTTPException(status_code=403, detail=f"voce so acessa a empresa {empresa_alvo}")
    condicoes = ["ltrim(rtrim(p.Nosso_Pedido)) = ?"]
    parametros: list[Any] = [pedido.strip()]
    alvo = empresa_alvo or empresa
    if alvo:
        condicoes.append("p.Empresa = ?")
        parametros.append(alvo)
    linhas = erp.query(
        SQL_FATURAMENTOS_POR_PEDIDO.format(condicoes=" and ".join(condicoes)),
        tuple(parametros),
    )
    itens = [_linha_faturamento(dict(linha)) for linha in linhas]
    return {
        "paginacao": _paginacao(len(itens), 1, max(1, len(itens))),
        "itens": itens,
    }


@router.get("/crm/faturamentos")
def listar_faturamentos(
    busca: str | None = None,
    cnpj: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    empresa: str | None = None,
    pagina: int = 1,
    por_pagina: int = 50,
    pedido_origem: str | None = None,
    usuario: _faturamento = None,
) -> dict[str, Any]:
    """Faturamentos (notas) do ERP (documento), prontos para busca e selecao pelo CRM.

    `pedido_origem` filtra notas pelo número original do pedido do ERP (`nosso_pedido`),
    usado pelo CRM para encontrar a nota de um pedido já vinculado.
    """
    if pagina < 1:
        raise HTTPException(status_code=422, detail="pagina comeca em 1")
    por_pagina = max(1, min(por_pagina, 500))
    empresa_alvo = empresa_efetiva(usuario, empresa)
    where, params = _filtros(
        busca=busca,
        cnpj=cnpj,
        data_inicio=data_inicio,
        data_fim=data_fim,
        empresa=empresa_alvo,
        campo_busca="nr_nota",
        campo_cnpj="cliente",
        campo_data="data_nota",
        pedido_origem=pedido_origem,
    )
    with warehouse.engine().connect() as conn:
        total = int(
            conn.execute(text(SQL_FATURAMENTOS_TOTAL.format(where=where)), params).scalar() or 0
        )
        linhas = [
            dict(linha)
            for linha in conn.execute(
                text(SQL_FATURAMENTOS.format(where=where)),
                {**params, "por_pagina": por_pagina, "offset": (pagina - 1) * por_pagina},
            ).mappings()
        ]
    return {
        "paginacao": _paginacao(total, pagina, por_pagina),
        "itens": [_linha_faturamento(linha) for linha in linhas],
    }


@router.post("/crm/faturamentos/sincronizar")
def sincronizar_faturamentos(usuario: _faturamento = None) -> dict[str, Any]:
    return delta_erp.sincronizar_faturamentos()


@router.get("/crm/faturamentos/{empresa}/{pedido}/{nr_nota}/pedidos")
def pedidos_da_nota(
    empresa: str,
    pedido: str,
    nr_nota: str,
    empresa_consultada: str | None = None,
    usuario: _faturamento = None,
) -> dict[str, Any]:
    """Pedidos de venda (nosso_pedido) que compõem uma nota faturada."""
    empresa_alvo = empresa_efetiva(usuario, empresa_consultada)
    if empresa_alvo and empresa_alvo != empresa:
        raise HTTPException(status_code=403, detail="voce so acessa a empresa {empresa_alvo}")
    linhas = erp.query(
        "select distinct nullif(ltrim(rtrim(p.Nosso_Pedido)), '') as pedido "
        "from dbo.Fat_Pedido p "
        "where p.Empresa = ? and p.Nr_Nota = ? order by 1",
        (empresa, nr_nota),
    )
    return {
        "empresa": empresa,
        "pedido": pedido,
        "nr_nota": nr_nota,
        "pedidos": [_texto(linha.get("pedido")) for linha in linhas if _texto(linha.get("pedido"))],
    }


@router.get("/crm/faturamentos/{empresa}/{pedido}/{nr_nota}")
def detalhe_faturamento(
    empresa: str,
    pedido: str,
    nr_nota: str,
    empresa_consultada: str | None = None,
    usuario: _faturamento = None,
) -> dict[str, Any]:
    """Cabecalho + itens de um faturamento (nota) do ERP."""
    empresa_alvo = empresa_efetiva(usuario, empresa_consultada)
    if empresa_alvo and empresa_alvo != empresa:
        raise HTTPException(status_code=403, detail="voce so acessa a empresa {empresa_alvo}")
    with warehouse.engine().connect() as conn:
        cabecalho = (
            conn.execute(
                text(
                    "select p.empresa, p.pedido, p.nr_nota, p.serie, p.cliente, "
                    "c.razao_nome_cliente as cliente_nome, p.data_nota, p.data_emissao, "
                    "p.vr_nota, p.soma_itens, p.nosso_pedido, p.status_gravado, "
                    "p.cond_pagto_extenso "
                    "from raw.fat_pedido p "
                    "left join raw.clientes_principal c on c.codigo_cliente = p.cliente "
                    "where p.empresa = :empresa and p.pedido = :pedido and p.nr_nota = :nr_nota"
                ),
                {"empresa": empresa, "pedido": pedido, "nr_nota": nr_nota},
            )
            .mappings()
            .one_or_none()
        )
        if cabecalho is None:
            raise HTTPException(status_code=404, detail="Faturamento nao encontrado")
        itens = [
            {
                "item": int(linha.get("item") or 0),
                "produto": _texto(linha.get("cod_produto")),
                "descricao": _texto(linha.get("des_produto")),
                "quantidade": _numero(linha.get("qtde")),
                "metros": _numero(linha.get("metros")),
                "unidade": _texto(linha.get("unidade")),
                "valor_unitario": _numero(linha.get("vr_unitario")),
                "valor_total": _numero(linha.get("vr_total")),
                "acrescimo_desconto": _numero(linha.get("acres_desc")),
            }
            for linha in conn.execute(
                text(SQL_FATURAMENTO_ITENS),
                {"empresa": empresa, "nr_nota": nr_nota},
            ).mappings()
        ]
    documento = _linha_faturamento(dict(cabecalho))
    documento["total_itens"] = len(itens)
    documento["quantidade"] = sum(item["quantidade"] for item in itens)
    documento["valor_total"] = sum(
        item["valor_total"] + item["acrescimo_desconto"] for item in itens
    )
    return {**documento, "itens": itens}
