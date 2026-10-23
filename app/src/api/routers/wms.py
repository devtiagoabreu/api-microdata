"""WMS: separacao de pedidos no Postgres local.

O modulo WMS **nao** roda no dgbcomex (Vercel): o front chama as rotas Next.js, que fazem
proxy autenticado para ca.

Fontes de leitura (ERP, somente leitura) e de escrita (banco local):

- `raw.car_pedido` + `raw.car_itens_pedido`: pedidos liberados (status 2 e abertos), itens e
  saldo (`qtde - qtde_romaneio - qtde_acerto`).
- `raw.cte_peca` - `raw.cte_baixa`: pecas fisicamente em aberto (gaveta/endereco, sublote,
  aviso, grade).
- `raw.cte_gaveta` + `raw.cte_grupo_gaveta`: catalogo de gavetas (enderecos) e zonas, criado
  no ERP e espelhado aqui.
- `public.wms_separacoes` + `public.wms_separacao_pecas`: ordens de separacao (comercial marca
  o pedido; estoque seleciona as pecas). Pecas reservadas/separadas ficam bloqueadas para
  qualquer outra ordem, mesmo que o ERP ainda as mostre em aberto.

Escopo: as rotas exigem `estoque:leitura` (o usuario de servico do dgbcomex ja tem). A
autorizacao por usuario final fica no dgbcomex; aqui a API confia no token de servico.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.api.auth.escopos import ESCOPO_ESTOQUE, exigir_escopo
from src.api.auth.usuarios import Usuario
from src.db import warehouse

router = APIRouter(tags=["wms"])

_dependente = Annotated[Usuario | None, Depends(exigir_escopo(ESCOPO_ESTOQUE))]

STATUS_LIBERADO = "LIBERADO"
STATUS_EM_SEPARACAO = "EM_SEPARACAO"
STATUS_SEPARADO = "SEPARADO"
STATUS_CANCELADO = "CANCELADO"
STATUS_ATIVOS = (STATUS_LIBERADO, STATUS_EM_SEPARACAO)
STATUS_PECA_ATIVA = ("RESERVADA", "SEPARADA")
LIMITE_MAX = 500

# Uma peca peca pode estar em uma unica ordem enquanto reservada/separada. Depois da baixa
# no ERP ela some do estoque em aberto; a linha continua no historico da ordem.
SQL_ABERTAS = """
not exists (
    select 1
    from raw.cte_baixa b
    where b.empresa = a.empresa
      and b.nro_rolo = a.nro_rolo
      and b.nro_peca = a.nro_peca
)
and a.nro_rolo_origem is null
"""

SQL_RESERVADAS = """
not exists (
    select 1
    from public.wms_separacao_pecas sp
    where sp.empresa = a.empresa
      and sp.nro_rolo = a.nro_rolo
      and sp.nro_peca = a.nro_peca
      and sp.status in ('RESERVADA', 'SEPARADA')
)
"""


class Modelo(BaseModel):
    """Corpo em camelCase (o dgbcomex manda assim) e aceita snake_case tambem."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class Acao(Modelo):
    usuario_id: int | None = None
    observacao: str | None = None


class Cancelamento(Acao):
    motivo: str | None = None


class NovaSeparacao(Modelo):
    empresa: str
    pedido: str
    usuario_id: int | None = None
    observacao: str | None = None


class PecaRef(Modelo):
    empresa: str | None = None
    nro_rolo: str
    nro_peca: str


class AdicionarPecas(Modelo):
    item: int
    pecas: list[PecaRef] = Field(min_length=1)
    usuario_id: int | None = None


def _texto(valor: str | None) -> str | None:
    if valor is None:
        return None
    limpo = valor.strip()
    return limpo or None


def _decimal_texto(valor: Any) -> str | None:
    """Igual ao Drizzle: coluna `numeric` sai como string para nao perder escala."""
    return None if valor is None else f"{valor:f}"


def _float(valor: Any) -> float | None:
    return None if valor is None else float(valor)


def _float0(valor: Any) -> float:
    return 0.0 if valor is None else float(valor)


def _data(valor: Any) -> str | None:
    return valor.isoformat() if valor is not None and hasattr(valor, "isoformat") else valor


def _painel(linha: Any) -> dict[str, Any]:
    return {
        "id": linha["id"],
        "empresa": linha["empresa"],
        "pedido": linha["pedido"],
        "status": linha["status"],
        "clienteCodigo": linha["cliente_codigo"],
        "clienteNome": linha["cliente_nome"],
        "dataPedido": linha["data_pedido"],
        "dataEntrega": linha["data_entrega"],
        "observacao": linha["observacao"],
        "motivoCancelamento": linha["motivo_cancelamento"],
        "criadoPor": linha["criado_por"],
        "iniciadoPor": linha["iniciado_por"],
        "concluidoPor": linha["concluido_por"],
        "canceladoPor": linha["cancelado_por"],
        "criadoEm": _data(linha["criado_em"]),
        "iniciadoEm": _data(linha["iniciado_em"]),
        "concluidoEm": _data(linha["concluido_em"]),
        "canceladoEm": _data(linha["cancelado_em"]),
        "atualizadoEm": _data(linha["atualizado_em"]),
        "totalPecas": linha["total_pecas"],
        "totalMetros": _float0(linha["total_metros"]),
        "itensSeparados": linha["itens_separados"],
        "saldoMetros": _float0(linha["saldo_metros"]),
    }


def _peca(linha: Any) -> dict[str, Any]:
    return {
        "id": linha["id"],
        "item": linha["item"],
        "empresa": linha["empresa"],
        "nroRolo": linha["nro_rolo"],
        "nroPeca": linha["nro_peca"],
        "produto": linha["produto"],
        "produtoDesc": linha["produto_desc"],
        "situacao": linha["situacao"],
        "cor": linha["cor"],
        "corDesc": linha["cor_desc"],
        "desenho": linha["desenho"],
        "variante": linha["variante"],
        "categoria": linha["categoria"],
        "largura": linha["largura"],
        "subLote": linha["sub_lote"],
        "aviso": linha["aviso"],
        "gaveta": linha["gaveta"],
        "gavetaDescricao": linha["gaveta_descricao"],
        "zona": linha["zona"],
        "metros": _float(linha["metros"]),
        "peso": _float(linha["peso"]),
        "status": linha["status"],
        "adicionadoEm": _data(linha["adicionado_em"]),
        "baixadoNoErp": bool(linha["baixado_no_erp"]),
    }


def _gaveta(linha: Any) -> dict[str, Any]:
    return {
        "codigo": linha["codigo"],
        "descricao": linha["descricao"],
        "grupoGaveta": linha["grupo_gaveta"],
        "zona": linha["zona"],
        "setor": linha["setor"],
        "fazSugestao": linha["faz_sugestao"],
        "estoquePlano": linha["estoque_plano"],
        "confirmarTransferencia": linha["confirmar_transferencia"],
        "pecas": linha["pecas"],
        "metros": _float0(linha["metros"]),
    }


def _evento(
    conn: Any,
    separacao_id: int,
    tipo: str,
    *,
    descricao: str | None = None,
    usuario_id: int | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        text(
            """
            insert into public.wms_separacao_eventos
                (separacao_id, tipo, descricao, usuario_id, payload)
            values
                (:separacao_id, :tipo, :descricao, :usuario_id, cast(:payload as jsonb))
            """
        ),
        {
            "separacao_id": separacao_id,
            "tipo": tipo,
            "descricao": descricao,
            "usuario_id": usuario_id,
            "payload": None if payload is None else json.dumps(payload, ensure_ascii=False),
        },
    )


SQL_SEPARACAO = """
select
    s.*,
    (
        select count(*)::int
        from public.wms_separacao_pecas sp
        where sp.separacao_id = s.id
    ) as total_pecas,
    (
        select cast(coalesce(sum(sp.metros), 0) as double precision)
        from public.wms_separacao_pecas sp
        where sp.separacao_id = s.id
    ) as total_metros,
    (
        select count(distinct sp.item)::int
        from public.wms_separacao_pecas sp
        where sp.separacao_id = s.id
    ) as itens_separados,
    (
        select cast(
            coalesce(
                sum(
                    greatest(
                        i.qtde
                        - coalesce(i.qtde_romaneio, 0)
                        - coalesce(i.qtde_acerto, 0),
                        0
                    )
                ),
                0
            ) as double precision
        )
        from raw.car_itens_pedido i
        where i.empresa = s.empresa
          and i.pedido = s.pedido
          and coalesce(i.status_item, '') <> 'E'
    ) as saldo_metros
from public.wms_separacoes s
{onde}
{ordem}
{limite}
"""


def _separacao_por_id(conn: Any, separacao_id: int) -> dict[str, Any]:
    linha = conn.execute(
        text(SQL_SEPARACAO.format(onde="where s.id = :id", ordem="", limite="limit 1")),
        {"id": separacao_id},
    ).mappings().first()
    if linha is None:
        raise HTTPException(status_code=404, detail="Ordem de separação não encontrada")
    return _painel(linha)


def _travar_separacao(conn: Any, separacao_id: int) -> Any:
    linha = conn.execute(
        text("select * from public.wms_separacoes where id = :id for update"),
        {"id": separacao_id},
    ).mappings().first()
    if linha is None:
        raise HTTPException(status_code=404, detail="Ordem de separação não encontrada")
    return linha


def _item_do_pedido(conn: Any, empresa: str, pedido: str, item: int) -> Any:
    linha = conn.execute(
        text(
            """
            select *
            from raw.car_itens_pedido
            where empresa = :empresa and pedido = :pedido and item = :item
            """
        ),
        {"empresa": empresa, "pedido": pedido, "item": item},
    ).mappings().first()
    if linha is None:
        raise HTTPException(status_code=404, detail="Item do pedido não encontrado")
    return linha


def _filtros_pedido(
    *,
    busca: str,
    status_separacao: str,
) -> tuple[str, dict[str, Any]]:
    condicoes: list[str] = []
    params: dict[str, Any] = {}
    if busca:
        condicoes.append(
            "(p.pedido ilike :busca or p.cliente ilike :busca "
            "or c.razao_nome_cliente ilike :busca)"
        )
        params["busca"] = f"%{busca}%"
    if status_separacao:
        condicoes.append("coalesce(s.status, 'SEM_SEPARACAO') = :status_separacao")
        params["status_separacao"] = status_separacao
    return (" and " + " and ".join(condicoes) if condicoes else ""), params


SQL_PEDIDOS = """
select
    p.empresa,
    p.pedido,
    p.cliente                              as cliente_codigo,
    c.razao_nome_cliente                   as cliente_nome,
    to_char(p.data_pedido, 'YYYY-MM-DD')   as data_pedido,
    to_char(p.data_entrega, 'YYYY-MM-DD')  as data_entrega,
    p.status,
    p.status_ped,
    count(i.item)::int                     as total_itens,
    cast(
        coalesce(
            sum(
                greatest(
                    i.qtde
                    - coalesce(i.qtde_romaneio, 0)
                    - coalesce(i.qtde_acerto, 0),
                    0
                )
            ),
            0
        ) as double precision
    )                                      as saldo_metros,
    s.id                                   as separacao_id,
    s.status                               as separacao_status
from raw.car_pedido p
join raw.car_itens_pedido i
  on i.empresa = p.empresa and i.pedido = p.pedido
left join raw.clientes_principal c on c.codigo_cliente = p.cliente
left join lateral (
    select s2.id, s2.status
    from public.wms_separacoes s2
    where s2.empresa = p.empresa
      and s2.pedido = p.pedido
      and s2.status <> 'CANCELADO'
    order by s2.id desc
    limit 1
) s on true
where p.status = '2'
  and coalesce(p.status_ped, '') <> 'E'
  and coalesce(i.status_item, '') <> 'E'
  and (
      i.qtde - coalesce(i.qtde_romaneio, 0) - coalesce(i.qtde_acerto, 0)
  ) > 0
  {filtros}
group by
    p.empresa, p.pedido, p.cliente, c.razao_nome_cliente,
    p.data_pedido, p.data_entrega, p.status, p.status_ped,
    s.id, s.status
order by p.data_pedido desc, p.pedido desc
limit :limite offset :offset
"""

SQL_CONTAR_PEDIDOS = """
select count(*)::int
from (
    select p.empresa, p.pedido, s.id, s.status
    from raw.car_pedido p
    join raw.car_itens_pedido i
      on i.empresa = p.empresa and i.pedido = p.pedido
    left join raw.clientes_principal c on c.codigo_cliente = p.cliente
    left join lateral (
        select s2.id, s2.status
        from public.wms_separacoes s2
        where s2.empresa = p.empresa
          and s2.pedido = p.pedido
          and s2.status <> 'CANCELADO'
        order by s2.id desc
        limit 1
    ) s on true
    where p.status = '2'
      and coalesce(p.status_ped, '') <> 'E'
      and coalesce(i.status_item, '') <> 'E'
      and (
          i.qtde - coalesce(i.qtde_romaneio, 0) - coalesce(i.qtde_acerto, 0)
      ) > 0
      {filtros}
    group by p.empresa, p.pedido, s.id, s.status
) t
"""


@router.get("/wms/dashboard")
def dashboard(usuario: _dependente) -> dict[str, Any]:
    """Resumo do WMS: backlog, ordens por status, pecas reservadas e estoque em aberto."""
    with warehouse.engine().connect() as conn:
        pedidos = conn.execute(
            text(
                """
                select count(*)::int
                from (
                    select p.empresa, p.pedido
                    from raw.car_pedido p
                    join raw.car_itens_pedido i
                      on i.empresa = p.empresa and i.pedido = p.pedido
                    where p.status = '2'
                      and coalesce(p.status_ped, '') <> 'E'
                      and coalesce(i.status_item, '') <> 'E'
                      and (
                          i.qtde - coalesce(i.qtde_romaneio, 0) - coalesce(i.qtde_acerto, 0)
                      ) > 0
                    group by p.empresa, p.pedido
                ) t
                """
            )
        ).scalar_one()
        ordens = conn.execute(
            text(
                """
                select status, count(*)::int
                from public.wms_separacoes
                group by status
                """
            )
        ).all()
        pecas_reservadas = conn.execute(
            text(
                "select count(*)::int, cast(coalesce(sum(metros), 0) as double precision) "
                "from public.wms_separacao_pecas where status in ('RESERVADA', 'SEPARADA')"
            )
        ).one()
        em_aberto = conn.execute(
            text(f"select count(*)::int from raw.cte_peca a where {SQL_ABERTAS}")
        ).scalar_one()
        gavetas = conn.execute(text("select count(*)::int from raw.cte_gaveta")).scalar_one()

    por_status = {linha[0]: linha[1] for linha in ordens}
    return {
        "pedidosLiberados": pedidos,
        "separacoesLiberadas": por_status.get(STATUS_LIBERADO, 0),
        "separacoesEmAndamento": por_status.get(STATUS_EM_SEPARACAO, 0),
        "separacoesConcluidas": por_status.get(STATUS_SEPARADO, 0),
        "pecasReservadas": pecas_reservadas[0],
        "metrosReservados": float(pecas_reservadas[1] or 0),
        "pecasEmAberto": em_aberto,
        "gavetas": gavetas,
    }


@router.get("/wms/gavetas")
def listar_gavetas(
    usuario: _dependente,
    busca: str = Query("", description="Codigo, descricao ou zona"),
    zona: str = Query("", description="Codigo do grupo de gaveta"),
    limite: int = Query(200, ge=1, le=LIMITE_MAX),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Catalogo de gavetas do ERP (somente leitura), com a ocupacao em aberto."""
    condicoes: list[str] = []
    params: dict[str, Any] = {"limite": limite, "offset": offset}
    termo = busca.strip()
    if termo:
        condicoes.append(
            "(g.codigo ilike :busca or g.descricao ilike :busca "
            "or gg.descricao ilike :busca)"
        )
        params["busca"] = f"%{termo}%"
    if zona.strip():
        condicoes.append("g.grupo_gaveta = :zona")
        params["zona"] = zona.strip()
    filtro = " and " + " and ".join(condicoes) if condicoes else ""

    sql = f"""
        select
            g.codigo,
            g.descricao,
            g.grupo_gaveta,
            gg.descricao as zona,
            g.setor,
            g.faz_sugestao,
            g.estoque_plano,
            g.confirmar_transferencia,
            coalesce(o.pecas, 0)::int as pecas,
            cast(coalesce(o.metros, 0) as double precision) as metros
        from raw.cte_gaveta g
        left join raw.cte_grupo_gaveta gg on gg.codigo = g.grupo_gaveta
        left join (
            select a.gaveta, count(*)::int as pecas, sum(a.metros) as metros
            from raw.cte_peca a
            where {SQL_ABERTAS}
              and coalesce(a.gaveta, '') <> ''
            group by a.gaveta
        ) o on o.gaveta = g.codigo
        where true {filtro}
        order by g.grupo_gaveta nulls last, g.codigo
        limit :limite offset :offset
    """
    contar = f"""
        select count(*)::int
        from raw.cte_gaveta g
        left join raw.cte_grupo_gaveta gg on gg.codigo = g.grupo_gaveta
        where true {filtro}
    """
    with warehouse.engine().connect() as conn:
        itens = [_gaveta(linha) for linha in conn.execute(text(sql), params).mappings()]
        total = conn.execute(text(contar), params).scalar_one()
    return {"itens": itens, "total": total}


@router.get("/wms/pedidos")
def listar_pedidos(
    usuario: _dependente,
    busca: str = Query("", description="Pedido, cliente (codigo) ou razao social"),
    status_separacao: str = Query(
        "",
        alias="statusSeparacao",
        description="SEM_SEPARACAO, LIBERADO, EM_SEPARACAO, SEPARADO ou CANCELADO",
    ),
    limite: int = Query(50, ge=1, le=LIMITE_MAX),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Backlog: pedidos aprovados e abertos no ERP (status 2) com saldo a separar."""
    filtro, params = _filtros_pedido(
        busca=busca.strip(), status_separacao=status_separacao.strip().upper()
    )
    params.update({"limite": limite, "offset": offset})
    with warehouse.engine().connect() as conn:
        itens = [
            {
                "empresa": linha["empresa"],
                "pedido": linha["pedido"],
                "clienteCodigo": linha["cliente_codigo"],
                "clienteNome": linha["cliente_nome"],
                "dataPedido": linha["data_pedido"],
                "dataEntrega": linha["data_entrega"],
                "status": linha["status"],
                "totalItens": linha["total_itens"],
                "saldoMetros": _float0(linha["saldo_metros"]),
                "separacaoId": linha["separacao_id"],
                "separacaoStatus": linha["separacao_status"] or "SEM_SEPARACAO",
            }
            for linha in conn.execute(
                text(SQL_PEDIDOS.format(filtros=filtro)), params
            ).mappings()
        ]
        total = conn.execute(
            text(SQL_CONTAR_PEDIDOS.format(filtros=filtro)), params
        ).scalar_one()
    return {"itens": itens, "total": total}


def _itens_pedido(
    conn: Any, empresa: str, pedido: str, separacao_id: int | None = None
) -> list[dict[str, Any]]:
    if separacao_id is None:
        origem_reserva = """
            select sp.item, sum(sp.metros) as metros, count(*)::int as pecas
            from public.wms_separacao_pecas sp
            join public.wms_separacoes s2 on s2.id = sp.separacao_id
            where s2.empresa = :empresa
              and s2.pedido = :pedido
              and s2.status <> 'CANCELADO'
            group by sp.item
        """
        params: dict[str, Any] = {"empresa": empresa, "pedido": pedido}
    else:
        origem_reserva = """
            select sp.item, sum(sp.metros) as metros, count(*)::int as pecas
            from public.wms_separacao_pecas sp
            where sp.separacao_id = :separacao_id
            group by sp.item
        """
        params = {
            "empresa": empresa,
            "pedido": pedido,
            "separacao_id": separacao_id,
        }

    sql = f"""
        select
            i.item,
            i.produto,
            pr.descricao as produto_desc,
            i.situacao,
            si.descricao as situacao_desc,
            i.cor,
            co.descricao as cor_desc,
            i.desenho,
            de.descricao as desenho_desc,
            i.variante,
            va.descricao as variante_desc,
            i.categoria,
            ca.descricao as categoria_desc,
            i.largura,
            cast(coalesce(i.qtde, 0) as double precision) as qtde,
            cast(coalesce(i.qtde_romaneio, 0) as double precision) as qtde_romaneio,
            cast(coalesce(i.qtde_acerto, 0) as double precision) as qtde_acerto,
            cast(
                greatest(
                    i.qtde
                    - coalesce(i.qtde_romaneio, 0)
                    - coalesce(i.qtde_acerto, 0),
                    0
                ) as double precision
            ) as saldo,
            i.unid,
            cast(coalesce(r.metros, 0) as double precision) as reservado_metros,
            coalesce(r.pecas, 0)::int as pecas_reservadas
        from raw.car_itens_pedido i
        left join raw.produtos pr on pr.codigo = i.produto
        left join raw.car_situacoes si on si.codigo = i.situacao
        left join raw.car_cores co on co.codigo = i.cor
        left join raw.car_desenhos de on de.codigo = i.desenho
        left join raw.car_variante va on va.codigo = i.variante
        left join raw.car_categorias ca on ca.codigo = i.categoria
        left join ({origem_reserva}) r on r.item = i.item
        where i.empresa = :empresa
          and i.pedido = :pedido
          and coalesce(i.status_item, '') <> 'E'
        order by i.item
    """
    return [
        {
            "item": linha["item"],
            "produto": linha["produto"],
            "produtoDesc": linha["produto_desc"],
            "situacao": linha["situacao"],
            "situacaoDesc": linha["situacao_desc"],
            "cor": linha["cor"],
            "corDesc": linha["cor_desc"],
            "desenho": linha["desenho"],
            "desenhoDesc": linha["desenho_desc"],
            "variante": linha["variante"],
            "varianteDesc": linha["variante_desc"],
            "categoria": linha["categoria"],
            "categoriaDesc": linha["categoria_desc"],
            "largura": linha["largura"],
            "qtde": _float0(linha["qtde"]),
            "qtdeRomaneio": _float0(linha["qtde_romaneio"]),
            "qtdeAcerto": _float0(linha["qtde_acerto"]),
            "saldo": _float0(linha["saldo"]),
            "unid": linha["unid"],
            "reservadoMetros": _float0(linha["reservado_metros"]),
            "pecasReservadas": linha["pecas_reservadas"],
        }
        for linha in conn.execute(text(sql), params).mappings()
    ]


def _pedido(conn: Any, empresa: str, pedido: str) -> dict[str, Any]:
    linha = conn.execute(
        text(
            """
            select
                p.empresa,
                p.pedido,
                p.cliente as cliente_codigo,
                c.razao_nome_cliente as cliente_nome,
                to_char(p.data_pedido, 'YYYY-MM-DD') as data_pedido,
                to_char(p.data_entrega, 'YYYY-MM-DD') as data_entrega,
                p.status,
                p.status_ped
            from raw.car_pedido p
            left join raw.clientes_principal c on c.codigo_cliente = p.cliente
            where p.empresa = :empresa and p.pedido = :pedido
            """
        ),
        {"empresa": empresa, "pedido": pedido},
    ).mappings().first()
    if linha is None:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    separacao = conn.execute(
        text(
            """
            select id, status
            from public.wms_separacoes
            where empresa = :empresa and pedido = :pedido and status <> 'CANCELADO'
            order by id desc
            limit 1
            """
        ),
        {"empresa": empresa, "pedido": pedido},
    ).mappings().first()
    return {
        "empresa": linha["empresa"],
        "pedido": linha["pedido"],
        "clienteCodigo": linha["cliente_codigo"],
        "clienteNome": linha["cliente_nome"],
        "dataPedido": linha["data_pedido"],
        "dataEntrega": linha["data_entrega"],
        "status": linha["status"],
        "statusPed": linha["status_ped"],
        "separacaoId": separacao["id"] if separacao else None,
        "separacaoStatus": separacao["status"] if separacao else "SEM_SEPARACAO",
        "itens": _itens_pedido(conn, empresa, pedido),
    }


@router.get("/wms/pedidos/{empresa}/{pedido}")
def detalhe_pedido(empresa: str, pedido: str, usuario: _dependente) -> dict[str, Any]:
    """Pedido com itens, saldo e o que ja esta reservado/separado no WMS."""
    with warehouse.engine().connect() as conn:
        return _pedido(conn, empresa, pedido)


@router.get("/wms/separacoes")
def listar_separacoes(
    usuario: _dependente,
    status_filtro: str = Query("", alias="status", description="Status da ordem"),
    busca: str = Query("", description="Pedido, cliente (codigo) ou razao social"),
    limite: int = Query(50, ge=1, le=LIMITE_MAX),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Ordens de separacao (kanban/lista)."""
    condicoes: list[str] = []
    params: dict[str, Any] = {"limite": limite, "offset": offset}
    if status_filtro.strip():
        condicoes.append("s.status = :status")
        params["status"] = status_filtro.strip().upper()
    termo = busca.strip()
    if termo:
        condicoes.append(
            "(s.pedido ilike :busca or s.cliente_codigo ilike :busca "
            "or s.cliente_nome ilike :busca)"
        )
        params["busca"] = f"%{termo}%"
    onde = "where " + " and ".join(condicoes) if condicoes else ""

    with warehouse.engine().connect() as conn:
        itens = [
            _painel(linha)
            for linha in conn.execute(
                text(
                    SQL_SEPARACAO.format(
                        onde=onde,
                        ordem="order by s.criado_em desc, s.id desc",
                        limite="limit :limite offset :offset",
                    )
                ),
                params,
            ).mappings()
        ]
        total = conn.execute(
            text(f"select count(*)::int from public.wms_separacoes s {onde}"), params
        ).scalar_one()
    return {"itens": itens, "total": total}


@router.post("/wms/separacoes", status_code=status.HTTP_201_CREATED)
def criar_separacao(dados: NovaSeparacao, usuario: _dependente) -> dict[str, Any]:
    """Comercial marca um pedido do backlog para separacao (grava somente no banco local)."""
    empresa = _texto(dados.empresa)
    pedido = _texto(dados.pedido)
    if empresa is None or pedido is None:
        raise HTTPException(status_code=400, detail="Empresa e pedido são obrigatórios")

    with warehouse.engine().begin() as conn:
        cabecalho = conn.execute(
            text(
                """
                select
                    p.empresa,
                    p.pedido,
                    p.cliente,
                    c.razao_nome_cliente,
                    to_char(p.data_pedido, 'YYYY-MM-DD') as data_pedido,
                    to_char(p.data_entrega, 'YYYY-MM-DD') as data_entrega
                from raw.car_pedido p
                left join raw.clientes_principal c on c.codigo_cliente = p.cliente
                where p.empresa = :empresa
                  and p.pedido = :pedido
                  and p.status = '2'
                  and coalesce(p.status_ped, '') <> 'E'
                """
            ),
            {"empresa": empresa, "pedido": pedido},
        ).mappings().first()
        if cabecalho is None:
            raise HTTPException(
                status_code=400,
                detail="Pedido não está liberado (aprovado e aberto) no ERP",
            )

        saldo = conn.execute(
            text(
                """
                select cast(
                    coalesce(
                        sum(
                            greatest(
                                i.qtde
                                - coalesce(i.qtde_romaneio, 0)
                                - coalesce(i.qtde_acerto, 0),
                                0
                            )
                        ),
                        0
                    ) as double precision
                )
                from raw.car_itens_pedido i
                where i.empresa = :empresa
                  and i.pedido = :pedido
                  and coalesce(i.status_item, '') <> 'E'
                """
            ),
            {"empresa": empresa, "pedido": pedido},
        ).scalar_one()
        if float(saldo or 0) <= 0:
            raise HTTPException(status_code=400, detail="Pedido não tem saldo a separar")

        existente = conn.execute(
            text(
                """
                select id
                from public.wms_separacoes
                where empresa = :empresa
                  and pedido = :pedido
                  and status in ('LIBERADO', 'EM_SEPARACAO')
                limit 1
                """
            ),
            {"empresa": empresa, "pedido": pedido},
        ).first()
        if existente is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este pedido já tem uma ordem de separação ativa",
            )

        nova = conn.execute(
            text(
                """
                insert into public.wms_separacoes (
                    empresa, pedido, status, cliente_codigo, cliente_nome,
                    data_pedido, data_entrega, observacao, criado_por,
                    iniciado_por, concluido_por, cancelado_por
                ) values (
                    :empresa, :pedido, 'LIBERADO', :cliente_codigo, :cliente_nome,
                    :data_pedido, :data_entrega, :observacao, :criado_por,
                    null, null, null
                )
                returning id
                """
            ),
            {
                "empresa": empresa,
                "pedido": pedido,
                "cliente_codigo": cabecalho["cliente"],
                "cliente_nome": cabecalho["razao_nome_cliente"],
                "data_pedido": cabecalho["data_pedido"],
                "data_entrega": cabecalho["data_entrega"],
                "observacao": _texto(dados.observacao),
                "criado_por": dados.usuario_id,
            },
        ).scalar_one()
        _evento(
            conn,
            nova,
            "LIBERADO",
            descricao="Pedido marcado para separação",
            usuario_id=dados.usuario_id,
        )
        return _separacao_por_id(conn, nova)


@router.get("/wms/separacoes/{separacao_id}")
def detalhe_separacao(separacao_id: int, usuario: _dependente) -> dict[str, Any]:
    """Ordem com itens do pedido, pecas reservadas/separadas e totais."""
    with warehouse.engine().connect() as conn:
        cabecalho = conn.execute(
            text("select * from public.wms_separacoes where id = :id"),
            {"id": separacao_id},
        ).mappings().first()
        if cabecalho is None:
            raise HTTPException(status_code=404, detail="Ordem de separação não encontrada")
        ordem = _separacao_por_id(conn, separacao_id)
        ordem["itens"] = _itens_pedido(
            conn, cabecalho["empresa"], cabecalho["pedido"], separacao_id
        )
        ordem["pecas"] = [
            _peca(linha)
            for linha in conn.execute(
                text(
                    """
                    select
                        sp.*,
                        pr.descricao as produto_desc,
                        co.descricao as cor_desc,
                        g.descricao as gaveta_descricao,
                        gg.descricao as zona,
                        exists (
                            select 1
                            from raw.cte_baixa b
                            where b.empresa = sp.empresa
                              and b.nro_rolo = sp.nro_rolo
                              and b.nro_peca = sp.nro_peca
                        ) as baixado_no_erp
                    from public.wms_separacao_pecas sp
                    left join raw.produtos pr on pr.codigo = sp.produto
                    left join raw.car_cores co on co.codigo = sp.cor
                    left join raw.cte_gaveta g on g.codigo = sp.gaveta
                    left join raw.cte_grupo_gaveta gg on gg.codigo = g.grupo_gaveta
                    where sp.separacao_id = :id
                    order by sp.item, sp.gaveta nulls last, sp.nro_rolo
                    """
                ),
                {"id": separacao_id},
            ).mappings()
        ]
        return ordem


@router.post("/wms/separacoes/{separacao_id}/iniciar")
def iniciar_separacao(
    separacao_id: int, dados: Acao | None = None, usuario: _dependente = None
) -> dict[str, Any]:
    """Move a ordem de LIBERADO para EM_SEPARACAO (idempotente)."""
    dados = dados or Acao()
    with warehouse.engine().begin() as conn:
        atual = _travar_separacao(conn, separacao_id)
        if atual["status"] == STATUS_CANCELADO:
            raise HTTPException(status_code=409, detail="Ordem de separação cancelada")
        if atual["status"] == STATUS_SEPARADO:
            raise HTTPException(status_code=409, detail="Ordem de separação já concluída")
        if atual["status"] == STATUS_LIBERADO:
            conn.execute(
                text(
                    """
                    update public.wms_separacoes
                    set status = 'EM_SEPARACAO',
                        iniciado_por = coalesce(iniciado_por, :usuario_id),
                        iniciado_em = coalesce(iniciado_em, now()),
                        atualizado_em = now()
                    where id = :id
                    """
                ),
                {"id": separacao_id, "usuario_id": dados.usuario_id},
            )
            _evento(
                conn,
                separacao_id,
                "INICIADA",
                descricao=_texto(dados.observacao),
                usuario_id=dados.usuario_id,
            )
        return _separacao_por_id(conn, separacao_id)


@router.post("/wms/separacoes/{separacao_id}/concluir")
def concluir_separacao(
    separacao_id: int, dados: Acao | None = None, usuario: _dependente = None
) -> dict[str, Any]:
    """Conclui a separacao; as pecas continuam bloqueadas ate a baixa no ERP."""
    dados = dados or Acao()
    with warehouse.engine().begin() as conn:
        atual = _travar_separacao(conn, separacao_id)
        if atual["status"] == STATUS_CANCELADO:
            raise HTTPException(status_code=409, detail="Ordem de separação cancelada")
        if atual["status"] == STATUS_SEPARADO:
            return _separacao_por_id(conn, separacao_id)

        pecas = conn.execute(
            text(
                "select count(*)::int from public.wms_separacao_pecas "
                "where separacao_id = :id"
            ),
            {"id": separacao_id},
        ).scalar_one()
        if pecas == 0:
            raise HTTPException(
                status_code=400, detail="Selecione ao menos uma peça antes de concluir"
            )

        conn.execute(
            text(
                """
                update public.wms_separacao_pecas
                set status = 'SEPARADA', updated_at = now()
                where separacao_id = :id
                """
            ),
            {"id": separacao_id},
        )
        conn.execute(
            text(
                """
                update public.wms_separacoes
                set status = 'SEPARADO',
                    iniciado_por = coalesce(iniciado_por, :usuario_id),
                    iniciado_em = coalesce(iniciado_em, now()),
                    concluido_por = :usuario_id,
                    concluido_em = now(),
                    atualizado_em = now()
                where id = :id
                """
            ),
            {"id": separacao_id, "usuario_id": dados.usuario_id},
        )
        _evento(
            conn,
            separacao_id,
            "CONCLUIDA",
            descricao=_texto(dados.observacao),
            usuario_id=dados.usuario_id,
            payload={"pecas": pecas},
        )
        return _separacao_por_id(conn, separacao_id)


@router.post("/wms/separacoes/{separacao_id}/cancelar")
def cancelar_separacao(
    separacao_id: int, dados: Cancelamento | None = None, usuario: _dependente = None
) -> dict[str, Any]:
    """Cancela a ordem e libera as pecas para outra separacao."""
    dados = dados or Cancelamento()
    with warehouse.engine().begin() as conn:
        atual = _travar_separacao(conn, separacao_id)
        if atual["status"] == STATUS_CANCELADO:
            return _separacao_por_id(conn, separacao_id)

        pecas = conn.execute(
            text(
                "delete from public.wms_separacao_pecas where separacao_id = :id "
                "returning id"
            ),
            {"id": separacao_id},
        ).all()
        conn.execute(
            text(
                """
                update public.wms_separacoes
                set status = 'CANCELADO',
                    motivo_cancelamento = :motivo,
                    cancelado_por = :usuario_id,
                    cancelado_em = now(),
                    atualizado_em = now()
                where id = :id
                """
            ),
            {
                "id": separacao_id,
                "motivo": _texto(dados.motivo) or _texto(dados.observacao),
                "usuario_id": dados.usuario_id,
            },
        )
        _evento(
            conn,
            separacao_id,
            "CANCELADA",
            descricao=_texto(dados.motivo) or _texto(dados.observacao),
            usuario_id=dados.usuario_id,
            payload={"pecasLiberadas": len(pecas)},
        )
        return _separacao_por_id(conn, separacao_id)


def _condicoes_estoque(
    *,
    busca: str,
    gaveta: str,
    sub_lote: str,
    aviso: str,
    cor: str,
    produto: str,
) -> tuple[str, dict[str, Any]]:
    condicoes: list[str] = []
    params: dict[str, Any] = {}
    if busca:
        condicoes.append(
            "(a.nro_rolo ilike :busca or a.nro_peca ilike :busca "
            "or a.produto ilike :busca or a.cor ilike :busca)"
        )
        params["busca"] = f"%{busca}%"
    for valor, coluna in (
        (gaveta, "a.gaveta"),
        (sub_lote, "a.sub_lote"),
        (aviso, "a.aviso"),
        (cor, "a.cor"),
        (produto, "a.produto"),
    ):
        if valor:
            nome = f"f_{coluna.split('.')[-1]}"
            condicoes.append(f"{coluna} = :{nome}")
            params[nome] = valor
    return (" and " + " and ".join(condicoes) if condicoes else ""), params


SQL_DISPONIVEIS = """
select
    a.empresa,
    a.nro_rolo,
    a.nro_peca,
    a.produto,
    pr.descricao as produto_desc,
    a.situacao,
    si.descricao as situacao_desc,
    a.cor,
    co.descricao as cor_desc,
    a.desenho,
    de.descricao as desenho_desc,
    a.variante,
    va.descricao as variante_desc,
    a.categoria,
    ca.descricao as categoria_desc,
    a.largura,
    a.sub_lote,
    a.aviso,
    a.gaveta,
    g.descricao as gaveta_descricao,
    gg.descricao as zona,
    cast(a.metros as double precision) as metros,
    cast(a.peso as double precision) as peso,
    to_char(a.data_entrada, 'YYYY-MM-DD') as data_entrada
from raw.cte_peca a
left join raw.produtos pr on pr.codigo = a.produto
left join raw.car_situacoes si on si.codigo = a.situacao
left join raw.car_cores co on co.codigo = a.cor
left join raw.car_desenhos de on de.codigo = a.desenho
left join raw.car_variante va on va.codigo = a.variante
left join raw.car_categorias ca on ca.codigo = a.categoria
left join raw.cte_gaveta g on g.codigo = a.gaveta
left join raw.cte_grupo_gaveta gg on gg.codigo = g.grupo_gaveta
where {abertas}
  and {reservadas}
  {filtros}
"""


def _disponiveis(
    conn: Any,
    *,
    filtros: str,
    params: dict[str, Any],
    limite: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    sql = SQL_DISPONIVEIS.format(abertas=SQL_ABERTAS, reservadas=SQL_RESERVADAS, filtros=filtros)
    sql += (
        " order by a.gaveta nulls last, a.sub_lote, a.nro_rolo, a.nro_peca"
        " limit :limite offset :offset"
    )
    contar = f"""
        select count(*)::int
        from raw.cte_peca a
        where {SQL_ABERTAS}
          and {SQL_RESERVADAS}
          {filtros}
    """
    consulta_params = {**params, "limite": limite, "offset": offset}
    itens = [
        {
            "empresa": linha["empresa"],
            "nro_rolo": linha["nro_rolo"],
            "nro_peca": linha["nro_peca"],
            "produto": linha["produto"],
            "produto_desc": linha["produto_desc"],
            "situacao": linha["situacao"],
            "situacao_desc": linha["situacao_desc"],
            "cor": linha["cor"],
            "cor_desc": linha["cor_desc"],
            "desenho": linha["desenho"],
            "desenho_desc": linha["desenho_desc"],
            "variante": linha["variante"],
            "variante_desc": linha["variante_desc"],
            "categoria": linha["categoria"],
            "categoria_desc": linha["categoria_desc"],
            "largura": linha["largura"],
            "sub_lote": linha["sub_lote"],
            "aviso": linha["aviso"],
            "gaveta": linha["gaveta"],
            "gaveta_descricao": linha["gaveta_descricao"],
            "zona": linha["zona"],
            "metros": _float(linha["metros"]),
            "peso": _float(linha["peso"]),
            "data_entrada": linha["data_entrada"],
        }
        for linha in conn.execute(text(sql), consulta_params).mappings()
    ]
    total = conn.execute(text(contar), params).scalar_one()
    return itens, total


@router.get("/wms/estoque")
def listar_estoque(
    usuario: _dependente,
    busca: str = Query("", description="Rolo, peca, produto ou cor"),
    gaveta: str = Query("", description="Codigo da gaveta (endereco)"),
    sub_lote: str = Query("", alias="subLote", description="Sublote"),
    aviso: str = Query("", description="Aviso"),
    cor: str = Query("", description="Cor"),
    produto: str = Query("", description="Produto"),
    limite: int = Query(50, ge=1, le=LIMITE_MAX),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Consulta do estoque em aberto, sem as pecas reservadas/separadas."""
    filtros, params = _condicoes_estoque(
        busca=busca.strip(),
        gaveta=gaveta.strip(),
        sub_lote=sub_lote.strip(),
        aviso=aviso.strip(),
        cor=cor.strip(),
        produto=produto.strip(),
    )
    with warehouse.engine().connect() as conn:
        itens, total = _disponiveis(
            conn, filtros=filtros, params=params, limite=limite, offset=offset
        )
    return {"itens": itens, "total": total}


@router.get("/wms/separacoes/{separacao_id}/itens/{item}/pecas")
def pecas_do_item(
    separacao_id: int,
    item: int,
    usuario: _dependente,
    busca: str = Query("", description="Rolo ou peca"),
    gaveta: str = Query("", description="Codigo da gaveta (endereco)"),
    sub_lote: str = Query("", alias="subLote", description="Sublote"),
    aviso: str = Query("", description="Aviso"),
    limite: int = Query(50, ge=1, le=LIMITE_MAX),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Pecas em aberto compativeis com a grade do item, excluindo as ja reservadas."""
    with warehouse.engine().connect() as conn:
        cabecalho = conn.execute(
            text("select empresa, pedido from public.wms_separacoes where id = :id"),
            {"id": separacao_id},
        ).mappings().first()
        if cabecalho is None:
            raise HTTPException(status_code=404, detail="Ordem de separação não encontrada")
        item_pedido = _item_do_pedido(conn, cabecalho["empresa"], cabecalho["pedido"], item)

        filtros, params = _condicoes_estoque(
            busca=busca.strip(),
            gaveta=gaveta.strip(),
            sub_lote=sub_lote.strip(),
            aviso=aviso.strip(),
            cor="",
            produto="",
        )
        for coluna in ("produto", "situacao", "cor", "desenho", "variante", "categoria"):
            valor = item_pedido[coluna]
            if valor is None:
                filtros += f" and a.{coluna} is null"
            else:
                filtros += f" and a.{coluna} = :item_{coluna}"
                params[f"item_{coluna}"] = valor
        params["limite"] = limite
        params["offset"] = offset

        itens, total = _disponiveis(
            conn, filtros=filtros, params=params, limite=limite, offset=offset
        )
    return {
        "itens": itens,
        "total": total,
        "item": {
            "item": item_pedido["item"],
            "produto": item_pedido["produto"],
            "situacao": item_pedido["situacao"],
            "cor": item_pedido["cor"],
            "desenho": item_pedido["desenho"],
            "variante": item_pedido["variante"],
            "categoria": item_pedido["categoria"],
        },
    }


@router.post("/wms/separacoes/{separacao_id}/pecas", status_code=status.HTTP_201_CREATED)
def adicionar_pecas(
    separacao_id: int, dados: AdicionarPecas, usuario: _dependente
) -> dict[str, Any]:
    """Reserva pecas para o item. A ordem e iniciada automaticamente se necessario."""
    with warehouse.engine().begin() as conn:
        atual = _travar_separacao(conn, separacao_id)
        if atual["status"] in (STATUS_CANCELADO, STATUS_SEPARADO):
            raise HTTPException(
                status_code=409, detail="Ordem de separação não aceita novas peças"
            )
        item_pedido = _item_do_pedido(
            conn, atual["empresa"], atual["pedido"], dados.item
        )

        adicionadas: list[int] = []
        try:
            for referencia in dados.pecas:
                rolo = _texto(referencia.nro_rolo)
                peca = _texto(referencia.nro_peca)
                if rolo is None or peca is None:
                    raise HTTPException(
                        status_code=400, detail="Nro. Rolo e Nro. Peça são obrigatórios"
                    )

                linha = conn.execute(
                    text(
                        f"""
                        select
                            a.empresa, a.nro_rolo, a.nro_peca, a.produto, a.situacao,
                            a.cor, a.desenho, a.variante, a.categoria, a.largura,
                            a.sub_lote, a.aviso, a.gaveta, a.metros, a.peso
                        from raw.cte_peca a
                        where a.empresa = :empresa
                          and a.nro_rolo = :nro_rolo
                          and a.nro_peca = :nro_peca
                          and {SQL_ABERTAS}
                          and {SQL_RESERVADAS}
                          and a.produto = :produto
                          and a.situacao = :situacao
                          and a.cor = :cor
                          and a.desenho = :desenho
                          and a.variante = :variante
                          and a.categoria = :categoria
                        limit 1
                        """
                    ),
                    {
                        "empresa": atual["empresa"],
                        "nro_rolo": rolo,
                        "nro_peca": peca,
                        "produto": item_pedido["produto"],
                        "situacao": item_pedido["situacao"],
                        "cor": item_pedido["cor"],
                        "desenho": item_pedido["desenho"],
                        "variante": item_pedido["variante"],
                        "categoria": item_pedido["categoria"],
                    },
                ).mappings().first()
                if linha is None:
                    reservada = conn.execute(
                        text(
                            "select 1 from public.wms_separacao_pecas "
                            "where empresa = :empresa and nro_rolo = :nro_rolo "
                            "and nro_peca = :nro_peca "
                            "and status in ('RESERVADA', 'SEPARADA') limit 1"
                        ),
                        {
                            "empresa": atual["empresa"],
                            "nro_rolo": rolo,
                            "nro_peca": peca,
                        },
                    ).first()
                    if reservada is not None:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=f"Peça {rolo}/{peca} já está reservada em outra ordem",
                        )
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Peça {rolo}/{peca} indisponível, já reservada ou "
                            "incompatível com o item"
                        ),
                    )

                nova = conn.execute(
                    text(
                        """
                        insert into public.wms_separacao_pecas (
                            separacao_id, item, empresa, nro_rolo, nro_peca,
                            produto, situacao, cor, desenho, variante, categoria,
                            largura, sub_lote, aviso, gaveta, metros, peso,
                            status, adicionado_por
                        ) values (
                            :separacao_id, :item, :empresa, :nro_rolo, :nro_peca,
                            :produto, :situacao, :cor, :desenho, :variante, :categoria,
                            :largura, :sub_lote, :aviso, :gaveta, :metros, :peso,
                            'RESERVADA', :usuario_id
                        )
                        returning id
                        """
                    ),
                    {
                        "separacao_id": separacao_id,
                        "item": dados.item,
                        "empresa": linha["empresa"],
                        "nro_rolo": linha["nro_rolo"],
                        "nro_peca": linha["nro_peca"],
                        "produto": linha["produto"],
                        "situacao": linha["situacao"],
                        "cor": linha["cor"],
                        "desenho": linha["desenho"],
                        "variante": linha["variante"],
                        "categoria": linha["categoria"],
                        "largura": _texto(linha["largura"]),
                        "sub_lote": _texto(linha["sub_lote"]),
                        "aviso": _texto(linha["aviso"]),
                        "gaveta": _texto(linha["gaveta"]),
                        "metros": linha["metros"],
                        "peso": linha["peso"],
                        "usuario_id": dados.usuario_id,
                    },
                ).scalar_one()
                adicionadas.append(nova)
        except IntegrityError as erro:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Uma das peças já está reservada em outra ordem",
            ) from erro

        if atual["status"] == STATUS_LIBERADO:
            conn.execute(
                text(
                    """
                    update public.wms_separacoes
                    set status = 'EM_SEPARACAO',
                        iniciado_por = coalesce(iniciado_por, :usuario_id),
                        iniciado_em = coalesce(iniciado_em, now()),
                        atualizado_em = now()
                    where id = :id
                    """
                ),
                {"id": separacao_id, "usuario_id": dados.usuario_id},
            )
        _evento(
            conn,
            separacao_id,
            "PECAS_ADICIONADAS",
            usuario_id=dados.usuario_id,
            payload={"item": dados.item, "pecas": adicionadas},
        )
        return {
            "separacao": _separacao_por_id(conn, separacao_id),
            "adicionadas": len(adicionadas),
        }


@router.delete("/wms/separacoes/{separacao_id}/pecas/{peca_id}")
def remover_peca(
    separacao_id: int,
    peca_id: int,
    usuario: _dependente,
    usuario_id: int | None = Query(None, alias="usuarioId"),
) -> dict[str, Any]:
    """Remove uma peca da ordem (somente enquanto ela esta em separacao)."""
    with warehouse.engine().begin() as conn:
        atual = _travar_separacao(conn, separacao_id)
        if atual["status"] != STATUS_EM_SEPARACAO:
            raise HTTPException(
                status_code=409, detail="Só é possível remover peças em separação"
            )
        removida = conn.execute(
            text(
                "delete from public.wms_separacao_pecas "
                "where id = :id and separacao_id = :separacao_id returning nro_rolo, nro_peca"
            ),
            {"id": peca_id, "separacao_id": separacao_id},
        ).mappings().first()
        if removida is None:
            raise HTTPException(status_code=404, detail="Peça da ordem não encontrada")
        _evento(
            conn,
            separacao_id,
            "PECA_REMOVIDA",
            usuario_id=usuario_id,
            payload={"nroRolo": removida["nro_rolo"], "nroPeca": removida["nro_peca"]},
        )
        return {
            "separacao": _separacao_por_id(conn, separacao_id),
            "removida": {"nroRolo": removida["nro_rolo"], "nroPeca": removida["nro_peca"]},
        }


__all__ = ["router"]
