from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from sqlalchemy import text

from src.db import erp, warehouse
from src.etl import sources
from src.etl.extract import introspect
from src.etl.load import upsert
from src.etl.transform import values
from src.etl.transform.naming import qualificar_sql_server

CHAVE_PAI = ("Empresa", "Pedido")
CHAVE_PAI_RAW = ("empresa", "pedido")
LOTE_CHAVES = 500


def _ident(coluna: str) -> str:
    return f"[{coluna.replace(']', ']]')}]"


def _plano(tabela_erp: str) -> tuple[Any, list[str], list[str], list[str], list[Any]]:
    fonte = sources.por_tabela(tabela_erp)
    colunas_pg, chave_raw = introspect.planejar(fonte, perfilar=False)
    meta_erp = introspect.colunas_erp(tabela_erp)
    mapa = {coluna.origem: coluna.nome for coluna in colunas_pg}
    colunas_erp = list(mapa)
    return fonte, colunas_erp, [mapa[coluna] for coluna in colunas_erp], chave_raw, meta_erp


def _max_data(engine: Any, tabela: str, coluna: str) -> datetime | date | None:
    with engine.connect() as conn:
        return conn.execute(text(f"select max({coluna}) from raw.{tabela}")).scalar()


def _iso(valor: datetime | date | None) -> str | None:
    return valor.isoformat() if valor is not None else None


def _linhas_raw(
    linhas: list[dict[str, Any]],
    colunas_erp: list[str],
    colunas_raw: list[str],
    meta_erp: list[Any],
) -> list[dict[str, Any]]:
    resultado: list[dict[str, Any]] = []
    for linha in linhas:
        limpa = values.linha_limpa(meta_erp, linha)
        resultado.append(
            {colunas_raw[i]: limpa.get(coluna) for i, coluna in enumerate(colunas_erp)}
        )
    return resultado


def _carregar_filhos(engine: Any, tabela_filho: str, pais: list[dict[str, Any]]) -> int:
    fonte, colunas_erp, colunas_raw, chave_raw, meta_erp = _plano(tabela_filho)
    destino = qualificar_sql_server(fonte.tabela_erp)
    selecao = ", ".join(_ident(coluna) for coluna in colunas_erp)
    total = 0

    for inicio in range(0, len(pais), LOTE_CHAVES):
        lote = pais[inicio : inicio + LOTE_CHAVES]
        condicoes = " or ".join(
            f"({_ident(CHAVE_PAI[0])} = ? and {_ident(CHAVE_PAI[1])} = ?)" for _ in lote
        )
        parametros = [
            valor
            for linha in lote
            for valor in (linha["empresa"], linha["pedido"])
        ]
        sql = f"select {selecao} from {destino} where {condicoes}"
        filhos = _linhas_raw(
            erp.query(sql, parametros), colunas_erp, colunas_raw, meta_erp
        )
        upsert.apagar_documentos(engine, fonte.destino, list(CHAVE_PAI_RAW), lote)
        total += upsert.upsert(engine, fonte.destino, chave_raw, colunas_raw, filhos)

    return total


def _sincronizar(
    *,
    tabela_pai: str,
    tabela_filho: str,
    raw_pai: str,
    coluna_data_raw: str,
    montar_sql: Callable[[list[str], datetime | date | None], tuple[str, list[Any]]],
) -> dict[str, Any]:
    engine = warehouse.engine()
    desde = _max_data(engine, raw_pai, coluna_data_raw)
    _, colunas_erp, colunas_raw, chave_raw, meta_erp = _plano(tabela_pai)
    sql, parametros = montar_sql(colunas_erp, desde)
    pais = _linhas_raw(erp.query(sql, parametros), colunas_erp, colunas_raw, meta_erp)

    if not pais:
        return {"desde": _iso(desde), "documentos": 0, "itens": 0}

    itens = _carregar_filhos(engine, tabela_filho, pais)
    documentos = upsert.upsert(engine, raw_pai, chave_raw, colunas_raw, pais)
    return {"desde": _iso(desde), "documentos": documentos, "itens": itens}


def _sql_pedidos(
    colunas_erp: list[str], desde: datetime | date | None
) -> tuple[str, list[Any]]:
    selecao = ", ".join(f"p.{_ident(coluna)}" for coluna in colunas_erp)
    pedido = qualificar_sql_server("dbo.Car_Pedido")
    faturamento = qualificar_sql_server("dbo.Fat_Pedido")
    condicoes = [
        "(p.[Status] is null or p.[Status] <> '3')",
        (
            f"not exists (select 1 from {faturamento} f "
            "where f.[Empresa] = p.[Empresa] and f.[Nosso_Pedido] = p.[Pedido])"
        ),
    ]
    parametros: list[Any] = []

    if desde is not None:
        condicoes.insert(0, "p.[Data_Pedido] >= ?")
        parametros.append(desde)

    sql = (
        f"select {selecao} from {pedido} p where " + " and ".join(condicoes)
    )
    return sql, parametros


def _sql_faturamentos(
    colunas_erp: list[str], desde: datetime | date | None
) -> tuple[str, list[Any]]:
    selecao = ", ".join(f"p.{_ident(coluna)}" for coluna in colunas_erp)
    faturamento = qualificar_sql_server("dbo.Fat_Pedido")
    sql = f"select {selecao} from {faturamento} p"
    parametros: list[Any] = []

    if desde is not None:
        sql += " where p.[Data_Emissao] >= ?"
        parametros.append(desde)

    return sql, parametros


def sincronizar_pedidos() -> dict[str, Any]:
    return _sincronizar(
        tabela_pai="Car_Pedido",
        tabela_filho="Car_Itens_Pedido",
        raw_pai="car_pedido",
        coluna_data_raw="data_pedido",
        montar_sql=_sql_pedidos,
    )


def sincronizar_faturamentos() -> dict[str, Any]:
    return _sincronizar(
        tabela_pai="Fat_Pedido",
        tabela_filho="Fat_Itens_Pedido",
        raw_pai="fat_pedido",
        coluna_data_raw="data_emissao",
        montar_sql=_sql_faturamentos,
    )
