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


def _faturamento_mes(mes: str, total: str) -> dict:
    ano, m = mes.split("-")
    return {"mes": date(int(ano), int(m), 1), "total": Decimal(total)}


def _classificacao(
    documento: str = "000007424U",
    serie: str = "U   ",
    fornecedor: str = "00055",
    razao: str = "MF LOG TRANSPORTES LTDA",
    empresa: str = "13",
    parcela: str = "01",
    baixa: str = "2026-09-30",
    dpto: str = "TRANSPORTE",
    cod_dpto: tuple[int, int, int, int] = (1, 1, 5, 1),
    despesa: str = "FIXOS VARIAVEIS",
    despesa_2: str = "IMPORTACAO",
    valor: str = "2068.73",
) -> dict:
    """Linha da `sp_PagRel_CCusto_Niveis` — documento já vem com a série grudada."""
    return {
        "Empresa": empresa,
        "Documento": documento,
        "CodFornecedor": fornecedor,
        "Razao_Nome_Cliente": razao,
        "PArcela": parcela,
        "Data_Baixa": datetime.fromisoformat(baixa),
        "DescDpto4": dpto,
        "CodDpto1": cod_dpto[0],
        "CodDpto2": cod_dpto[1],
        "CodDpto3": cod_dpto[2],
        "CodDpto4": cod_dpto[3],
        "DescDesp1": despesa,
        "DescDesp2": despesa_2,
        "Valor_Baixado": Decimal(valor),
    }


@pytest.fixture(autouse=True)
def sem_auth(monkeypatch):
    monkeypatch.setenv("API_AUTENTICACAO_EXIGIDA", "false")


@pytest.fixture
def erp_mock(monkeypatch):
    """Separa as três consultas: série mensal, itens do recorte e classificação.

    `ultimo_resultado` abre a própria conexão (por isso a procedure do centro de
    custo), então precisa ser mockado à parte — sem isso o teste iria no ERP de
    verdade só para descobrir que não há classificação.
    """

    def montar(itens, serie, classificacoes=(), faturamento=(), faturamento_intervalo="0"):
        chamadas: list[tuple[str, tuple]] = []

        def query(sql: str, params=None):
            if sql is detalhe.SQL_SERIE:
                tipo, dados = "serie", list(serie)
            elif sql is detalhe.SQL_FATURAMENTO_MENSAL:
                tipo, dados = "faturamento_mensal", list(faturamento)
            elif sql is detalhe.SQL_FATURAMENTO_INTERVALO:
                tipo, dados = "faturamento_intervalo", [{"total": Decimal(faturamento_intervalo)}]
            else:
                tipo, dados = "itens", list(itens)
            chamadas.append((tipo, tuple(params or ())))
            return dados

        def ultimo_resultado(sql: str, params=None):
            chamadas.append(("classificacao", tuple(params or ())))
            return list(classificacoes)

        monkeypatch.setattr(detalhe.erp, "query", query)
        monkeypatch.setattr(detalhe.erp, "ultimo_resultado", ultimo_resultado)
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
        erp_mock([_linha(valor="-120.50")], [_serie_mes("2026-10", "-120.50", 1)])
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

    def test_usa_uma_consulta_de_serie_uma_de_itens_e_una_de_classificacao(self, erp_mock):
        chamadas = erp_mock([_linha()], [_serie_mes("2026-10", "2068.73")])
        client.get("/contas-pagas-detalhe", params={"data": "2026-10-13"}).json()
        tipos = [tipo for tipo, _ in chamadas]
        # Uma consulta de série, uma de itens, uma de faturamento e a classificação.
        assert tipos == ["serie", "faturamento_mensal", "itens", "classificacao"]
        # A classificação cobre a mesma janela dos itens — senão o departamento viria
        # de outro período e o card não fecharia. A procedure recebe o fim de novo
        # como @DatRetr.
        janela_itens = chamadas[2][1]
        assert chamadas[3][1] == janela_itens + (janela_itens[1],)


class TestWhitelist:
    def test_as_consultas_passam_pelo_guard_de_leitura(self):
        from src.db.erp import assert_read_only

        assert_read_only(detalhe.SQL_SERIE)
        assert_read_only(detalhe.SQL_ITENS)
        assert_read_only(detalhe.SQL_CLASSIFICACAO)
        assert_read_only(detalhe.SQL_FATURAMENTO_MENSAL)
        assert_read_only(detalhe.SQL_FATURAMENTO_INTERVALO)

    def test_as_consultas_so_leem_nas_tabelas_da_base(self):
        for sql in (
            detalhe.SQL_SERIE,
            detalhe.SQL_ITENS,
            detalhe.SQL_CLASSIFICACAO,
            detalhe.SQL_FATURAMENTO_MENSAL,
            detalhe.SQL_FATURAMENTO_INTERVALO,
        ):
            baixo = sql.lower()
            assert "insert" not in baixo
            assert "update " not in baixo
            assert "delete" not in baixo
            assert "truncate" not in baixo


class TestRecorteDeDatas:
    """`data_inicio`/`data_fim` recortam a lista; os cards continuam do mês âncora."""

    def test_sem_datas_a_lista_e_o_mes_inteiro(self, erp_mock):
        erp_mock([_linha()], [_serie_mes("2026-09", "2068.73", 1)])
        corpo = client.get(
            "/contas-pagas-detalhe", params={"data": "2026-09-15"}
        ).json()

        assert corpo["periodo"]["periodo"] == "01/09/2026 a 30/09/2026"
        assert corpo["periodo"]["recorte"] is False
        assert corpo["mes"]["periodo"] == "01/09/2026 a 30/09/2026"

    def test_o_intervalo_traz_somente_o_periodo_pedido(self, erp_mock):
        chamadas = erp_mock([_linha()], [_serie_mes("2026-09", "2068.73", 1)])
        corpo = client.get(
            "/contas-pagas-detalhe",
            params={"data_inicio": "2026-08-15", "data_fim": "2026-09-10"},
        ).json()

        assert corpo["periodo"]["periodo"] == "15/08/2026 a 10/09/2026"
        assert corpo["periodo"]["recorte"] is True
        # `data_fim` é inclusivo: vira dia seguinte exclusivo no SQL.
        janela = [p for tipo, p in chamadas if tipo == "itens"][0]
        assert janela == (date(2026, 8, 15), date(2026, 9, 11))

    def test_data_inicio_depois_de_data_fim_e_recusado(self, erp_mock):
        erp_mock([_linha()], [_serie_mes("2026-09", "2068.73", 1)])
        resposta = client.get(
            "/contas-pagas-detalhe",
            params={"data_inicio": "2026-09-10", "data_fim": "2026-09-01"},
        )

        assert resposta.status_code == 422
        assert "data_inicio" in resposta.json()["detail"]


class TestMinDataEPeriodo:
    """`min_data` alimenta a data inicial da tela; `periodo` é o 5º card."""

    def test_min_data_e_a_primeira_baixa_do_conjunto(self, erp_mock):
        erp_mock(
            [
                _linha(documento="A", baixa="2026-09-30"),
                _linha(documento="B", baixa="2026-08-15"),
                _linha(documento="C", baixa="2026-09-02"),
            ],
            [],
        )
        corpo = client.get(
            "/contas-pagas-detalhe",
            params={"data_inicio": "2026-08-01", "data_fim": "2026-09-30"},
        ).json()

        assert corpo["min_data"] == "2026-08-15"

    def test_sem_baixas_min_data_e_nula(self, erp_mock):
        erp_mock([], [_serie_mes("2026-09", "0", 0)])
        corpo = client.get("/contas-pagas-detalhe", params={"data": "2026-09-15"}).json()

        assert corpo["min_data"] is None

    def test_periodo_traz_total_e_contagem_do_intervalo(self, erp_mock):
        erp_mock(
            [
                _linha(documento="A", valor="100", baixa="2026-08-15"),
                _linha(documento="B", valor="250", baixa="2026-09-10"),
            ],
            [],
        )
        corpo = client.get(
            "/contas-pagas-detalhe",
            params={"data_inicio": "2026-08-01", "data_fim": "2026-09-30"},
        ).json()

        assert corpo["periodo"]["total"] == 350.0
        assert corpo["periodo"]["lancamentos"] == 2
        # O card "Mês atual" é a janela fixa do mês âncora (hoje), não a lista:
        # com recorte/sem `data`, a lista é o período e não pode inflar o card.
        assert corpo["mes"]["total"] == 0.0

    def test_mes_atual_e_a_janela_fixa_mesmo_com_recorte(self, erp_mock):
        erp_mock(
            [_linha(documento="A", valor="100", baixa="2026-08-15")],
            [_serie_mes("2026-10", "500", 3)],
        )
        corpo = client.get(
            "/contas-pagas-detalhe",
            params={
                "data": "2026-10-13",
                "data_inicio": "2026-08-01",
                "data_fim": "2026-08-31",
            },
        ).json()

        # A lista é agosto (recorte), mas o card do mês âncora é outubro.
        assert corpo["periodo"]["total"] == 100.0
        assert corpo["mes"]["total"] == 500.0
        assert corpo["mes"]["lancamentos"] == 3

    def test_modo_todos_sem_data_usa_o_intervalo_e_ancora_os_cards_em_hoje(self, erp_mock):
        # Sem `data`, os 4 cards fixos usam o mês corrente; a lista é o intervalo.
        erp_mock(
            [
                _linha(documento="A", valor="100", baixa="2026-03-15"),
                _linha(documento="B", valor="250", baixa="2026-07-10"),
            ],
            [_serie_mes("2026-07", "250", 1)],
        )
        corpo = client.get(
            "/contas-pagas-detalhe",
            params={"data_inicio": "2026-01-01", "data_fim": "2026-07-31"},
        ).json()

        assert corpo["referencia"]["mes"] == date.today().strftime("%Y-%m")
        # A lista é o intervalo inteiro (2 baixas)...
        assert len(corpo["mes"]["itens"]) == 2
        # ...mas o card "Mês atual" é a janela de hoje, não a lista.
        assert corpo["mes"]["lancamentos"] == 0
        assert corpo["periodo"]["recorte"] is True
        assert corpo["periodo"]["total"] == 350.0


class TestClassificacao:
    def test_a_baixa_recebe_departamento_e_despesa(self, erp_mock):
        erp_mock(
            [_linha(valor="2068.73")],
            [_serie_mes("2026-09", "2068.73", 1)],
            [_classificacao(valor="2068.73")],
        )
        corpo = client.get(
            "/contas-pagas-detalhe", params={"data": "2026-09-15"}
        ).json()

        item = corpo["mes"]["itens"][0]
        assert item["departamento"] == "TRANSPORTE"
        assert item["departamento_codigo"] == "1.1.5.1"
        assert item["despesa"] == "FIXOS VARIAVEIS"
        assert item["despesa_2"] == "IMPORTACAO"
        assert item["rateio"] is False

    def test_baixa_sem_classificacao_agrupa_como_traco(self, erp_mock):
        erp_mock(
            [_linha(valor="2068.73")],
            [_serie_mes("2026-09", "2068.73", 1)],
            [],
        )
        corpo = client.get(
            "/contas-pagas-detalhe", params={"data": "2026-09-15"}
        ).json()

        item = corpo["mes"]["itens"][0]
        assert item["departamento"] == ""
        assert [g["departamento"] for g in corpo["mes"]["por_departamento"]] == ["—"]

    def test_rateio_fica_com_a_linha_maior_e_marca_a_baixa(self, erp_mock):
        # Mesma chave nas duas linhas: a baixa fica com a maior e avisa que houve
        # rateio, para a tela não apresentar um departamento como se fosse o todo.
        erp_mock(
            [_linha(valor="9208.48")],
            [_serie_mes("2026-09", "9208.48", 1)],
            [
                _classificacao(dpto="IMPORTACAO", cod_dpto=(1, 1, 6, 1), valor="2482.58"),
                _classificacao(dpto="TRANSPORTE", cod_dpto=(1, 1, 5, 1), valor="9208.48"),
            ],
        )
        corpo = client.get(
            "/contas-pagas-detalhe", params={"data": "2026-09-15"}
        ).json()

        item = corpo["mes"]["itens"][0]
        assert item["departamento"] == "TRANSPORTE"
        assert item["rateio"] is True

    def test_grupos_somam_o_valor_pago_das_baixas(self, erp_mock):
        # O rateio da procedure traz 11.691,06 para uma baixa de 9.208,48. O grupo
        # tem de somar os 9.208,48, senão a tela mostra um total que não bate com o
        # card de contas pagas.
        erp_mock(
            [_linha(valor="9208.48"), _linha(documento="X", valor="1000")],
            [_serie_mes("2026-09", "10208.48", 2)],
            [
                _classificacao(dpto="TRANSPORTE", cod_dpto=(1, 1, 5, 1), valor="2482.58"),
                _classificacao(dpto="TRANSPORTE", cod_dpto=(1, 1, 5, 1), valor="9208.48"),
                _classificacao(
                    documento="XU", dpto="IMPORTACAO", cod_dpto=(1, 1, 6, 1), valor="1000"
                ),
            ],
        )
        corpo = client.get(
            "/contas-pagas-detalhe", params={"data": "2026-09-15"}
        ).json()

        soma = sum(g["valor"] for g in corpo["mes"]["por_departamento"])
        assert round(soma, 2) == round(corpo["mes"]["total"], 2)
        assert corpo["mes"]["total"] == pytest.approx(10208.48)

    def test_o_periodo_alimentado_por_departamento_e_despesa_existe(self, erp_mock):
        erp_mock(
            [_linha(valor="100")],
            [_serie_mes("2026-09", "100", 1)],
            [_classificacao(valor="100")],
        )
        corpo = client.get(
            "/contas-pagas-detalhe", params={"data": "2026-09-15"}
        ).json()

        assert corpo["mes"]["por_departamento"][0]["departamento"] == "TRANSPORTE"
        assert corpo["mes"]["por_despesa"][0]["despesa"] == "FIXOS VARIAVEIS"
        assert corpo["mes"]["por_fornecedor"][0]["lancamentos"] == 1


class TestFaturamento:
    """O faturamento base é o do `vwFaturamento` (Σ Vr_Total + Σ Acres_Desc).

    Cada janela e o `periodo` trazem `faturamento`, que é o denominador da razão
    pagamento ÷ faturamento usada pelos cards e pelos dois gráficos de participação.
    """

    def test_cada_janela_traz_o_faturamento_do_mesmo_periodo(self, erp_mock):
        erp_mock(
            [_linha(valor="150")],
            [_serie_mes("2026-10", "150", 1)],
            faturamento=[
                _faturamento_mes("2025-06", "4000"),
                _faturamento_mes("2026-09", "2000"),
                _faturamento_mes("2026-10", "3000"),
            ],
        )
        corpo = client.get(
            "/contas-pagas-detalhe", params={"data": "2026-10-13"}
        ).json()

        assert corpo["mes"]["faturamento"] == 3000.0
        assert corpo["mes_anterior"]["faturamento"] == 2000.0
        # Ano atual: jan a dez/2026 (só os meses que têm faturamento na lista).
        assert corpo["ano_atual"]["faturamento"] == 5000.0
        # Ano anterior: 2025 inteiro.
        assert corpo["ano_anterior"]["faturamento"] == 4000.0

    def test_periodo_do_recorte_fecha_mes_usa_a_janela(self, erp_mock):
        # Sem `data_inicio`/`data_fim` a lista é o mês âncora: o faturamento do
        # `periodo` é o da janela do mês, sem ir no intervalo.
        chamadas = erp_mock(
            [_linha(valor="150")],
            [_serie_mes("2026-10", "150", 1)],
            faturamento=[_faturamento_mes("2026-10", "3000")],
        )
        corpo = client.get(
            "/contas-pagas-detalhe", params={"data": "2026-10-13"}
        ).json()

        assert corpo["periodo"]["faturamento"] == 3000.0
        tipos = [tipo for tipo, _ in chamadas]
        assert "faturamento_intervalo" not in tipos

    def test_recorte_arbitrario_usa_a_soma_do_intervalo(self, erp_mock):
        # Trimestre/dia a dia: o faturamento vem da soma direta no intervalo, não da
        # soma de meses inteiros (que inflaria o denominador).
        chamadas = erp_mock(
            [_linha(valor="350")],
            [_serie_mes("2026-08", "350", 1)],
            faturamento=[_faturamento_mes("2026-08", "9999")],
            faturamento_intervalo="1234.56",
        )
        corpo = client.get(
            "/contas-pagas-detalhe",
            params={"data_inicio": "2026-08-15", "data_fim": "2026-09-10"},
        ).json()

        assert corpo["periodo"]["faturamento"] == 1234.56
        janela_intervalo = [p for tipo, p in chamadas if tipo == "faturamento_intervalo"][0]
        assert janela_intervalo == (date(2026, 8, 15), date(2026, 9, 11))

    def test_sem_faturamento_no_periodo_e_zero(self, erp_mock):
        erp_mock([_linha(valor="150")], [_serie_mes("2026-10", "150", 1)])
        corpo = client.get(
            "/contas-pagas-detalhe", params={"data": "2026-10-13"}
        ).json()

        assert corpo["mes"]["faturamento"] == 0.0
        assert corpo["periodo"]["faturamento"] == 0.0

