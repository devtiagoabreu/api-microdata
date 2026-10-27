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
import re
import unicodedata
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

ACAO_NENHUMA = "NENHUMA"
ACAO_CRIAR = "CRIAR_ORDEM"
ACAO_CONCLUIR = "CONCLUIR_ORDEM"
ACAO_CANCELAR = "CANCELAR_ORDEM"
ACOES_SITUACAO = (ACAO_NENHUMA, ACAO_CRIAR, ACAO_CONCLUIR, ACAO_CANCELAR)
CAMPOS_BUSCA_PECA = {
    "lote": "sub_lote",
    "sublote": "sub_lote",
    "sub_lote": "sub_lote",
    "aviso": "aviso",
    "gaveta": "gaveta",
    "endereco": "gaveta",
}
COR_PADRAO = "#94a3b8"

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


class Reabertura(Acao):
    status: str = STATUS_LIBERADO


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


class MoverSituacao(Modelo):
    situacao_id: int
    usuario_id: int | None = None
    observacao: str | None = None
    cancelar_ordem: bool = False


class NovaSituacao(Modelo):
    codigo: str | None = None
    nome: str
    cor: str = COR_PADRAO
    ordem: int = 0
    acao: str = ACAO_NENHUMA
    perfis: list[str] = Field(default_factory=list)
    ativo: bool = True


class EdicaoSituacao(Modelo):
    nome: str | None = None
    cor: str | None = None
    ordem: int | None = None
    acao: str | None = None
    perfis: list[str] | None = None
    ativo: bool | None = None


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
        "arquivadaEm": _data(linha["arquivada_em"]),
        "arquivadaPor": linha["arquivada_por"],
        "totalPecas": linha["total_pecas"],
        "totalMetros": _float0(linha["total_metros"]),
        "itensSeparados": linha["itens_separados"],
        "saldoMetros": _float0(linha["saldo_metros"]),
        "artigos": linha["artigos"],
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


def _slug(valor: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", valor).encode("ascii", "ignore").decode()
    limpo = re.sub(r"[^A-Za-z0-9]+", "_", sem_acento).strip("_")
    return limpo.upper()


def _situacao(linha: Any) -> dict[str, Any]:
    return {
        "id": linha["id"],
        "codigo": linha["codigo"],
        "nome": linha["nome"],
        "cor": linha["cor"],
        "ordem": linha["ordem"],
        "acao": linha["acao"],
        "perfis": list(linha["perfis"] or []),
        "ativo": bool(linha["ativo"]),
        "sistema": bool(linha["sistema"]),
        "pedidos": linha["pedidos"] if "pedidos" in linha else None,
        "criadoEm": _data(linha["criado_em"]),
        "atualizadoEm": _data(linha["atualizado_em"]),
    }


def _situacao_por_id(conn: Any, situacao_id: int) -> Any:
    linha = conn.execute(
        text(
            """
            select
                s.*,
                (
                    select count(*)::int
                    from public.wms_pedidos_situacao ps
                    where ps.situacao_id = s.id
                ) as pedidos
            from public.wms_situacoes_pedido s
            where s.id = :id
            """
        ),
        {"id": situacao_id},
    ).mappings().first()
    if linha is None:
        raise HTTPException(status_code=404, detail="Situação do pedido não encontrada")
    return linha


def _situacao_por_codigo(conn: Any, codigo: str) -> Any:
    return conn.execute(
        text("select * from public.wms_situacoes_pedido where codigo = :codigo"),
        {"codigo": codigo},
    ).mappings().first()


def _situacao_atual(conn: Any, empresa: str, pedido: str) -> Any:
    return conn.execute(
        text(
            """
            select
                s.*,
                ps.atualizado_por,
                ps.atualizado_em
            from public.wms_pedidos_situacao ps
            join public.wms_situacoes_pedido s on s.id = ps.situacao_id
            where ps.empresa = :empresa and ps.pedido = :pedido
            """
        ),
        {"empresa": empresa, "pedido": pedido},
    ).mappings().first()


def _definir_situacao(
    conn: Any,
    empresa: str,
    pedido: str,
    codigo: str,
    *,
    usuario_id: int | None = None,
    observacao: str | None = None,
) -> dict[str, Any] | None:
    """Sincroniza a situacao local do pedido (kanban) com o codigo pedido."""
    nova = _situacao_por_codigo(conn, codigo)
    if nova is None:
        return None
    atual = _situacao_atual(conn, empresa, pedido)
    anterior_id = atual["id"] if atual is not None else None
    if anterior_id == nova["id"]:
        return _situacao(nova)
    conn.execute(
        text(
            """
            insert into public.wms_pedidos_situacao
                (empresa, pedido, situacao_id, atualizado_por, atualizado_em)
            values
                (:empresa, :pedido, :situacao_id, :usuario_id, now())
            on conflict (empresa, pedido) do update
                set situacao_id = excluded.situacao_id,
                    atualizado_por = excluded.atualizado_por,
                    atualizado_em = now()
            """
        ),
        {
            "empresa": empresa,
            "pedido": pedido,
            "situacao_id": nova["id"],
            "usuario_id": usuario_id,
        },
    )
    conn.execute(
        text(
            """
            insert into public.wms_pedido_eventos
                (empresa, pedido, situacao_anterior_id, situacao_nova_id,
                 usuario_id, observacao)
            values
                (:empresa, :pedido, :anterior_id, :nova_id, :usuario_id, :observacao)
            """
        ),
        {
            "empresa": empresa,
            "pedido": pedido,
            "anterior_id": anterior_id,
            "nova_id": nova["id"],
            "usuario_id": usuario_id,
            "observacao": _texto(observacao),
        },
    )
    return _situacao(nova)


def _pedido_erp(conn: Any, empresa: str, pedido: str) -> Any:
    return conn.execute(
        text(
            """
            select
                p.empresa,
                p.pedido,
                p.cliente,
                c.razao_nome_cliente,
                to_char(p.data_pedido, 'YYYY-MM-DD') as data_pedido,
                to_char(p.data_entrega, 'YYYY-MM-DD') as data_entrega,
                p.status,
                p.status_ped,
                cast(
                    coalesce(
                        (
                            select sum(
                                greatest(
                                    i.qtde
                                    - coalesce(i.qtde_romaneio, 0)
                                    - coalesce(i.qtde_acerto, 0),
                                    0
                                )
                            )
                            from raw.car_itens_pedido i
                            where i.empresa = p.empresa
                              and i.pedido = p.pedido
                              and coalesce(i.status_item, '') <> 'E'
                        ),
                        0
                    ) as double precision
                ) as saldo
            from raw.car_pedido p
            left join raw.clientes_principal c on c.codigo_cliente = p.cliente
            where p.empresa = :empresa and p.pedido = :pedido
            """
        ),
        {"empresa": empresa, "pedido": pedido},
    ).mappings().first()


def _ordem_ativa(conn: Any, empresa: str, pedido: str) -> Any:
    return conn.execute(
        text(
            """
            select *
            from public.wms_separacoes
            where empresa = :empresa
              and pedido = :pedido
              and status in ('LIBERADO', 'EM_SEPARACAO')
            order by id desc
            limit 1
            """
        ),
        {"empresa": empresa, "pedido": pedido},
    ).mappings().first()


def _criar_ordem(
    conn: Any,
    cabecalho: Any,
    *,
    status_ordem: str,
    usuario_id: int | None,
    observacao: str | None = None,
) -> int:
    return conn.execute(
        text(
            """
            insert into public.wms_separacoes (
                empresa, pedido, status, cliente_codigo, cliente_nome,
                data_pedido, data_entrega, observacao, criado_por,
                iniciado_por, iniciado_em, concluido_por, cancelado_por
            ) values (
                :empresa, :pedido, :status, :cliente_codigo, :cliente_nome,
                :data_pedido, :data_entrega, :observacao, :criado_por,
                case when :status_ref = 'EM_SEPARACAO' then :iniciado_por else null end,
                case when :status_ref = 'EM_SEPARACAO' then now() else null end,
                null, null
            )
            returning id
            """
        ),
        {
            "empresa": cabecalho["empresa"],
            "pedido": cabecalho["pedido"],
            "status": status_ordem,
            "status_ref": status_ordem,
            "cliente_codigo": cabecalho["cliente"],
            "cliente_nome": cabecalho["razao_nome_cliente"],
            "data_pedido": cabecalho["data_pedido"],
            "data_entrega": cabecalho["data_entrega"],
            "observacao": _texto(observacao),
            "criado_por": usuario_id,
            "iniciado_por": usuario_id,
        },
    ).scalar_one()


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
    ) as saldo_metros,
    (
        select string_agg(distinct pr.descricao, ', ')
        from raw.car_itens_pedido i
        left join raw.produtos pr on pr.codigo = i.produto
        where i.empresa = s.empresa
          and i.pedido = s.pedido
          and coalesce(i.status_item, '') <> 'E'
    ) as artigos
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
    arquivados: bool = False,
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
        condicoes.append(
            "coalesce(st.codigo, 'SEM_SEPARACAO') = :status_separacao"
        )
        params["status_separacao"] = status_separacao
    if arquivados:
        condicoes.append(
            "exists (select 1 from public.wms_pedidos_arquivados arq "
            "where arq.empresa = p.empresa and arq.pedido = p.pedido)"
        )
    else:
        condicoes.append(
            "not exists (select 1 from public.wms_pedidos_arquivados arq "
            "where arq.empresa = p.empresa and arq.pedido = p.pedido)"
            " and coalesce(st.codigo, 'SEM_SEPARACAO') not in ('CANCELADO', 'ENVIADO')"
        )
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
    case
        when coalesce(st.codigo, 'SEM_SEPARACAO') in ('CANCELADO', 'ENVIADO')
            then coalesce(st.codigo, 'SEM_SEPARACAO')
        when count(i.item) = sum(case when coalesce(i.qtde_fat, 0) >= i.qtde then 1 else 0 end)
             and count(i.item) > 0
            then 'FATURADO'
        else coalesce(st.codigo, 'SEM_SEPARACAO')
    end                                    as situacao_codigo,
    st.id                                  as situacao_id,
    st.nome                                as situacao_nome,
    st.cor                                 as situacao_cor,
    st.ordem                               as situacao_ordem,
    st.acao                                as situacao_acao,
    st.perfis                              as situacao_perfis,
    arq.arquivado_em                       as arquivado_em,
    string_agg(distinct pr.descricao, ', ') filter (where pr.descricao is not null) as artigos
from raw.car_pedido p
join raw.car_itens_pedido i
  on i.empresa = p.empresa and i.pedido = p.pedido
left join raw.produtos pr on pr.codigo = i.produto
left join raw.clientes_principal c on c.codigo_cliente = p.cliente
left join public.wms_pedidos_situacao ps
  on ps.empresa = p.empresa and ps.pedido = p.pedido
left join public.wms_situacoes_pedido st on st.id = ps.situacao_id
left join public.wms_pedidos_arquivados arq
  on arq.empresa = p.empresa and arq.pedido = p.pedido
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
    s.id, s.status,
    st.id, st.codigo, st.nome, st.cor, st.ordem, st.acao, st.perfis,
    arq.arquivado_em
order by p.data_entrega asc nulls last, p.pedido
limit :limite offset :offset
"""

SQL_CONTAR_PEDIDOS = """
select count(*)::int
from (
    select p.empresa, p.pedido, s.id, s.status, st.codigo
    from raw.car_pedido p
    join raw.car_itens_pedido i
      on i.empresa = p.empresa and i.pedido = p.pedido
    left join raw.clientes_principal c on c.codigo_cliente = p.cliente
    left join public.wms_pedidos_situacao ps
      on ps.empresa = p.empresa and ps.pedido = p.pedido
    left join public.wms_situacoes_pedido st on st.id = ps.situacao_id
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
    group by p.empresa, p.pedido, s.id, s.status, st.codigo
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
        situacoes = conn.execute(
            text(
                """
                select st.codigo, count(*)::int
                from public.wms_pedidos_situacao ps
                join public.wms_situacoes_pedido st on st.id = ps.situacao_id
                where not exists (
                    select 1 from public.wms_pedidos_arquivados arq
                    where arq.empresa = ps.empresa and arq.pedido = ps.pedido
                )
                group by st.codigo
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

    por_status = {linha[0]: linha[1] for linha in situacoes}
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
    arquivados: bool = Query(False, description="Somente pedidos arquivados"),
) -> dict[str, Any]:
    """Backlog: pedidos aprovados e abertos no ERP (status 2) com saldo a separar."""
    filtro, params = _filtros_pedido(
        busca=busca.strip(),
        status_separacao=status_separacao.strip().upper(),
        arquivados=arquivados,
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
                "separacaoStatus": linha["situacao_codigo"] or "SEM_SEPARACAO",
                "situacaoId": linha["situacao_id"],
                "situacaoNome": linha["situacao_nome"],
                "situacaoCor": linha["situacao_cor"],
                "situacaoOrdem": linha["situacao_ordem"],
                "situacaoAcao": linha["situacao_acao"],
                "situacaoPerfis": list(linha["situacao_perfis"] or []),
                "artigos": linha["artigos"],
                "arquivado": linha["arquivado_em"] is not None,
                "arquivadoEm": _data(linha["arquivado_em"]),
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
                p.status_ped,
                arq.arquivado_em
            from raw.car_pedido p
            left join raw.clientes_principal c on c.codigo_cliente = p.cliente
            left join public.wms_pedidos_arquivados arq
              on arq.empresa = p.empresa and arq.pedido = p.pedido
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
    situacao = _situacao_atual(conn, empresa, pedido)
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
        "separacaoStatus": situacao["codigo"] if situacao else "SEM_SEPARACAO",
        "situacaoId": situacao["id"] if situacao else None,
        "situacaoNome": situacao["nome"] if situacao else None,
        "situacaoCor": situacao["cor"] if situacao else None,
        "situacaoOrdem": situacao["ordem"] if situacao else None,
        "situacaoAcao": situacao["acao"] if situacao else None,
        "situacaoPerfis": list(situacao["perfis"] or []) if situacao else [],
        "arquivado": linha["arquivado_em"] is not None,
        "arquivadoEm": _data(linha["arquivado_em"]),
        "itens": _itens_pedido(conn, empresa, pedido),
    }


@router.get("/wms/pedidos/{empresa}/{pedido}")
def detalhe_pedido(empresa: str, pedido: str, usuario: _dependente) -> dict[str, Any]:
    """Pedido com itens, saldo e o que ja esta reservado/separado no WMS."""
    with warehouse.engine().connect() as conn:
        return _pedido(conn, empresa, pedido)


def _validar_cor(cor: str) -> str:
    valor = (cor or "").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", valor):
        raise HTTPException(status_code=400, detail="Cor deve estar no formato #RRGGBB")
    return valor.lower()


def _normalizar_perfis(perfis: list[str]) -> list[str]:
    vistos: list[str] = []
    for perfil in perfis:
        nome = _slug(perfil or "")
        if nome and nome not in vistos:
            vistos.append(nome)
    return vistos


def _validar_acao(acao: str) -> str:
    valor = (acao or "").strip().upper()
    if valor not in ACOES_SITUACAO:
        raise HTTPException(
            status_code=400,
            detail=f"Ação inválida. Use: {', '.join(ACOES_SITUACAO)}",
        )
    return valor


@router.get("/wms/situacoes")
def listar_situacoes(
    usuario: _dependente,
    ativo: bool | None = Query(None, description="Filtra por situações ativas/inativas"),
) -> dict[str, Any]:
    """Cadastro de situações do pedido: cada situação ativa é uma coluna do kanban."""
    condicao = "" if ativo is None else "where s.ativo = :ativo"
    params: dict[str, Any] = {} if ativo is None else {"ativo": ativo}
    with warehouse.engine().connect() as conn:
        itens = [
            _situacao(linha)
            for linha in conn.execute(
                text(
                    f"""
                    select
                        s.*,
                        (
                            select count(*)::int
                            from public.wms_pedidos_situacao ps
                            where ps.situacao_id = s.id
                        ) as pedidos
                    from public.wms_situacoes_pedido s
                    {condicao}
                    order by s.ordem, s.id
                    """
                ),
                params,
            ).mappings()
        ]
    return {"itens": itens, "total": len(itens)}


@router.get("/wms/situacoes/{situacao_id}")
def detalhe_situacao(situacao_id: int, usuario: _dependente) -> dict[str, Any]:
    with warehouse.engine().connect() as conn:
        return _situacao(_situacao_por_id(conn, situacao_id))


@router.post("/wms/situacoes", status_code=status.HTTP_201_CREATED)
def criar_situacao(dados: NovaSituacao, usuario: _dependente) -> dict[str, Any]:
    nome = _texto(dados.nome)
    if nome is None:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    codigo = _slug(dados.codigo or nome)
    if not codigo:
        raise HTTPException(status_code=400, detail="Código inválido")
    cor = _validar_cor(dados.cor)
    acao = _validar_acao(dados.acao)
    perfis = _normalizar_perfis(dados.perfis)

    with warehouse.engine().begin() as conn:
        try:
            novo_id = conn.execute(
                text(
                    """
                    insert into public.wms_situacoes_pedido
                        (codigo, nome, cor, ordem, acao, perfis, ativo, sistema)
                    values
                        (:codigo, :nome, :cor, :ordem, :acao, :perfis, :ativo, false)
                    returning id
                    """
                ),
                {
                    "codigo": codigo,
                    "nome": nome,
                    "cor": cor,
                    "ordem": dados.ordem,
                    "acao": acao,
                    "perfis": perfis,
                    "ativo": dados.ativo,
                },
            ).scalar_one()
        except IntegrityError as erro:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe uma situação com esse código",
            ) from erro
        return _situacao(_situacao_por_id(conn, novo_id))


@router.put("/wms/situacoes/{situacao_id}")
def atualizar_situacao(
    situacao_id: int, dados: EdicaoSituacao, usuario: _dependente
) -> dict[str, Any]:
    campos: list[str] = []
    params: dict[str, Any] = {"id": situacao_id}
    if dados.nome is not None:
        nome = _texto(dados.nome)
        if nome is None:
            raise HTTPException(status_code=400, detail="Nome é obrigatório")
        campos.append("nome = :nome")
        params["nome"] = nome
    if dados.cor is not None:
        campos.append("cor = :cor")
        params["cor"] = _validar_cor(dados.cor)
    if dados.ordem is not None:
        campos.append("ordem = :ordem")
        params["ordem"] = dados.ordem
    if dados.acao is not None:
        campos.append("acao = :acao")
        params["acao"] = _validar_acao(dados.acao)
    if dados.perfis is not None:
        campos.append("perfis = :perfis")
        params["perfis"] = _normalizar_perfis(dados.perfis)

    with warehouse.engine().begin() as conn:
        atual = _situacao_por_id(conn, situacao_id)
        if dados.ativo is not None and not dados.ativo and atual["pedidos"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Situação em uso: mova os pedidos antes de desativá-la",
            )
        if dados.ativo is not None:
            campos.append("ativo = :ativo")
            params["ativo"] = dados.ativo
        if campos:
            conn.execute(
                text(
                    f"""
                    update public.wms_situacoes_pedido
                    set {", ".join(campos)}, atualizado_em = now()
                    where id = :id
                    """
                ),
                params,
            )
        return _situacao(_situacao_por_id(conn, situacao_id))


@router.delete("/wms/situacoes/{situacao_id}")
def excluir_situacao(situacao_id: int, usuario: _dependente) -> dict[str, Any]:
    with warehouse.engine().begin() as conn:
        atual = _situacao_por_id(conn, situacao_id)
        if atual["sistema"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Situação padrão do sistema não pode ser excluída",
            )
        if atual["pedidos"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Situação em uso: mova os pedidos antes de excluí-la",
            )
        conn.execute(
            text("delete from public.wms_situacoes_pedido where id = :id"),
            {"id": situacao_id},
        )
    return {"id": situacao_id, "excluida": True}


@router.post("/wms/pedidos/{empresa}/{pedido}/situacao")
def mover_pedido_situacao(
    empresa: str, pedido: str, dados: MoverSituacao, usuario: _dependente
) -> dict[str, Any]:
    """Move o pedido no kanban. A situação é local; a coluna define a ação no WMS."""
    empresa = (empresa or "").strip()
    pedido = (pedido or "").strip()
    with warehouse.engine().begin() as conn:
        cabecalho = _pedido_erp(conn, empresa, pedido)
        if cabecalho is None:
            raise HTTPException(status_code=404, detail="Pedido não encontrado")

        alvo = _situacao(_situacao_por_id(conn, dados.situacao_id))
        if not alvo["ativo"]:
            raise HTTPException(status_code=400, detail="Situação do pedido está inativa")
        if alvo["codigo"] in (STATUS_LIBERADO, STATUS_EM_SEPARACAO):
            if (
                cabecalho["status"] != "2"
                or (cabecalho["status_ped"] or "") == "E"
                or float(cabecalho["saldo"] or 0) <= 0
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Pedido não está liberado (aprovado e aberto) no ERP",
                )

        ordem = _ordem_ativa(conn, empresa, pedido)
        acao = alvo["acao"]

        if acao == ACAO_CRIAR:
            if ordem is None:
                nova_ordem = _criar_ordem(
                    conn,
                    cabecalho,
                    status_ordem=STATUS_EM_SEPARACAO,
                    usuario_id=dados.usuario_id,
                    observacao=dados.observacao,
                )
                _evento(
                    conn,
                    nova_ordem,
                    "INICIADA",
                    descricao=_texto(dados.observacao) or "Criada ao mover no kanban",
                    usuario_id=dados.usuario_id,
                )
            elif ordem["status"] == STATUS_LIBERADO:
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
                    {"id": ordem["id"], "usuario_id": dados.usuario_id},
                )
                _evento(
                    conn,
                    ordem["id"],
                    "INICIADA",
                    descricao=_texto(dados.observacao),
                    usuario_id=dados.usuario_id,
                )
        elif acao == ACAO_CONCLUIR:
            if ordem is None:
                separada = conn.execute(
                    text(
                        """
                        select 1
                        from public.wms_separacoes
                        where empresa = :empresa and pedido = :pedido
                          and status = 'SEPARADO'
                        limit 1
                        """
                    ),
                    {"empresa": empresa, "pedido": pedido},
                ).first()
                if separada is None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Pedido não possui ordem em separação para concluir",
                    )
            else:
                pecas = conn.execute(
                    text(
                        "select count(*)::int from public.wms_separacao_pecas "
                        "where separacao_id = :id"
                    ),
                    {"id": ordem["id"]},
                ).scalar_one()
                if pecas == 0:
                    raise HTTPException(
                        status_code=400,
                        detail="Selecione ao menos uma peça antes de concluir",
                    )
                conn.execute(
                    text(
                        """
                        update public.wms_separacao_pecas
                        set status = 'SEPARADA', updated_at = now()
                        where separacao_id = :id
                        """
                    ),
                    {"id": ordem["id"]},
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
                    {"id": ordem["id"], "usuario_id": dados.usuario_id},
                )
                _evento(
                    conn,
                    ordem["id"],
                    "CONCLUIDA",
                    descricao=_texto(dados.observacao),
                    usuario_id=dados.usuario_id,
                    payload={"pecas": pecas},
                )
        elif acao == ACAO_CANCELAR:
            if ordem is not None:
                pecas = conn.execute(
                    text(
                        "delete from public.wms_separacao_pecas "
                        "where separacao_id = :id returning id"
                    ),
                    {"id": ordem["id"]},
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
                        "id": ordem["id"],
                        "motivo": _texto(dados.observacao),
                        "usuario_id": dados.usuario_id,
                    },
                )
                _evento(
                    conn,
                    ordem["id"],
                    "CANCELADA",
                    descricao=_texto(dados.observacao),
                    usuario_id=dados.usuario_id,
                    payload={"pecasLiberadas": len(pecas)},
                )
        else:
            if ordem is not None:
                pecas = conn.execute(
                    text(
                        "select count(*)::int from public.wms_separacao_pecas "
                        "where separacao_id = :id"
                    ),
                    {"id": ordem["id"]},
                ).scalar_one()
                if alvo["codigo"] == STATUS_LIBERADO and pecas == 0:
                    conn.execute(
                        text(
                            """
                            update public.wms_separacoes
                            set status = 'LIBERADO',
                                iniciado_por = null,
                                iniciado_em = null,
                                atualizado_em = now()
                            where id = :id
                            """
                        ),
                        {"id": ordem["id"]},
                    )
                    _evento(
                        conn,
                        ordem["id"],
                        "LIBERADA",
                        descricao=_texto(dados.observacao),
                        usuario_id=dados.usuario_id,
                    )
                elif dados.cancelar_ordem:
                    liberadas = conn.execute(
                        text(
                            "delete from public.wms_separacao_pecas "
                            "where separacao_id = :id returning id"
                        ),
                        {"id": ordem["id"]},
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
                            "id": ordem["id"],
                            "motivo": _texto(dados.observacao),
                            "usuario_id": dados.usuario_id,
                        },
                    )
                    _evento(
                        conn,
                        ordem["id"],
                        "CANCELADA",
                        descricao=_texto(dados.observacao)
                        or "Cancelada ao mover o pedido",
                        usuario_id=dados.usuario_id,
                        payload={"pecasLiberadas": len(liberadas)},
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "ORDEN_ATIVA_CANCELAR"
                        ),
                    )

        conn.execute(
            text(
                "delete from public.wms_pedidos_arquivados "
                "where empresa = :empresa and pedido = :pedido"
            ),
            {"empresa": empresa, "pedido": pedido},
        )
        _definir_situacao(
            conn,
            empresa,
            pedido,
            alvo["codigo"],
            usuario_id=dados.usuario_id,
            observacao=dados.observacao,
        )
        return _pedido(conn, empresa, pedido)


@router.post("/wms/pedidos/{empresa}/{pedido}/arquivar")
def arquivar_pedido(
    empresa: str, pedido: str, usuario: _dependente
) -> dict[str, Any]:
    """Tira um pedido cancelado do kanban/lista (situacao local, ERP intacto)."""
    empresa = (empresa or "").strip()
    pedido = (pedido or "").strip()
    with warehouse.engine().begin() as conn:
        if _pedido_erp(conn, empresa, pedido) is None:
            raise HTTPException(status_code=404, detail="Pedido não encontrado")
        atual = _situacao_atual(conn, empresa, pedido)
        if atual is None or atual["codigo"] != STATUS_CANCELADO:
            raise HTTPException(
                status_code=400,
                detail="Só é possível arquivar pedidos cancelados",
            )
        conn.execute(
            text(
                """
                insert into public.wms_pedidos_arquivados
                    (empresa, pedido, situacao_id, arquivado_em, arquivado_por)
                values (:empresa, :pedido, :situacao_id, now(), NULL)
                on conflict (empresa, pedido) do update
                    set situacao_id = excluded.situacao_id,
                        arquivado_em = now()
                """
            ),
            {"empresa": empresa, "pedido": pedido, "situacao_id": atual["id"]},
        )
        return _pedido(conn, empresa, pedido)


@router.post("/wms/pedidos/{empresa}/{pedido}/desarquivar")
def desarquivar_pedido(
    empresa: str, pedido: str, usuario: _dependente
) -> dict[str, Any]:
    """Devolve um pedido arquivado ao kanban/lista."""
    empresa = (empresa or "").strip()
    pedido = (pedido or "").strip()
    with warehouse.engine().begin() as conn:
        removidos = conn.execute(
            text(
                "delete from public.wms_pedidos_arquivados "
                "where empresa = :empresa and pedido = :pedido"
            ),
            {"empresa": empresa, "pedido": pedido},
        ).rowcount
        if not removidos:
            raise HTTPException(
                status_code=404, detail="Pedido não está arquivado"
            )
        return _pedido(conn, empresa, pedido)


@router.get("/wms/separacoes")
def listar_separacoes(
    usuario: _dependente,
    status_filtro: str = Query("", alias="status", description="Status da ordem"),
    busca: str = Query("", description="Pedido, cliente (codigo) ou razao social"),
    limite: int = Query(50, ge=1, le=LIMITE_MAX),
    offset: int = Query(0, ge=0),
    arquivadas: bool = Query(False, description="Somente ordens arquivadas"),
) -> dict[str, Any]:
    """Ordens de separacao (kanban/lista)."""
    condicoes: list[str] = []
    params: dict[str, Any] = {"limite": limite, "offset": offset}
    condicoes.append(
        "s.arquivada_em is not null" if arquivadas else "s.arquivada_em is null"
    )
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
        _definir_situacao(
            conn,
            empresa,
            pedido,
            STATUS_LIBERADO,
            usuario_id=dados.usuario_id,
            observacao=dados.observacao,
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
        _definir_situacao(
            conn,
            atual["empresa"],
            atual["pedido"],
            STATUS_EM_SEPARACAO,
            usuario_id=dados.usuario_id,
            observacao=dados.observacao,
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
            _definir_situacao(
                conn,
                atual["empresa"],
                atual["pedido"],
                STATUS_SEPARADO,
                usuario_id=dados.usuario_id,
                observacao=dados.observacao,
            )
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
        _definir_situacao(
            conn,
            atual["empresa"],
            atual["pedido"],
            STATUS_SEPARADO,
            usuario_id=dados.usuario_id,
            observacao=dados.observacao,
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
            _definir_situacao(
                conn,
                atual["empresa"],
                atual["pedido"],
                STATUS_CANCELADO,
                usuario_id=dados.usuario_id,
                observacao=dados.motivo,
            )
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
        _definir_situacao(
            conn,
            atual["empresa"],
            atual["pedido"],
            STATUS_CANCELADO,
            usuario_id=dados.usuario_id,
            observacao=_texto(dados.motivo) or _texto(dados.observacao),
        )
        return _separacao_por_id(conn, separacao_id)


@router.post("/wms/separacoes/{separacao_id}/arquivar")
def arquivar_separacao(
    separacao_id: int, usuario: _dependente
) -> dict[str, Any]:
    """Tira uma ordem cancelada do kanban/lista, preservando o histórico."""
    with warehouse.engine().begin() as conn:
        atual = _travar_separacao(conn, separacao_id)
        if atual["status"] != STATUS_CANCELADO:
            raise HTTPException(
                status_code=400,
                detail="Só é possível arquivar ordens canceladas",
            )
        conn.execute(
            text(
                """
                update public.wms_separacoes
                set arquivada_em = now(),
                    arquivada_por = :usuario_id,
                    atualizado_em = now()
                where id = :id
                """
            ),
            {"id": separacao_id, "usuario_id": None},
        )
        _evento(conn, separacao_id, "ARQUIVADA")
        return _separacao_por_id(conn, separacao_id)


@router.post("/wms/separacoes/{separacao_id}/desarquivar")
def desarquivar_separacao(
    separacao_id: int, usuario: _dependente
) -> dict[str, Any]:
    """Devolve uma ordem cancelada arquivada ao kanban/lista."""
    with warehouse.engine().begin() as conn:
        atual = _travar_separacao(conn, separacao_id)
        if atual["arquivada_em"] is None:
            raise HTTPException(
                status_code=404, detail="Ordem não está arquivada"
            )
        conn.execute(
            text(
                """
                update public.wms_separacoes
                set arquivada_em = null,
                    arquivada_por = null,
                    atualizado_em = now()
                where id = :id
                """
            ),
            {"id": separacao_id},
        )
        _evento(conn, separacao_id, "DESARQUIVADA")
        return _separacao_por_id(conn, separacao_id)


@router.post("/wms/separacoes/{separacao_id}/reabrir")
def reabrir_separacao(
    separacao_id: int,
    dados: Reabertura | None = None,
    usuario: _dependente = None,
) -> dict[str, Any]:
    """Devolve uma ordem cancelada ao fluxo de producao (libera as pecas)."""
    dados = dados or Reabertura()
    novo_status = (dados.status or STATUS_LIBERADO).strip().upper()
    if novo_status not in STATUS_ATIVOS:
        raise HTTPException(
            status_code=400,
            detail="Status inválido: use LIBERADO ou EM_SEPARACAO",
        )
    with warehouse.engine().begin() as conn:
        atual = _travar_separacao(conn, separacao_id)
        if atual["status"] != STATUS_CANCELADO:
            raise HTTPException(
                status_code=400,
                detail="Só é possível reabrir ordens canceladas",
            )
        conn.execute(
            text(
                """
                update public.wms_separacoes
                set status = :status,
                    arquivada_em = null,
                    arquivada_por = null,
                    motivo_cancelamento = null,
                    cancelado_por = null,
                    cancelado_em = null,
                    iniciado_em = case when :em_separacao
                                       then now() else null end,
                    iniciado_por = case when :em_separacao
                                        then :usuario_id else null end,
                    concluido_em = null,
                    concluido_por = null,
                    atualizado_em = now()
                where id = :id
                """
            ),
            {
                "id": separacao_id,
                "status": novo_status,
                "em_separacao": novo_status == STATUS_EM_SEPARACAO,
                "usuario_id": dados.usuario_id,
            },
        )
        conn.execute(
            text(
                "delete from public.wms_pedidos_arquivados "
                "where empresa = :empresa and pedido = :pedido"
            ),
            {"empresa": atual["empresa"], "pedido": atual["pedido"]},
        )
        _evento(
            conn,
            separacao_id,
            "REABERTA",
            descricao=_texto(dados.observacao),
            usuario_id=dados.usuario_id,
            payload={"status": novo_status},
        )
        _definir_situacao(
            conn,
            atual["empresa"],
            atual["pedido"],
            novo_status,
            usuario_id=dados.usuario_id,
            observacao=_texto(dados.observacao),
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
            "or a.produto ilike :busca or a.cor ilike :busca "
            "or pr.descricao ilike :busca_desc)"
        )
        params["busca"] = f"%{busca}%"
        params["busca_desc"] = f"%{busca}%"
    for valor, coluna in (
        (gaveta, "a.gaveta"),
        (sub_lote, "a.sub_lote"),
        (aviso, "a.aviso"),
        (cor, "a.cor"),
        (produto, "a.produto"),
    ):
        if valor:
            nome = f"f_{coluna.split('.')[-1]}"
            condicoes.append(f"{coluna} ilike :{nome}")
            params[nome] = f"%{valor}%"
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
        left join raw.produtos pr on pr.codigo = a.produto
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


@router.get("/wms/pedidos/{empresa}/{pedido}/itens/{item}/estoque-disponivel")
def estoque_disponivel_para_item(
    empresa: str,
    pedido: str,
    item: int,
    usuario: _dependente,
    limite: int = Query(200, ge=1, le=LIMITE_MAX),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Peças em aberto compatíveis com o item do pedido, para verificar capacidade de suprimento."""
    with warehouse.engine().connect() as conn:
        item_pedido = _item_do_pedido(conn, empresa, pedido, item)
        filtros, params = _condicoes_estoque(
            busca="", gaveta="", sub_lote="", aviso="", cor="", produto=""
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

    total_metros = sum((linha["metros"] or 0) for linha in itens)
    saldo = item_pedido["saldo"] or 0
    percentual = (total_metros / saldo * 100) if saldo > 0 else 0
    return {
        "item": {
            "item": item_pedido["item"],
            "produto": item_pedido["produto"],
            "produto_desc": item_pedido["produto_desc"],
            "situacao": item_pedido["situacao"],
            "situacao_desc": item_pedido["situacao_desc"],
            "cor": item_pedido["cor"],
            "cor_desc": item_pedido["cor_desc"],
            "desenho": item_pedido["desenho"],
            "desenho_desc": item_pedido["desenho_desc"],
            "variante": item_pedido["variante"],
            "variante_desc": item_pedido["variante_desc"],
            "categoria": item_pedido["categoria"],
            "categoria_desc": item_pedido["categoria_desc"],
            "largura": item_pedido["largura"],
            "saldo": _float0(item_pedido["saldo"]),
            "unid": item_pedido["unid"],
        },
        "itens": itens,
        "total": total,
        "totalMetrosDisponiveis": total_metros,
        "saldoItem": saldo,
        "percentualCapacidade": round(min(percentual, 100), 1) if saldo > 0 else 0,
    }


@router.get("/wms/separacoes/{separacao_id}/itens/{item}/pecas")
def pecas_do_item(
    separacao_id: int,
    item: int,
    usuario: _dependente,
    busca: str = Query("", description="Rolo, peca ou texto no campo escolhido"),
    gaveta: str = Query("", description="Codigo da gaveta (endereco)"),
    sub_lote: str = Query("", alias="subLote", description="Sublote"),
    aviso: str = Query("", description="Aviso"),
    campo: str = Query(
        "", description="Campo da busca: lote (sub-lote), aviso ou gaveta"
    ),
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

        termo = busca.strip()
        campo_busca = campo.strip().lower()
        coluna_busca = CAMPOS_BUSCA_PECA.get(campo_busca) if campo_busca else None
        if campo_busca and coluna_busca is None:
            raise HTTPException(
                status_code=400, detail="Campo de busca inválido: use lote, aviso ou gaveta"
            )
        filtros, params = _condicoes_estoque(
            busca="" if coluna_busca else termo,
            gaveta=gaveta.strip(),
            sub_lote=sub_lote.strip(),
            aviso=aviso.strip(),
            cor="",
            produto="",
        )
        if coluna_busca and termo:
            filtros += f" and a.{coluna_busca} ilike :busca_campo"
            params["busca_campo"] = f"%{termo}%"
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
        _definir_situacao(
            conn,
            atual["empresa"],
            atual["pedido"],
            STATUS_EM_SEPARACAO,
            usuario_id=dados.usuario_id,
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


class KanbanReordenarItem(BaseModel):
    chave: str
    posicao: int = Field(ge=0)


class KanbanReordenar(BaseModel):
    tipo: str = Field(pattern="^(PEDIDO|SEPARACAO)$")
    coluna: str
    itens: list[KanbanReordenarItem]
    usuario_id: int | None = None


@router.get("/wms/kanban/ordem")
def kanban_ordem(
    usuario: _dependente,
    tipo: str = Query(..., pattern="^(PEDIDO|SEPARACAO)$"),
    colunas: str = Query(""),
) -> dict[str, dict[str, int]]:
    """Posicoes verticais salvas do kanban (globais, por tipo e coluna)."""
    where = ["tipo = :tipo"]
    params: dict[str, Any] = {"tipo": tipo}
    lista = [c.strip().upper() for c in colunas.split(",") if c.strip()]
    if lista:
        where.append("coluna = ANY(:colunas)")
        params["colunas"] = lista
    sql = text(
        "select chave, coluna, posicao from public.wms_kanban_ordem "
        f"where {' and '.join(where)}"
    )
    with warehouse.engine().begin() as conn:
        rows = conn.execute(sql, params).mappings().all()
    res: dict[str, dict[str, int]] = {}
    for r in rows:
        res.setdefault(r["coluna"], {})[r["chave"]] = int(r["posicao"] or 0)
    return res


@router.post("/wms/kanban/reordenar")
def kanban_reordenar(
    usuario: _dependente, dados: KanbanReordenar
) -> dict[str, bool]:
    """Salva a ordem vertical de uma coluna do kanban."""
    with warehouse.engine().begin() as conn:
        for item in dados.itens:
            partes = item.chave.split("|")
            conn.execute(
                text(
                    """
                    insert into public.wms_kanban_ordem
                        (tipo, chave, empresa, pedido, separacao_id, coluna,
                         posicao, atualizado_em, atualizado_por)
                    values
                        (:tipo, :chave, :empresa, :pedido, :separacao_id,
                         :coluna, :posicao, now(), :atualizado_por)
                    on conflict (tipo, chave, coluna) do update
                        set posicao = excluded.posicao,
                            atualizado_em = now(),
                            atualizado_por = excluded.atualizado_por
                    """
                ),
                {
                    "tipo": dados.tipo,
                    "chave": item.chave,
                    "empresa": partes[0] if len(partes) == 2 else None,
                    "pedido": (
                        partes[1]
                        if len(partes) == 2 and dados.tipo == "PEDIDO"
                        else None
                    ),
                    "separacao_id": (
                        int(item.chave)
                        if dados.tipo == "SEPARACAO" and item.chave.isdigit()
                        else None
                    ),
                    "coluna": dados.coluna,
                    "posicao": int(item.posicao or 0),
                    "atualizado_por": dados.usuario_id,
                },
            )
    return {"ok": True}


__all__ = ["router"]