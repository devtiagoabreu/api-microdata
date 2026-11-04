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
from src.db import warehouse

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


def _filtros(
    *,
    busca: str | None,
    cnpj: str | None,
    data_inicio: date | None,
    data_fim: date | None,
    empresa: str | None,
    campo_busca: str,
    campo_cnpj: str,
    campo_data: str,
) -> tuple[str, dict[str, Any]]:
    """Monta o `where` compartilhado por pedidos e faturamentos."""
    clausulas: list[str] = []
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
        "cliente_cnpj": _texto(linha.get("cliente")),
        "cliente_nome": _texto(linha.get("cliente_nome")),
        "data_pedido": _data(linha.get("data_pedido")),
        "data_entrega": _data(linha.get("data_entrega")),
        "status": _texto(linha.get("status")),
        "status_pedido": _texto(linha.get("status_ped")),
        "condicao_pagamento": _texto(linha.get("cond_pagto")),
        "representante": _texto(linha.get("pedido_representante")),
        "identificador_erp": _texto(linha.get("pedido_id")),
        "itens": int(linha.get("itens") or 0),
        "quantidade": _numero(linha.get("quantidade")),
        "valor_total": _numero(linha.get("valor_total")),
    }


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
    documento["itens"] = len(itens)
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
select i.item, i.cod_produto, i.des_produto, i.unidade, i.qtde, i.metros,
  i.vr_unitario, i.vr_total, i.acres_desc
from raw.fat_itens_pedido i
where i.empresa = :empresa and i.pedido = :pedido
order by i.item
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
        "itens": int(linha.get("itens") or 0),
        "quantidade": _numero(linha.get("quantidade")),
        "valor_total": _numero(linha.get("valor_total")),
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
    usuario: _faturamento = None,
) -> dict[str, Any]:
    """Faturamentos (notas) do ERP (documento), prontos para busca e selecao pelo CRM."""
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
                {"empresa": empresa, "pedido": pedido},
            ).mappings()
        ]
    documento = _linha_faturamento(dict(cabecalho))
    documento["itens"] = len(itens)
    documento["quantidade"] = sum(item["quantidade"] for item in itens)
    documento["valor_total"] = sum(
        item["valor_total"] + item["acrescimo_desconto"] for item in itens
    )
    return {**documento, "itens": itens}
