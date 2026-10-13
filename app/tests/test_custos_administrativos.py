"""Testes do detalhe de custo administrativo (BI): lançamentos + agrupamentos."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routers import custos_administrativos as detalhe

client = TestClient(app)


def _linha(
    documento: str = "016092026U",
    fornecedor: str = "00001",
    razao: str = "FOLHA DE PAGAMENTO",
    despesa: str = "FIXOS",
    despesa2: str = "",
    dpto1: int = 1,
    dpto2: int = 1,
    dpto3: int = 1,
    dpto4: int = 2,
    dpto_nome: str = "ADM SBO",
    valor: str = "-2740.01",
    baixa: str = "2026-09-16",
    empresa: str = "13",
) -> dict:
    return {
        "Empresa": empresa,
        "Documento": documento,
        "PArcela": "1",
        "CodFornecedor": fornecedor,
        "Razao_Nome_Cliente": razao,
        "DescDesp1": despesa,
        "DescDesp2": despesa2,
        "CodDpto1": dpto1,
        "CodDpto2": dpto2,
        "CodDpto3": dpto3,
        "CodDpto4": dpto4,
        "DescDpto4": dpto_nome,
        "Data_Baixa": date.fromisoformat(baixa),
        "Data_Emissao": date.fromisoformat("2026-09-01"),
        "Referente": "OBS",
        "Valor_Baixado": Decimal(valor),
    }


@pytest.fixture(autouse=True)
def sem_auth(monkeypatch):
    monkeypatch.setenv("API_AUTENTICACAO_EXIGIDA", "false")


class TestFiltro:
    def test_so_aceita_departamentos_administrativos(self, monkeypatch):
        # Precisa devolver a lista nova a cada chamada: a rota busca os dois meses.
        def busca(sql, params=()):
            return [
                _linha(),
                _linha(documento="FORA", dpto1=2, dpto_nome="PRODUCAO"),
                _linha(documento="FORA2", dpto3=9, dpto_nome="OUTRO"),
            ]

        monkeypatch.setattr(detalhe.erp, "ultimo_resultado", busca)
        corpo = client.get(
            "/custos-administrativos-detalhe", params={"data": "2026-10-09"}
        ).json()

        assert len(corpo["mes_anterior"]["itens"]) == 1
        assert corpo["mes_anterior"]["itens"][0]["documento"] == "016092026U"

    def test_usa_a_whitelist_read_only(self):
        from src.db.erp import assert_read_only

        assert_read_only(detalhe.SQL_DETALHE)

    def test_monta_as_janelas_do_mes_atual_e_anterior(self):
        (ini_atual, fim_atual), (ini_ant, fim_ant) = detalhe._janelas(date(2026, 10, 9))
        assert (ini_atual, fim_atual) == (date(2026, 10, 1), date(2026, 10, 9))
        assert (ini_ant, fim_ant) == (date(2026, 9, 1), date(2026, 9, 30))

    def test_janelas_January_que_vira_ano(self):
        # Janeiro: o mês anterior é dezembro do ano anterior.
        (_, _), (ini_ant, fim_ant) = detalhe._janelas(date(2027, 1, 20))
        assert (ini_ant, fim_ant) == (date(2026, 12, 1), date(2026, 12, 31))


class TestResposta:
    def test_soma_bate_com_o_cartao_que_usa_o_mesmo_campo(self, monkeypatch):
        # A `uspCustoAdmComparativo` soma `Valor_Baixado`; a lista soma o absoluto das
        # mesmas linhas, então as batem — e a ordenação por maior valor fica correta.
        linhas = [
            _linha(documento="A", valor="2740.01"),
            _linha(documento="B", valor="1274.50"),
        ]
        monkeypatch.setattr(detalhe.erp, "ultimo_resultado", lambda sql, params=(): linhas)
        corpo = client.get(
            "/custos-administrativos-detalhe", params={"data": "2026-10-09"}
        ).json()

        assert round(corpo["mes_anterior"]["total"], 2) == 4014.51
        assert corpo["mes_anterior"]["lancamentos"] == 2

    def test_normaliza_sinal_variando_do_rateio(self, monkeypatch):
        # `E_S` entrada/saixa faz o valor vir negativo em parte das linhas; custo é custo.
        linhas = [
            _linha(documento="A", valor="100"),
            _linha(documento="B", valor="-30"),
        ]
        monkeypatch.setattr(detalhe.erp, "ultimo_resultado", lambda sql, params=(): linhas)
        corpo = client.get(
            "/custos-administrativos-detalhe", params={"data": "2026-10-09"}
        ).json()
        anterior = corpo["mes_anterior"]
        assert [i["valor"] for i in anterior["itens"]] == [100.0, 30.0]
        assert round(anterior["total"], 2) == 130.0

    def test_mes_sem_baixa_vem_zerado_e_nao_quebra(self, monkeypatch):
        monkeypatch.setattr(detalhe.erp, "ultimo_resultado", lambda sql, params=(): [])
        corpo = client.get(
            "/custos-administrativos-detalhe", params={"data": "2026-10-09"}
        ).json()

        for chave in ("mes_atual", "mes_anterior"):
            assert corpo[chave]["total"] == 0
            assert corpo[chave]["itens"] == []
            assert corpo[chave]["por_despesa"] == []

    def test_agrupa_por_departamento_despesa_e_fornecedor(self, monkeypatch):
        linhas = [
            _linha(documento="A", despesa="FIXOS", razao="FOLHA", valor="100"),
            _linha(documento="B", despesa="FIXOS", razao="FOLHA", valor="50"),
            _linha(documento="C", despesa="VARIÁVEIS", razao="TELEFONICA", valor="25"),
        ]
        monkeypatch.setattr(detalhe.erp, "ultimo_resultado", lambda sql, params=(): linhas)
        corpo = client.get(
            "/custos-administrativos-detalhe", params={"data": "2026-10-09"}
        ).json()
        anterior = corpo["mes_anterior"]

        assert [g["departamento_nome"] for g in anterior["por_departamento"]] == ["ADM SBO"]
        assert [g["despesa"] for g in anterior["por_despesa"]] == ["FIXOS", "VARIÁVEIS"]
        assert anterior["por_despesa"][0] == {
            "despesa": "FIXOS",
            "lancamentos": 2,
            "valor": 150.0,
        }
        assert [g["razao_social"] for g in anterior["por_fornecedor"]] == [
            "FOLHA",
            "TELEFONICA",
        ]

    def test_agrupamento_ordena_por_valor_decrescente(self, monkeypatch):
        linhas = [
            _linha(documento="A", razao="PEQUENO", valor="10"),
            _linha(documento="B", razao="GRANDE", valor="1000"),
        ]
        monkeypatch.setattr(detalhe.erp, "ultimo_resultado", lambda sql, params=(): linhas)
        corpo = client.get(
            "/custos-administrativos-detalhe", params={"data": "2026-10-09"}
        ).json()
        grupos = corpo["mes_anterior"]["por_fornecedor"]
        assert grupos[0]["razao_social"] == "GRANDE"

    def test_devolve_o_periodo_legivel_de_cada_mes(self, monkeypatch):
        monkeypatch.setattr(detalhe.erp, "ultimo_resultado", lambda sql, params=(): [])
        corpo = client.get(
            "/custos-administrativos-detalhe", params={"data": "2026-10-09"}
        ).json()

        assert corpo["mes_atual"]["periodo"] == "01/10/2026 a 09/10/2026"
        assert corpo["mes_anterior"]["periodo"] == "01/09/2026 a 30/09/2026"
        assert corpo["mes_anterior"]["mes"] == "2026-09"
        assert corpo["departamentos"] == ["1.1.1.1", "1.1.1.2"]

    def test_limpa_espacos_dos_campos_char(self, monkeypatch):
        linhas = [_linha(documento="016092026U   ", razao="FOLHA DE PAGAMENTO   ")]
        monkeypatch.setattr(detalhe.erp, "ultimo_resultado", lambda sql, params=(): linhas)
        corpo = client.get(
            "/custos-administrativos-detalhe", params={"data": "2026-10-09"}
        ).json()
        item = corpo["mes_anterior"]["itens"][0]
        assert item["documento"] == "016092026U"
        assert item["razao_social"] == "FOLHA DE PAGAMENTO"
        assert item["data_baixa"] == "2026-09-16"
        assert item["departamento"] == "1.1.1.2"


def _linha_mes(
    mes: str,
    documento: str = "016U",
    valor: str = "100",
    razao: str = "FOLHA DE PAGAMENTO",
    despesa: str = "FIXOS",
    dpto_nome: str = "ADM SBO",
    dpto4: int = 2,
) -> dict:
    return _linha(
        documento=documento,
        razao=razao,
        despesa=despesa,
        dpto_nome=dpto_nome,
        dpto4=dpto4,
        valor=valor,
        baixa=f"{mes}-10",
    )


# Os 12 meses fechados de uma referência em outubro/2026.
MESES_FECHADOS = [
    "2025-10", "2025-11", "2025-12",
    "2026-01", "2026-02", "2026-03", "2026-04",
    "2026-05", "2026-06", "2026-07", "2026-08", "2026-09",
]


@pytest.fixture
def anual(monkeypatch):
    """Duas fontes distintas: itens do rateio e faturamento mês a mês."""

    def montar(itens, faturamento):
        monkeypatch.setattr(
            detalhe.erp, "ultimo_resultado", lambda sql, params=(): list(itens)
        )
        monkeypatch.setattr(
            detalhe.erp,
            "query",
            lambda sql, params=(): [
                {"Mes": mes, "Faturamento": Decimal(str(valor))}
                for mes, valor in faturamento.items()
            ],
        )

    return montar


class TestJanela12Meses:
    def test_pegam_o_mes_de_referencia_menos_doze_ate_o_anterior(self):
        inicio, fim = detalhe._janela_12_meses(date(2026, 10, 13))
        assert inicio == date(2025, 10, 1)
        assert fim == date(2026, 9, 30)

    def test_somar_meses_atravessa_a_virada_de_ano(self):
        assert detalhe._somar_meses(date(2025, 10, 1), 3) == date(2026, 1, 1)
        assert detalhe._somar_meses(date(2025, 11, 1), 2) == date(2026, 1, 1)

    def test_rotulo_do_mes_em_portugues(self):
        assert detalhe._mes_rotulo("2025-10") == "out/2025"
        assert detalhe._mes_rotulo("2026-01") == "jan/2026"


class TestDetalheAnual:
    def test_serie_tem_doze_meses_ordenados_e_o_rotulo_da_janela(self, anual):
        anual([], {})
        corpo = client.get(
            "/custos-administrativos-anual-detalhe", params={"data": "2026-10-13"}
        ).json()

        assert len(corpo["meses"]) == 12
        assert [m["mes"] for m in corpo["meses"]][0] == "2025-10"
        assert [m["mes"] for m in corpo["meses"]][-1] == "2026-09"
        assert corpo["janela"]["rotulo"] == "out/2025 a set/2026"
        assert corpo["janela"]["meses"] == 12

    def test_mes_sem_lancamento_vai_com_zero_e_nao_some_da_serie(self, anual):
        anual([_linha_mes("2026-09")], {})
        corpo = client.get(
            "/custos-administrativos-anual-detalhe", params={"data": "2026-10-13"}
        ).json()

        zeros = [m for m in corpo["meses"] if m["administrativo"] == 0]
        assert len(zeros) == 11
        setembro = [m for m in corpo["meses"] if m["mes"] == "2026-09"][0]
        assert setembro["administrativo"] == 100
        assert setembro["lancamentos"] == 1

    def test_total_e_media_sao_o_card_anual(self, anual):
        # 12 meses de R$ 100 = R$ 1.200 no total e R$ 100 de média.
        anual([_linha_mes(mes) for mes in MESES_FECHADOS], {})
        corpo = client.get(
            "/custos-administrativos-anual-detalhe", params={"data": "2026-10-13"}
        ).json()

        assert len(corpo["itens"]) == 12
        assert round(corpo["administrativo"]["total"], 2) == 1200.0
        assert round(corpo["administrativo"]["media"], 2) == 100.0
        assert corpo["administrativo"]["lancamentos"] == 12

    def test_faturamento_vem_da_mesma_conta_da_procedure(self, anual):
        anual([], {m: 1000 for m in ("2025-10", "2026-09")})
        corpo = client.get(
            "/custos-administrativos-anual-detalhe", params={"data": "2026-10-13"}
        ).json()

        assert round(corpo["faturamento"]["total"], 2) == 2000.0
        assert corpo["faturamento"]["media"] == pytest.approx(2000.0 / 12)
        # Só os 2 meses com faturamento entram na soma.
        assert [m["faturamento"] for m in corpo["meses"] if m["faturamento"]] == [1000.0, 1000.0]

    def test_porcentagem_do_mes_e_do_periodo(self, anual):
        anual(
            [_linha_mes("2026-09", valor="250")],
            {"2026-09": 1000, "2025-10": 3000},
        )
        corpo = client.get(
            "/custos-administrativos-anual-detalhe", params={"data": "2026-10-13"}
        ).json()

        setembro = [m for m in corpo["meses"] if m["mes"] == "2026-09"][0]
        assert round(setembro["porcentagem"], 4) == 0.25
        # Total 250 sobre 4000 de faturamento.
        assert round(corpo["faturamento"]["porcentagem"], 4) == 0.0625

    def test_porcentagem_vem_nulo_quando_nao_houve_faturamento(self, anual):
        anual([_linha_mes("2026-09")], {})
        corpo = client.get(
            "/custos-administrativos-anual-detalhe", params={"data": "2026-10-13"}
        ).json()

        assert corpo["faturamento"]["porcentagem"] is None
        assert [m for m in corpo["meses"] if m["mes"] == "2026-09"][0]["porcentagem"] is None

    def test_item_carrega_o_mes_para_o_filtro_da_tela(self, anual):
        anual([_linha_mes("2025-11", documento="DOC-NOV")], {})
        corpo = client.get(
            "/custos-administrativos-anual-detalhe", params={"data": "2026-10-13"}
        ).json()

        assert corpo["itens"][0]["mes"] == "2025-11"
        assert corpo["itens"][0]["documento"] == "DOC-NOV"

    def test_agrupamentos_somam_o_periodo_inteiro(self, anual):
        anual(
            [
                _linha_mes("2025-10", valor="100", despesa="FIXOS", razao="FOLHA"),
                _linha_mes("2026-09", valor="50", despesa="FIXOS", razao="FOLHA"),
                _linha_mes("2026-09", valor="25", despesa="VARIÁVEIS", razao="TELEFONICA"),
            ],
            {},
        )
        corpo = client.get(
            "/custos-administrativos-anual-detalhe", params={"data": "2026-10-13"}
        ).json()

        assert corpo["por_despesa"][0] == {"despesa": "FIXOS", "lancamentos": 2, "valor": 150.0}
        assert corpo["por_fornecedor"][0]["razao_social"] == "FOLHA"
        assert round(sum(g["valor"] for g in corpo["por_departamento"]), 2) == 175.0

    def test_so_aceita_departamentos_administrativos(self, anual):
        anual(
            [
                _linha_mes("2026-09", documento="DENTRO"),
                _linha_mes("2026-09", documento="FORA", dpto4=5, dpto_nome="PRODUCAO"),
            ],
            {},
        )
        corpo = client.get(
            "/custos-administrativos-anual-detalhe", params={"data": "2026-10-13"}
        ).json()

        # O filtro roda em `_buscar`, sobre os códigos 1.1.1.1/1.1.1.2.
        assert [i["documento"] for i in corpo["itens"]] == ["DENTRO"]
        assert round(corpo["administrativo"]["total"], 2) == 100.0

    def test_usa_a_whitelist_read_only(self, anual):
        from src.db.erp import assert_read_only

        assert_read_only(detalhe.SQL_DETALHE)
        assert_read_only(detalhe.SQL_FATURAMENTO_MENSAL)
