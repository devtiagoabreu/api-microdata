"""Testes do detalhe de faturamento para o BI (D7): base 12 meses no Neon.

A suite toca o Neon real (delete/insert em `marts.faturamento_detalhe`), no mesmo estilo do
`test_publicar_neon` (que reescreve os marts do dashboard). Cada teste limpa a base: o passo
final (`carga`) e feito fora da suite para deixar a base real carregada.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from src.api.main import app
from src.api.routers import faturamento_detalhe
from src.db import erp, neon

client = TestClient(app)


def _linha(
    pedido: str = "0001",
    item: int = 1,
    nr_nota: str = "100",
    dia: str = "2026-10-05",
    vr_total: str | float = "10",
    acres_desc: str | float = "2",
    vendedor: str = "0001",
    representante: str = "REPRESENTACOES A",
    produto: str = "P1",
    cliente: str = "CLI A",
) -> dict:
    return {
        "Empresa": "13",
        "Pedido": pedido,
        "Item": item,
        "Nr_Nota": nr_nota,
        "Data_Nota": dia,
        "Cliente": cliente,
        "Nome_Cliente": cliente,
        "Cod_Produto": produto,
        "Metros": "100.5",
        "Vr_Unitario": "3.25",
        "Vr_Total": vr_total,
        "Acres_Desc": acres_desc,
        "Peso": "5.5",
        "Vr_Nota": vr_total,
        "Romaneio": f"ROM {nr_nota}",
        "Vendedor": vendedor,
        "Nome_Vendedores": representante,
    }


def _limpar_base() -> None:
    with neon.engine().begin() as conn:
        conn.execute(text("delete from marts.faturamento_detalhe"))
        conn.execute(
            text(
                "update marts.faturamento_detalhe_estado set "
                "carga_completa = false, contagem = 0, ultima_data = null where id = 1"
            )
        )


class TestContrato:
    def test_rotas_publicadas(self):
        rotas = set(app.openapi()["paths"])
        for rota in (
            "/faturamento-detalhe/estado",
            "/faturamento-detalhe/carga",
            "/faturamento-detalhe/sync",
            "/faturamento-detalhe",
            "/faturamento-detalhe/opcoes",
        ):
            assert rota in rotas, rota

    def test_sql_do_detalhe_e_uma_leitura_no_erp(self):
        erp.assert_read_only(faturamento_detalhe.SQL_DETALHE)
        assert "vwFaturamento" in faturamento_detalhe.SQL_DETALHE
        assert "marts." not in faturamento_detalhe.SQL_DETALHE


class TestMapa:
    def test_limpa_espacos_e_convert_datas(self):
        linha = _linha()
        linha["Nome_Cliente"] = "  CLIENTE COM CHARS   "
        linha["Data_Nota"] = "2026-10-05"
        mapeada = faturamento_detalhe._linha_detalhe(linha)
        assert mapeada["nome_cliente"] == "CLIENTE COM CHARS"
        assert mapeada["data_nota"].isoformat() == "2026-10-05"
        assert mapeada["pedido"] == "0001"
        assert mapeada["item"] == 1
        assert mapeada["metros"] == 100.5
        assert mapeada["vr_unitario"] == 3.25
        assert mapeada["romaneio"] == "ROM 100"
        assert mapeada["representante"] == "REPRESENTACOES A"

    def test_campos_nulos_viram_zero(self):
        linha = _linha()
        linha["Vr_Total"] = None
        linha["Acres_Desc"] = None
        linha["Metros"] = None
        mapeada = faturamento_detalhe._linha_detalhe(linha)
        assert mapeada["vr_total"] == 0.0
        assert mapeada["acres_desc"] == 0.0
        assert mapeada["metros"] == 0.0


class TestJanela12Meses:
    def test_primeiro_dia_do_mes_ha_12_meses(self):
        assert faturamento_detalhe._inicio_12_meses(date(2026, 10, 8)) == date(2025, 10, 1)
        assert faturamento_detalhe._inicio_12_meses(date(2026, 1, 15)) == date(2025, 1, 1)


class TestFiltros:
    def test_sem_filtro_so_datainico_e_data_fim(self):
        where, params = faturamento_detalhe._filtros(
            date(2026, 10, 1),
            date(2026, 10, 8),
            None,
            None,
            None,
        )
        assert "data_nota >= :data_inicio" in where
        assert "data_nota <= :data_fim" in where
        assert params == {"data_inicio": date(2026, 10, 1), "data_fim": date(2026, 10, 8)}

    def test_filtro_de_representante_vira_ilike(self):
        where, params = faturamento_detalhe._filtros(
            date(2026, 10, 1),
            date(2026, 10, 8),
            "REP A",
            None,
            "P1",
        )
        assert "representante ilike :representante" in where
        assert "cod_produto ilike :produto" in where
        assert params["representante"] == "%REP A%"


class TestCargaESync:
    """Ciclo completo contra o Neon real, com o erp.query simulado."""

    @pytest.fixture(autouse=True)
    def _base_limpa(self):
        _limpar_base()
        yield
        _limpar_base()

    def test_carga_12_meses_substitui_e_grava_estado(self, monkeypatch):
        consultas: list[tuple[str, tuple]] = []

        def consulta(sql, params=()):
            consultas.append((sql, params))
            return [
                _linha(),
                _linha(
                    pedido="0002",
                    item=1,
                    nr_nota="101",
                    dia="2026-10-06",
                    vr_total="30",
                    representante="REPRESENTACOES B",
                ),
            ]

        monkeypatch.setattr(faturamento_detalhe.erp, "query", consulta)
        corpo = client.post("/faturamento-detalhe/carga").json()
        assert corpo["processados"] == 2
        assert corpo["contagem"] == 2
        assert corpo["ultima_data"] == "2026-10-06"
        _, params = consultas[0]
        assert params[0] == faturamento_detalhe._inicio_12_meses(date.today())
        assert params[1] == date.today() + timedelta(days=1)
        assert "marts." not in consultas[0][0]
        estado = client.get("/faturamento-detalhe/estado").json()
        assert estado["carga_completa"] is True
        assert estado["contagem"] == 2
        assert estado["ultima_data"] == "2026-10-06"
        assert "janela_inicio" in estado and "janela_fim" in estado

    def test_sync_sem_carga_da_409(self, monkeypatch):
        def consulta(sql, params=()):
            return [_linha()]

        monkeypatch.setattr(faturamento_detalhe.erp, "query", consulta)
        assert client.post("/faturamento-detalhe/sync").status_code == 409

    def test_sync_traz_o_delta_e_nao_duplica(self, monkeypatch):
        def consulta(sql, params=()):
            return [_linha(), _linha(pedido="0002", nr_nota="101", dia="2026-10-06")]

        monkeypatch.setattr(faturamento_detalhe.erp, "query", consulta)
        client.post("/faturamento-detalhe/carga")

        # Delta: re-emite a nota 100 (valor mudou) e inclui a nota 102 do mesmo dia 06/10.
        def delta(sql, params=()):
            return [
                _linha(vr_total="12", acres_desc="3"),
                _linha(pedido="0003", nr_nota="102", dia="2026-10-07", vr_total="7"),
            ]

        monkeypatch.setattr(faturamento_detalhe.erp, "query", delta)
        corpo = client.post("/faturamento-detalhe/sync").json()
        assert corpo["processados"] == 2
        assert corpo["contagem"] == 3
        assert corpo["ultima_data"] == "2026-10-07"
        with neon.engine().connect() as conn:
            valor = conn.execute(
                text(
                    "select vr_total, acres_desc from marts.faturamento_detalhe "
                    "where nr_nota = '100'"
                )
            ).one()
        assert valor[0] == 12 and valor[1] == 3, "o upsert substitui a linha do watermark"

    def test_detalhe_filtra_e_resume(self, monkeypatch):
        def consulta(sql, params=()):
            return [
                _linha(),
                _linha(
                    pedido="0002", nr_nota="101", dia="2026-10-06", vr_total="30",
                    acres_desc="0", representante="REPRESENTACOES B", produto="P2",
                    cliente="CLI B",
                ),
                _linha(
                    pedido="0003", nr_nota="102", dia="2026-09-01", vr_total="5",
                    acres_desc="0", vendedor="0003", representante="REPRESENTACOES A",
                    produto="P1", cliente="CLI A",
                ),
            ]

        monkeypatch.setattr(faturamento_detalhe.erp, "query", consulta)
        client.post("/faturamento-detalhe/carga")
        corpo = client.get(
            "/faturamento-detalhe",
            params={"data_inicio": "2026-09-01", "data_fim": "2026-10-31"},
        ).json()
        assert corpo["resumo"] == {
            "itens": 3,
            "notas": 3,
            "pedidos": 3,
            "metros": 301.5,
            "peso": 16.5,
            "faturamento": 47.0,
        }
        assert corpo["paginacao"]["total"] == 3
        assert len(corpo["itens"]) == 3
        assert corpo["itens"][0]["data_nota"] == "2026-10-06"
        assert corpo["itens"][0]["representante"] == "REPRESENTACOES B"

        so_rep = client.get("/faturamento-detalhe", params={"representante": "B"}).json()
        assert so_rep["resumo"]["itens"] == 1

        so_prod = client.get("/faturamento-detalhe", params={"produto": "P1"}).json()
        assert so_prod["resumo"]["itens"] == 2

        so_cli = client.get("/faturamento-detalhe", params={"cliente": "CLI A"}).json()
        assert so_cli["resumo"]["itens"] == 2

    def test_paginacao_divide(self, monkeypatch):
        def consulta(sql, params=()):
            return [
                _linha(pedido=f"{i:04d}", nr_nota=str(100 + i), dia="2026-10-05")
                for i in range(3)
            ]

        monkeypatch.setattr(faturamento_detalhe.erp, "query", consulta)
        client.post("/faturamento-detalhe/carga")
        primeira = client.get("/faturamento-detalhe", params={"por_pagina": 2, "pagina": 1}).json()
        assert len(primeira["itens"]) == 2
        assert primeira["paginacao"]["total_paginas"] == 2
        segunda = client.get("/faturamento-detalhe", params={"por_pagina": 2, "pagina": 2}).json()
        assert len(segunda["itens"]) == 1

    def test_pagina_zero_e_recusada(self):
        assert client.get("/faturamento-detalhe", params={"pagina": 0}).status_code == 422

    def test_opcoes_lista_representantes_e_produtos(self, monkeypatch):
        def consulta(sql, params=()):
            return [
                _linha(),
                _linha(
                    pedido="0002", vendedor="0002", nr_nota="101",
                    representante="REPRESENTACOES B", produto="P2",
                ),
            ]

        monkeypatch.setattr(faturamento_detalhe.erp, "query", consulta)
        client.post("/faturamento-detalhe/carga")
        corpo = client.get("/faturamento-detalhe/opcoes").json()
        assert {"codigo": "0001", "nome": "REPRESENTACOES A"} in corpo["representantes"]
        assert {"codigo": "0002", "nome": "REPRESENTACOES B"} in corpo["representantes"]
        assert corpo["produtos"] == ["P1", "P2"]