"""Rotas de detalhe do faturamento para o BI (D7): base 12 meses no Neon.

O card "Faturamento" do BI ganhou uma tela de detalhe que lista o **item de nota**
(empresa, numero da nota, pedido, romaneio, data, cliente, representante, quantidade e
valor) dos ultimos 12 meses, com filtro por periodo/representante/cliente/produto.

O fluxo e de **base + delta**:

- `POST /faturamento-detalhe/carga`: le o ERP ao vivo (mesma fonte de detalhe do card —
  `vwFaturamento` + `Fat_Pedido` + `Fat_Vend_Pedido` + `Rec_Vendedores`) dos ultimos 12
  meses e **substitui** o Neon (`delete` + `insert` na mesma transacao), gravando o
  estado (`carga_completa`, `contagem`, `ultima_data` como watermark). Devolve os itens
  lidos em `itens` — quem chamou a carga ja tem o que precisa, sem reler o Neon;
- `POST /faturamento-detalhe/sync`: so o delta — notas com `Data_Nota >= ultima_data`
  (inclui a re-leitura do dia do watermark, inofensiva e que pega notas novas do mesmo
  dia), `upsert` por PK, apaga o que saiu da janela de 12 meses, atualiza o estado e
  devolve **apenas os itens do delta** em `itens`;
- `GET /faturamento-detalhe/estado`: o front decide se e hora de carregar/atualizar e
  evita bater na API a cada tela (o resto fica no IndexedDB do navegador);
- `GET /faturamento-detalhe`: leitura paginada no Neon com filtros e um `resumo` da
  selecao (mesma formula do card: `Σ(Vr_Total + Acres_Desc)`).

Todas as rotas exigem o escopo `faturamento:leitura`, o mesmo dos cards de faturamento.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from src.api.auth.escopos import ESCOPO_FATURAMENTO, exigir_escopo
from src.api.auth.usuarios import Usuario
from src.db import erp, neon

router = APIRouter(tags=["faturamento-detalhe"])

_faturamento = Annotated[Usuario | None, Depends(exigir_escopo(ESCOPO_FATURAMENTO))]

COLUNAS = (
    "empresa",
    "pedido",
    "item",
    "nr_nota",
    "data_nota",
    "cliente",
    "nome_cliente",
    "cod_produto",
    "metros",
    "vr_unitario",
    "vr_total",
    "acres_desc",
    "peso",
    "vr_nota",
    "romaneio",
    "representante_codigo",
    "representante",
)

_UPSERT_ATUALIZA = ", ".join(f"{coluna} = excluded.{coluna}" for coluna in COLUNAS)

SQL_DETALHE = """
select vf.Empresa as Empresa, vf.Pedido as Pedido, vf.Item as Item, vf.Nr_Nota as Nr_Nota,
  convert(char(10), vf.Data_Nota, 120) as Data_Nota,
  vf.Cliente as Cliente, vf.Nome_Cliente as Nome_Cliente, vf.Cod_Produto as Cod_Produto,
  vf.Metros as Metros, vf.Vr_Unitario as Vr_Unitario, vf.Vr_Total as Vr_Total,
  vf.Acres_Desc as Acres_Desc, vf.Peso as Peso, vf.Vr_Nota as Vr_Nota,
  fp.Romaneio as Romaneio, vc.Vendedor as Vendedor, rv.Nome_Vendedores as Nome_Vendedores
from DBProDash.dbo.vwFaturamento vf
join Fat_Pedido fp on fp.Empresa = vf.Empresa and fp.Pedido = vf.Pedido
left join (
  select Empresa_NF_Vendedores, Doc_NF_Vendedores,
         min(Vendedor_NF_Vendedores) as Vendedor
  from Fat_Vend_Pedido
  group by Empresa_NF_Vendedores, Doc_NF_Vendedores
) vc on vc.Empresa_NF_Vendedores = vf.Empresa and vc.Doc_NF_Vendedores = vf.Pedido
left join Rec_Vendedores rv on rv.Codigo_Vendedores = vc.Vendedor
where vf.Data_Nota >= ? and vf.Data_Nota < ?
"""


def _inicio_12_meses(hoje: date) -> date:
    """Primeiro dia do mes de hoje ha 12 meses (janela mensal dos KPIs)."""
    return date(hoje.year - 1, hoje.month, 1)


def _linha_detalhe(linha: dict[str, Any]) -> dict[str, Any]:
    """Mapa a linha bruta do ERP para o formato do Neon.

    Os campos char/var do SQL Server chegam com espacos no final (ex.: `Nome_Vendedores`),
    entao todo texto e `.strip()`; a `Data_Nota` vem como `'YYYY-MM-DD'` do `convert`.
    """
    def _v(chave: str) -> Any:
        return linha.get(chave)

    texto = lambda valor: valor.strip() if isinstance(valor, str) else valor  # noqa: E731
    data_nota = _v("Data_Nota")
    return {
        "empresa": texto(_v("Empresa")),
        "pedido": texto(_v("Pedido")),
        "item": int(_v("Item") or 0),
        "nr_nota": texto(_v("Nr_Nota")),
        "data_nota": date.fromisoformat(data_nota) if data_nota else None,
        "cliente": texto(_v("Cliente")),
        "nome_cliente": texto(_v("Nome_Cliente")),
        "cod_produto": texto(_v("Cod_Produto")),
        "metros": float(_v("Metros") or 0),
        "vr_unitario": float(_v("Vr_Unitario") or 0),
        "vr_total": float(_v("Vr_Total") or 0),
        "acres_desc": float(_v("Acres_Desc") or 0),
        "peso": float(_v("Peso") or 0),
        "vr_nota": float(_v("Vr_Nota") or 0),
        "romaneio": texto(_v("Romaneio")),
        "representante_codigo": texto(_v("Vendedor")),
        "representante": texto(_v("Nome_Vendedores")),
    }


def _ler_erp(inicio: date, fim: date) -> list[dict[str, Any]]:
    return [_linha_detalhe(linha) for linha in erp.query(SQL_DETALHE, (inicio, fim))]


def _estado(conn: Any) -> dict[str, Any]:
    linha = conn.execute(
        text("select carga_completa, contagem, ultima_data, atualizado_em "
             "from marts.faturamento_detalhe_estado where id = 1")
    ).mappings().first()
    if linha is None:
        return {"carga_completa": False, "contagem": 0, "ultima_data": None}
    return {
        "carga_completa": bool(linha["carga_completa"]),
        "contagem": int(linha["contagem"] or 0),
        "ultima_data": linha["ultima_data"],
    }


def _serializar_itens(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Serializa o payload do ERP para o JSON da resposta.

    `data_nota` e `date`, que o FastAPI sabe serializar, mas o `dict` cru nao; aqui
    fica explicito para o `carga`/`sync` devolverem os itens no proprio corpo e o
    navegador popular o IndexedDB sem uma segunda leitura da base no Neon.
    """
    return [{**item, "data_nota": item["data_nota"].isoformat() if item["data_nota"] else None} for item in payload]


def _gravar_estado(
    conn: Any, carga_completa: bool, contagem: int, ultima_data: date | None
) -> None:
    conn.execute(
        text(
            "insert into marts.faturamento_detalhe_estado "
            "(id, carga_completa, contagem, ultima_data, atualizado_em) "
            "values (1, :carga_completa, :contagem, :ultima_data, now()) "
            "on conflict (id) do update set "
            "carga_completa = excluded.carga_completa, "
            "contagem = excluded.contagem, "
            "ultima_data = excluded.ultima_data, "
            "atualizado_em = excluded.atualizado_em"
        ),
        {"carga_completa": carga_completa, "contagem": contagem, "ultima_data": ultima_data},
    )


def _janela() -> tuple[date, date]:
    hoje = date.today()
    return _inicio_12_meses(hoje), hoje


@router.get("/faturamento-detalhe/estado")
def estado_faturamento_detalhe(usuario: _faturamento) -> dict[str, Any]:
    """Marcador da base de detalhe: o front so chama a API quando precisa atualizar."""
    inicio, fim = _janela()
    with neon.engine().connect() as conn:
        estado = _estado(conn)
    return {**estado, "janela_inicio": inicio.isoformat(), "janela_fim": fim.isoformat()}


@router.post("/faturamento-detalhe/carga")
def carga_faturamento_detalhe(usuario: _faturamento) -> dict[str, Any]:
    """(Re)constrói a base de 12 meses: le o ERP ao vivo e substitui o Neon."""
    inicio, fim = _janela()
    payload = _ler_erp(inicio, fim + timedelta(days=1))
    with neon.engine().begin() as conn:
        conn.execute(text("delete from marts.faturamento_detalhe"))
        _inserir(conn, payload)
        contagem = _contagem(conn)
        ultima_data = _ultima_data(conn)
        _gravar_estado(conn, True, contagem, ultima_data)
    return {
        "processados": len(payload),
        "contagem": contagem,
        "ultima_data": ultima_data,
        "janela_inicio": inicio,
        "janela_fim": fim,
        "itens": _serializar_itens(payload),
    }


@router.post("/faturamento-detalhe/sync")
def sync_faturamento_detalhe(usuario: _faturamento) -> dict[str, Any]:
    """Delta: le so notas com `Data_Nota >= ultima_data`, faz upsert e atualiza o estado.

    Rejeita com 409 se ainda nao houve carga (`carga_completa = false`): sem watermark nao
    da para saber onde comeca o que e novo.
    """
    with neon.engine().connect() as conn:
        estado = _estado(conn)
    if not estado["carga_completa"]:
        raise HTTPException(status_code=409, detail="carga inicial ainda nao feita")
    inicio = estado["ultima_data"] or _inicio_12_meses(date.today())
    _, fim = _janela()
    payload = _ler_erp(inicio, fim + timedelta(days=1))
    with neon.engine().begin() as conn:
        _inserir(conn, payload, atualizar=True)
        conn.execute(
            text("delete from marts.faturamento_detalhe where data_nota < :corte"),
            {"corte": _inicio_12_meses(date.today())},
        )
        contagem = _contagem(conn)
        ultima_data = _ultima_data(conn)
        _gravar_estado(conn, True, contagem, ultima_data)
    return {
        "processados": len(payload),
        "contagem": contagem,
        "ultima_data": ultima_data,
        "itens": _serializar_itens(payload),
    }


def _inserir(conn: Any, payload: list[dict[str, Any]], *, atualizar: bool = False) -> None:
    if not payload:
        return
    marcadores = ", ".join(f":{coluna}" for coluna in COLUNAS)
    destino = ", ".join(COLUNAS)
    resolver = (
        "on conflict (empresa, pedido, item, nr_nota) "
        f"do update set {_UPSERT_ATUALIZA}, atualizado_em = now()"
        if atualizar
        else "on conflict (empresa, pedido, item, nr_nota) do nothing"
    )
    conn.execute(
        text(
            f"insert into marts.faturamento_detalhe ({destino}) "  # noqa: S608
            f"values ({marcadores}) {resolver}"
        ),
        payload,
    )


def _contagem(conn: Any) -> int:
    return int(conn.execute(text("select count(*) from marts.faturamento_detalhe")).scalar() or 0)


def _ultima_data(conn: Any) -> date | None:
    return conn.execute(text("select max(data_nota) from marts.faturamento_detalhe")).scalar()


@router.get("/faturamento-detalhe")
def detalhe_faturamento(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    representante: str | None = None,
    cliente: str | None = None,
    produto: str | None = None,
    pagina: int = 1,
    por_pagina: int = 100,
    usuario: _faturamento = None,
) -> dict[str, Any]:
    """Leitura paginada no Neon com filtros; `resumo` traz os totais da selecao."""
    if pagina < 1:
        raise HTTPException(status_code=422, detail="pagina comeca em 1")
    por_pagina = max(1, min(por_pagina, 500))
    inicio = data_inicio or _inicio_12_meses(date.today())
    fim = data_fim or date.today()
    where, params = _filtros(inicio, fim, representante, cliente, produto)
    with neon.engine().connect() as conn:
        resumo = conn.execute(
            text(
                "select count(*) as itens, "
                "count(distinct (empresa, nr_nota)) as notas, "
                "count(distinct (empresa, pedido)) as pedidos, "
                "coalesce(sum(coalesce(vr_total, 0) + coalesce(acres_desc, 0)), 0) as faturamento, "
                "coalesce(sum(coalesce(metros, 0)), 0) as metros, "
                "coalesce(sum(coalesce(peso, 0)), 0) as peso "
                f"from marts.faturamento_detalhe {where}"  # noqa: S608
            ),
            params,
        ).mappings().one()
        itens = [
            dict(linha)
            for linha in conn.execute(
                text(
                    "select empresa, pedido, item, nr_nota, data_nota, cliente, nome_cliente, "
                    "cod_produto, metros, vr_unitario, vr_total, acres_desc, peso, vr_nota, "
                    "romaneio, representante_codigo, representante "
                    f"from marts.faturamento_detalhe {where} "  # noqa: S608
                    "order by data_nota desc, nr_nota desc, item "
                    "limit :por_pagina offset :offset"
                ),
                {**params, "por_pagina": por_pagina, "offset": (pagina - 1) * por_pagina},
            ).mappings()
        ]
    total = int(resumo["itens"] or 0)
    return {
        "resumo": {
            "itens": total,
            "notas": int(resumo["notas"] or 0),
            "pedidos": int(resumo["pedidos"] or 0),
            "metros": float(resumo["metros"] or 0),
            "peso": float(resumo["peso"] or 0),
            "faturamento": float(resumo["faturamento"] or 0),
        },
        "paginacao": {
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": (total + por_pagina - 1) // por_pagina if total else 0,
        },
        "itens": [
            {
                **item,
                "data_nota": item["data_nota"].isoformat() if item["data_nota"] else None,
            }
            for item in itens
        ],
    }


def _filtros(
    data_inicio: date,
    data_fim: date,
    representante: str | None,
    cliente: str | None,
    produto: str | None,
) -> tuple[str, dict[str, Any]]:
    clausulas: list[str] = []
    params: dict[str, Any] = {"data_inicio": data_inicio, "data_fim": data_fim}
    if representante:
        clausulas.append("representante ilike :representante")
        params["representante"] = f"%{representante}%"
    if cliente:
        clausulas.append("nome_cliente ilike :cliente")
        params["cliente"] = f"%{cliente}%"
    if produto:
        clausulas.append("cod_produto ilike :produto")
        params["produto"] = f"%{produto}%"
    where = "where data_nota >= :data_inicio and data_nota <= :data_fim"
    if clausulas:
        where += " and " + " and ".join(clausulas)
    return where, params


@router.get("/faturamento-detalhe/opcoes")
def opcoes_faturamento_detalhe(usuario: _faturamento) -> dict[str, Any]:
    """Distintos para os filtros: representantes (codigo+nome) e produtos (codigo)."""
    with neon.engine().connect() as conn:
        representantes = [
            {"codigo": linha["representante_codigo"], "nome": linha["representante"]}
            for linha in conn.execute(
                text(
                    "select distinct representante_codigo, representante "
                    "from marts.faturamento_detalhe "
                    "where representante_codigo is not null "
                    "order by representante"
                )
            ).mappings()
        ]
        produtos = [
            linha["cod_produto"]
            for linha in conn.execute(
                text(
                    "select distinct cod_produto from marts.faturamento_detalhe "
                    "where cod_produto is not null order by cod_produto"
                )
            ).mappings()
        ]
    return {"representantes": representantes, "produtos": produtos}


__all__ = ["router"]