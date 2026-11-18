from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from src.etl import delta_erp


def test_sincronizacao_completa_regrave_pedido_antigo_e_itens(monkeypatch: Any) -> None:
    pai_plano = (
        SimpleNamespace(destino="car_pedido", tabela_erp="Car_Pedido"),
        ["Empresa", "Pedido"],
        ["empresa", "pedido"],
        ["empresa", "pedido"],
        [],
    )
    filho_plano = (
        SimpleNamespace(destino="car_itens_pedido", tabela_erp="Car_Itens_Pedido"),
        ["Empresa", "Pedido", "Item", "Qtde"],
        ["empresa", "pedido", "item", "qtde"],
        ["empresa", "pedido", "item"],
        [],
    )
    pais = [{"empresa": "13", "pedido": "00006979"}]
    filhos = [{"empresa": "13", "pedido": "00006979", "item": 1, "qtde": 2}]
    consultas: list[tuple[str, list[Any]]] = []

    def fake_plano(tabela: str) -> Any:
        return pai_plano if tabela == "Car_Pedido" else filho_plano

    def fake_query(sql: str, parametros: list[Any]) -> list[dict[str, Any]]:
        consultas.append((sql, parametros))
        return filhos if "Car_Itens_Pedido" in sql else pais

    conn = object()

    @contextmanager
    def fake_begin() -> Any:
        yield conn

    engine = SimpleNamespace(begin=fake_begin)
    escritas: list[tuple[str, Any, str, Any]] = []

    def fake_apagar(
        conexao: Any, eng: Any, tabela: str, chave: Any, valores: Any
    ) -> int:
        assert eng is engine
        escritas.append(("delete", conexao, tabela, valores))
        return 1

    def fake_upsert(
        conexao: Any, tabela: str, chave: Any, colunas: Any, linhas: list[dict[str, Any]]
    ) -> int:
        escritas.append(("upsert", conexao, tabela, linhas))
        return len(linhas)

    monkeypatch.setattr(delta_erp, "_plano", fake_plano)
    monkeypatch.setattr(delta_erp, "_linhas_raw", lambda linhas, *_: linhas)
    monkeypatch.setattr(delta_erp.erp, "query", fake_query)
    monkeypatch.setattr(delta_erp.warehouse, "engine", lambda: engine)
    monkeypatch.setattr(delta_erp.upsert, "apagar_documentos_conn", fake_apagar)
    monkeypatch.setattr(delta_erp.upsert, "upsert_conn", fake_upsert)

    resultado = delta_erp.sincronizar_pedidos()

    assert resultado == {"desde": None, "documentos": 1, "itens": 1}
    sql_pais, parametros_pais = consultas[0]
    assert "p.[Data_Pedido] >= ?" not in sql_pais
    assert "p.[Status] <> '3'" in sql_pais
    assert "f.[Nosso_Pedido] = p.[Pedido]" in sql_pais
    assert parametros_pais == []
    assert [escrita[0] for escrita in escritas] == ["delete", "upsert", "upsert"]
    assert all(escrita[1] is conn for escrita in escritas)
    assert escritas[2][2] == "car_pedido"


def test_sql_de_faturamentos_sem_cursor_de_data() -> None:
    sql, parametros = delta_erp._sql_faturamentos(["Empresa", "Pedido"], None)

    assert "p.[Data_Emissao] >= ?" not in sql
    assert parametros == []
