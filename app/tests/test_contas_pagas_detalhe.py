"""Testes do detalhe de Contas Pagas (BI): lançamentos + as 4 janelas do card."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routers import contas_pagas_detalhe as detalhe

client = TestClient(app)


def _linha(
    documento: str = "000007424",
    serie: str = "U   ",
    fornecedor: str = "00055",
    razao: str = "MF LOG TRANSPORTES LTDA                     ",
    banco: str = "BANCO SANTANDER",
    nr_banco: str = "033",
    parcela: str = "01",
    empresa: str = "13",
    baixa: str = "2026-09-30",
    valor: str = "2068.73",
    juros: str = "0",
    desconto: str = "0",
) -> dict:
    return {
        "Empresa": empresa,
        "Documento": documento,
        "Serie": serie,
        "Tipo_Fornec": "0",
        "Fornecedor": fornecedor,
        "Parcela": parcela,
        "Parcial": "1",
        "Data_Baixa": datetime.fromisoformat(baixa),
        "Valor_Pago": Decimal(valor),
        "Juros_Pagos": Decimal(juros),
        "Desconto_Recebido": Decimal(desconto),
        "Valor_Liquido": Decimal(valor),
        "Nr_Banco": nr_banco,
        "Nr_Cheque": "D000002257",
        "Razao_Nome_Cliente": razao,
        "Nome_Bco_Bancos": banco,
    }


def _serie_mes(mes: str, total: str, lancamentos: int = 1) -> dict:
    ano, m = mes.split("-")
    return {
        "mes": date(int(ano), int(m), 1),
        "total": Decimal(total),
        "lancamentos": lancamentos,
    }


@pytest.fixture(autouse=True)
def sem_auth(monkeypatch):
    monkeypatch.setenv("API_AUTENTICACAO_EXIGIDA", "false")


@pytest.fixture
def erp_mock(monkeypatch):
    """Separa as duas consultas: série mensal e itens do mês."""

    def montar(itens, serie):
        chamadas: list[str] = []

        def query(sql: str, params=None):
            chamadas.append("serie" if sql is detalhe.SQL_SERIE else "itens")
            return list(serie) if sql is detalhe.SQL_SERIE else list(itens)

        monkeypatch.setattr(detalhe.erp, "query", query)
        return chamadas

    return montar


class TestJanelas:
    def test_as_quatro_janelas_batem_com_o_card(self):
        # As mesmas de `_janelas_4` em kpis.py, com o fim exclusivo.
        janelas = detalhe._janelas(date(2026, 10, 13))
        assert janelas["mes"] == (date(2026, 10, 1), date(2026, 11, 1))
        assert janelas["mes_anterior"] == (date(2026, 9, 1), date(2026, 10, 1))
        assert janelas["ano_atual"] == (date(2026, 1, 1), date(2026, 11, 1))
        assert janelas["ano_anterior"] == (date(2025, 1, 1), date(2026, 1, 1))

    def test_somar_meses_atravessa_a_virada_de_ano(self):
        assert detalhe._somar_meses(date(2026, 1, 1), -1) == date(2025, 12, 1)
        assert detalhe._somar_meses(date(2025, 12, 1), 1) == date(2026, 1, 1)


class TestRota:
    def test_devolve_o_mes_com_itens_e_as_outras_janelas_so_com_total(self, erp_mock):
        erp_mock(
            [_linha(valor="100"), _linha(documento="X", valor="50")],
            [_serie_mes("2026-10", "150", 2)],
        )
        corpo = client.get(
            "/contas-pagas-detalhe", params={"data": "2026-10-13"}
        ).json()

        assert corpo["referencia"]["mes"] == "2026-10"
        assert corpo["mes"]["total"] == 150.0
        assert corpo["mes"]["lancamentos"] == 2
        assert len(corpo["mes"]["itens"]) == 2
        # As outras janelas não trazem itens: a tela só lista o mês escolhido.
        for nome in ("mes_anterior", "ano_atual", "ano_anterior"):
            assert "itens" not in corpo[nome]
        # Outubro/2026 está dentro de `ano_atual` (jan a dez), então ele soma junto.
        assert corpo["mes_anterior"]["total"] == 0.0
        assert corpo["ano_atual"]["total"] == 150.0
        assert corpo["ano_anterior"]["total"] == 0.0

    def test_soma_a_serie_nas_janelas_do_ano(self, erp_mock):
        erp_mock(
            [],
            [
                _serie_mes("2026-01", "1000"),
                _serie_mes("2026-09", "2000"),
                _serie_mes("2026-10", "3000"),
                _serie_mes("2025-07", "7000", 7),
            ],
        )
        corpo = client.get(
            "/contas-pagas-detalhe", params={"data": "2026-10-13"}
        ).json()

        # Ano atual: jan a dez/2026.
        assert corpo["ano_atual"]["total"] == 6000.0
        assert corpo["ano_atual"]["lancamentos"] == 3
        # Ano anterior: o ano inteiro de 2025.
        assert corpo["ano_anterior"]["total"] == 7000.0
        assert corpo["ano_anterior"]["lancamentos"] == 7
        assert corpo["mes_anterior"]["total"] == 2000.0

    def test_a_serie_tem_24_meses_terminando_na_referencia(self, erp_mock):
        erp_mock([], [_serie_mes("2026-10", "100")])
        corpo = client.get(
            "/contas-pagas-detalhe", params={"data": "2026-10-13"}
        ).json()

        meses = corpo["meses"]
        assert len(meses) == 24
        assert meses[-1]["mes"] == "2026-10"
        assert meses[0]["mes"] == "2024-11"
        assert meses[-1]["total"] == 100.0
        # Mês sem movimento aparece zerado, não some.
        assert sum(1 for m in meses if m["total"] == 0) == 23

    def test_limpa_espacos_dos_campos_char(self, erp_mock):
        erp_mock([_linha()], [])
        corpo = client.get(
            "/contas-pagas-detalhe", params={"data": "2026-10-13"}
        ).json()
        item = corpo["mes"]["itens"][0]
        assert item["serie"] == "U"
        assert item["razao_social"] == "MF LOG TRANSPORTES LTDA"
        assert item["numero_banco"] == "033"
        assert item["data_baixa"] == "2026-09-30"

    def test_preserva_o_sinal_do_valor(self, erp_mock):
        # Sem abs(): o card soma Valor_Pago com o sinal que vier.
        erp_mock([_linha(valor="-120.50")], [])
        corpo = client.get(
            "/contas-pagas-detalhe", params={"data": "2026-10-13"}
        ).json()
        assert corpo["mes"]["itens"][0]["valor"] == -120.5
        assert corpo["mes"]["total"] == -120.5

    def test_agrupamentos_por_fornecedor_banco_e_empresa(self, erp_mock):
        erp_mock(
            [
                _linha(documento="A", valor="100", razao="TRANSPORTES KELLER"),
                _linha(
                    documento="B",
                    valor="50",
                    razao="TRANSPORTES KELLER",
                    banco="BANCO DO BRASIL",
                ),
                _linha(documento="C", valor="25", razao="FOLHA", empresa="14"),
            ],
            [],
        )
        corpo = client.get(
            "/contas-pagas-detalhe", params={"data": "2026-10-13"}
        ).json()
        mes = corpo["mes"]

        assert mes["por_fornecedor"][0] == {
            "razao_social": "TRANSPORTES KELLER",
            "lancamentos": 2,
            "valor": 150.0,
        }
        assert [g["banco"] for g in mes["por_banco"]] == ["BANCO SANTANDER", "BANCO DO BRASIL"]
        assert [g["empresa"] for g in mes["por_empresa"]] == ["13", "14"]

    def test_agrupamento_ordena_por_valor_decrescente(self, erp_mock):
        erp_mock(
            [
                _linha(documento="A", valor="10", razao="PEQUENO"),
                _linha(documento="B", valor="1000", razao="GRANDE"),
            ],
            [],
        )
        corpo = client.get(
            "/contas-pagas-detalhe", params={"data": "2026-10-13"}
        ).json()
        assert corpo["mes"]["por_fornecedor"][0]["razao_social"] == "GRANDE"

    def test_periodos_legiveis(self, erp_mock):
        erp_mock([], [_serie_mes("2026-10", "100")])
        corpo = client.get(
            "/contas-pagas-detalhe", params={"data": "2026-10-13"}
        ).json()

        assert corpo["mes"]["periodo"] == "01/10/2026 a 31/10/2026"
        assert corpo["mes_anterior"]["periodo"] == "01/09/2026 a 30/09/2026"
        assert corpo["ano_atual"]["periodo"] == "01/01/2026 a 31/10/2026"
        assert corpo["ano_anterior"]["periodo"] == "01/01/2025 a 31/12/2025"
        assert corpo["referencia"]["rotulo"] == "outubro"

    def test_usa_uma_consulta_de_serie_e_uma_de_itens(self, erp_mock):
        chamadas = erp_mock([_linha()], [_serie_mes("2026-10", "2068.73")])
        client.get("/contas-pagas-detalhe", params={"data": "2026-10-13"}).json()
        assert chamadas.count("serie") == 1
        assert chamadas.count("itens") == 1


class TestWhitelist:
    def test_as_duas_consultas_passam_pelo_guard_de_leitura(self):
        from src.db.erp import assert_read_only

        assert_read_only(detalhe.SQL_SERIE)
        assert_read_only(detalhe.SQL_ITENS)

    def test_as_consultas_so_leem_nas_tabelas_da_base(self):
        for sql in (detalhe.SQL_SERIE, detalhe.SQL_ITENS):
            baixo = sql.lower()
            assert "insert" not in baixo
            assert "update " not in baixo
            assert "delete" not in baixo
            assert "truncate" not in baixo
