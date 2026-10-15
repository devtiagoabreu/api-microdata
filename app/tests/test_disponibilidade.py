"""Testes da rota de disponibilidade comercial: estoque + compra em transito - carteira.

Nao toca em banco: as tres consultas sao interceptadas com `monkeypatch`, porque o que
importa aqui e a **regra** (juntar as tres fontes por produto x cor e calcular o
liquido), nao o conteudo do ERP.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routers import disponibilidade
from src.db import erp

client = TestClient(app)


def estoque_falso(
    produto: str = "000014",
    cor: str = "00005",
    metros: float = 91.0,
    pecas: int = 4,
    rolos: int = 2,
    desc: str = "VELUDO CONFORT",
    cor_desc: str = "5 - BLACK",
) -> dict:
    return {
        "produto": produto,
        "produto_desc": desc,
        "cor": cor,
        "cor_desc": cor_desc,
        "metros": metros,
        "pecas": pecas,
        "rolos": rolos,
    }


def caminho_falso(
    produto: str = "000014",
    cor: str = "00005",
    metros: float = 8_400.0,
    primeira: date | None = None,
    pedidos: int = 1,
) -> dict:
    return {
        "produto": produto,
        "cor": cor,
        "metros": metros,
        "primeira_chegada": primeira or date.today() + timedelta(days=20),
        "ultima_chegada": date.today() + timedelta(days=30),
        "pedidos": pedidos,
    }


def carteira_falsa(
    produto: str = "000014",
    cor: str = "00005",
    vendedor: str = "058",
    nome: str = "ANA SOUZA",
    saldo: float = 1_000.0,
    valor: float = 12_000.0,
    pedidos: int = 2,
) -> dict:
    return {
        "produto": produto,
        "cor": cor,
        "vendedor": vendedor,
        "vendedor_nome": nome,
        "pedidos": pedidos,
        "saldo": saldo,
        "valor": valor,
    }


@pytest.fixture
def fontes(monkeypatch):
    """Instala as tres fontes e devolve o dicionario para o teste ajustar."""
    dados = {"estoque": [], "caminho": [], "carteira": [], "sqls": []}

    def consultar_estoque(filtros):
        dados["sqls"].append((disponibilidade.SQL_ESTOQUE, list(filtros)))
        return dados["estoque"]

    def consultar_erp(sql, filtros):
        dados["sqls"].append((sql, list(filtros)))
        if sql is disponibilidade.SQL_CAMINHO:
            return dados["caminho"]
        return dados["carteira"]

    monkeypatch.setattr(disponibilidade, "_consultar_estoque", consultar_estoque)
    monkeypatch.setattr(disponibilidade, "_consultar_erp", consultar_erp)
    return dados


class TestRegra:
    def test_livre_e_cobertura(self, fontes):
        fontes["estoque"] = [estoque_falso(metros=1_000.0)]
        fontes["caminho"] = [caminho_falso(metros=500.0)]
        fontes["carteira"] = [carteira_falsa(saldo=1_500.0, valor=20_000.0)]

        corpo = client.get("/estoque-disponibilidade").json()

        assert corpo["resumo"]["produtos_cor"] == 1
        linha = corpo["linhas"][0]
        assert linha["estoque_metros"] == 1_000.0
        assert linha["caminho_metros"] == 500.0
        assert linha["prometido_metros"] == 1_500.0
        # prometeu 500 a mais do que tem: falta 500, e a compra cobre exatamente isso
        assert linha["livre_metros"] == -500.0
        assert linha["falta_metros"] == 500.0
        assert linha["cobertura_metros"] == 0.0
        assert corpo["resumo"]["com_falta"] == 1

    def test_soma_o_estoque_das_duas_fontes(self, fontes):
        # Uma cor pode estar em varias empresas: o group by da rota soma tudo que veio.
        fontes["estoque"] = [
            estoque_falso(metros=600.0, pecas=3, rolos=1),
            estoque_falso(metros=400.0, pecas=2, rolos=2),
        ]
        fontes["carteira"] = [
            carteira_falsa(saldo=200.0),
            carteira_falsa(saldo=100.0, vendedor="031"),
        ]

        corpo = client.get("/estoque-disponibilidade").json()

        assert len(corpo["linhas"]) == 1
        linha = corpo["linhas"][0]
        assert linha["estoque_metros"] == 1_000.0
        assert linha["estoque_pecas"] == 5
        assert linha["estoque_rolos"] == 3
        assert linha["prometido_metros"] == 300.0
        # o breakdown por representante vem ordenado pelo maior saldo
        assert [r["vendedor"] for r in linha["por_representante"]] == ["058", "031"]

    def test_cor_so_na_carteira_entra_na_resposta(self, fontes):
        # Estoque zero e sem compra ainda e promessa: e exatamente a cor que falta.
        fontes["carteira"] = [
            carteira_falsa(produto="000020", cor="00011", saldo=27_300.0, valor=500_000.0)
        ]

        corpo = client.get("/estoque-disponibilidade").json()

        linha = corpo["linhas"][0]
        assert linha["produto"] == "000020" and linha["cor"] == "00011"
        assert linha["estoque_metros"] == 0.0
        assert linha["falta_metros"] == 27_300.0

    def test_busca_o_nome_no_catalogo_quando_falta(self, fontes, monkeypatch):
        # Cor prometida e ainda nao comprada nao tem peca, entao nao passa pelo join do
        # estoque e voltava com codigo. A rota tem que buscar o nome no cadastro.
        fontes["carteira"] = [
            carteira_falsa(produto="000020", cor="00042", saldo=4_120.0)
        ]
        fontes["estoque"] = []  # sem peca: nao vem nome por este caminho

        pedidos: list[tuple[str, tuple]] = []

        def consulta(sql, params):
            pedidos.append((sql, tuple(params)))
            # O `format` dos marcadores devolve uma string nova, entao o match e por conteudo.
            if "Produtos p" in sql:
                return [{"codigo": "000020", "descricao": "VELUDO SILVER"}]
            if "Car_Cores c" in sql:
                return [{"codigo": "00042", "descricao": "42 - OFF WHITE"}]
            raise AssertionError(f"SQL inesperado: {sql}")

        monkeypatch.setattr(disponibilidade.erp, "query", consulta)

        linha = client.get("/estoque-disponibilidade").json()["linhas"][0]

        assert linha["produto_desc"] == "VELUDO SILVER"
        assert linha["cor_desc"] == "42 - OFF WHITE"
        # Um marcador por codigo, nao a lista repetida
        consulta_produto = next(p for sql, p in pedidos if "Produtos p" in sql)
        assert consulta_produto == ("000020",)

    def test_nao_consulta_catalogo_quando_tem_nome(self, fontes, monkeypatch):
        fontes["estoque"] = [estoque_falso(desc="VELUDO CONFORT", cor_desc="5 - BLACK")]

        def consulta(sql, params):  # pragma: no cover - nao deve ser chamado
            raise AssertionError(f"SQL inesperado: {sql}")

        monkeypatch.setattr(disponibilidade.erp, "query", consulta)

        linha = client.get("/estoque-disponibilidade").json()["linhas"][0]
        assert linha["produto_desc"] == "VELUDO CONFORT"

    def test_so_com_falta_e_um_pos_filtro(self, fontes):
        fontes["estoque"] = [
            estoque_falso(cor="00005", metros=5_000.0),
            estoque_falso(cor="00014", metros=10.0),
        ]
        fontes["carteira"] = [
            carteira_falsa(cor="00005", saldo=1_000.0),
            carteira_falsa(cor="00014", saldo=9_000.0),
        ]

        corpo = client.get("/estoque-disponibilidade?so_com_falta=true").json()

        assert [linha["cor"] for linha in corpo["linhas"]] == ["00014"]
        assert corpo["resumo"]["produtos_cor"] == 1

    def test_so_chegando_filtra_pela_compra(self, fontes):
        fontes["estoque"] = [
            estoque_falso(cor="00005", metros=5_000.0),
            estoque_falso(cor="00014", metros=10.0),
        ]
        fontes["caminho"] = [caminho_falso(cor="00014", metros=2_000.0)]

        corpo = client.get("/estoque-disponibilidade?so_chegando=true").json()

        assert [linha["cor"] for linha in corpo["linhas"]] == ["00014"]
        assert corpo["linhas"][0]["primeira_chegada"] is not None

    def test_ordem_coloca_a_maior_falta_primeiro(self, fontes):
        fontes["estoque"] = [
            estoque_falso(cor="00005", metros=0.0),
            estoque_falso(cor="00014", metros=1_000.0),
        ]
        fontes["carteira"] = [
            carteira_falsa(cor="00005", saldo=100.0),
            carteira_falsa(cor="00014", saldo=20_000.0),
        ]

        corpo = client.get("/estoque-disponibilidade").json()

        assert [linha["cor"] for linha in corpo["linhas"]] == ["00014", "00005"]

    def test_filtros_viram_where_e_parametro(self, fontes):
        client.get("/estoque-disponibilidade?produto=000014&cor=00005&representante=058")

        sqls = {sql: filtros for sql, filtros in fontes["sqls"]}
        estoque = sqls[disponibilidade.SQL_ESTOQUE]
        caminho = sqls[disponibilidade.SQL_CAMINHO]
        carteira = sqls[disponibilidade.SQL_CARTEIRA]

        # O warehouse usa `:nome` + dicionario; o ERP usa `?` posicional. Misturar quebra.
        assert estoque == [
            ("produto = :produto", "produto", "000014"),
            ("cor = :cor", "cor", "00005"),
        ]
        assert caminho == [("rtrim(i.Produto) = ?", "000014"), ("rtrim(i.Cor) = ?", "00005")]
        # o representante so entra na carteira: e a unica fonte que tem vendedor
        assert carteira[-1] == ("rtrim(q.Vendedor) = ?", "058")

    def test_corte_por_empresa(self, fontes, monkeypatch):
        monkeypatch.setattr(
            disponibilidade, "empresa_efetiva", lambda usuario, pedida: pedida or "13"
        )

        client.get("/estoque-disponibilidade")

        sqls = {sql: filtros for sql, filtros in fontes["sqls"]}
        assert sqls[disponibilidade.SQL_ESTOQUE][0] == ("empresa = :empresa", "empresa", "13")
        assert sqls[disponibilidade.SQL_CAMINHO][0] == ("p.Empresa = ?", "13")
        assert sqls[disponibilidade.SQL_CARTEIRA][0] == ("q.Empresa = ?", "13")

    def test_sem_empresa_nao_filtra(self, fontes, monkeypatch):
        monkeypatch.setattr(disponibilidade, "empresa_efetiva", lambda usuario, pedida: None)

        client.get("/estoque-disponibilidade")

        assert all(not filtros for _, filtros in fontes["sqls"])

    def test_resumo_fecha_com_as_linhas(self, fontes):
        fontes["estoque"] = [estoque_falso(metros=100.0), estoque_falso(cor="00014", metros=250.0)]
        fontes["caminho"] = [caminho_falso(cor="00014", metros=400.0)]
        fontes["carteira"] = [carteira_falsa(saldo=60.0, valor=1_000.0)]

        resumo = client.get("/estoque-disponibilidade").json()["resumo"]

        assert resumo["total_estoque"] == 350.0
        assert resumo["total_caminho"] == 400.0
        assert resumo["total_prometido"] == 60.0
        assert resumo["produtos_cor"] == 2


class TestPedidos:
    def pedido(self, over=None) -> dict:
        base = {
            "empresa": "13",
            "pedido": "00006862",
            "cliente": "07.920.906/0001-73",
            "cliente_nome": "TECIDOS ABC",
            "vendedor": "055",
            "vendedor_nome": "ANA SOUZA",
            "produto": "000014",
            "cor": "00005",
            "data_pedido": date(2026, 10, 14),
            "data_entrega": date(2026, 11, 17),
            "qtde_pedido": 1_843.2,
            "qtde_romaneada": 0.0,
            "saldo": 1_843.2,
            "valor": 12_165.12,
            "status": "Analise Financeira",
        }
        return {**base, **(over or {})}

    def _mock(self, linhas, monkeypatch):
        def consultar(sql, filtros):
            assert sql is disponibilidade.SQL_PEDIDOS
            return linhas

        monkeypatch.setattr(disponibilidade, "_consultar_erp", consultar)

    def test_devolve_o_codigo_do_pedido_e_o_cliente(self, monkeypatch):
        self._mock([self.pedido()], monkeypatch)

        corpo = client.get("/estoque-disponibilidade/pedidos?produto=000014&cor=00005").json()

        assert corpo["total"] == 1
        pedido = corpo["pedidos"][0]
        # o que a tela nao tinha: o codigo do pedido
        assert pedido["pedido"] == "00006862"
        assert pedido["cliente_nome"] == "TECIDOS ABC"
        assert pedido["vendedor_nome"] == "ANA SOUZA"
        assert pedido["saldo"] == 1_843.2
        assert pedido["data_entrega"] == "2026-11-17"
        assert corpo["valor"] == 12_165.12

    def test_ignora_item_sem_saldo(self, monkeypatch):
        # Item ja romaneado nao promete nada: nao entra na conversa de cobranca.
        self._mock([self.pedido(), self.pedido({"pedido": "00006863", "saldo": 0.0})], monkeypatch)

        corpo = client.get("/estoque-disponibilidade/pedidos").json()

        assert corpo["total"] == 1
        assert corpo["pedidos"][0]["pedido"] == "00006862"

    def test_ordena_do_pedido_mais_recente(self, monkeypatch):
        self._mock(
            [
                self.pedido({"pedido": "00006862", "data_pedido": date(2026, 10, 1)}),
                self.pedido({"pedido": "00006899", "data_pedido": date(2026, 10, 14)}),
            ],
            monkeypatch,
        )

        pedidos = client.get("/estoque-disponibilidade/pedidos").json()["pedidos"]

        assert [p["pedido"] for p in pedidos] == ["00006899", "00006862"]

    def test_filtros_viram_parametros(self, monkeypatch):
        vistos: list = []

        def consultar(sql, filtros):
            vistos.extend(filtros)
            return []

        monkeypatch.setattr(disponibilidade, "_consultar_erp", consultar)
        monkeypatch.setattr(disponibilidade, "empresa_efetiva", lambda usuario, pedida: "13")

        client.get("/estoque-disponibilidade/pedidos?produto=000014&cor=00005")

        assert vistos == [
            ("q.Empresa = ?", "13"),
            ("rtrim(q.Produto) = ?", "000014"),
            ("rtrim(q.Cor) = ?", "00005"),
        ]

    def test_sql_dos_pedidos_e_somente_leitura(self):
        assert "Vw_Saldo_Pedido_Carteira_Qlik" in disponibilidade.SQL_PEDIDOS
        assert "Clientes_Principal" in disponibilidade.SQL_PEDIDOS
        erp.assert_read_only(disponibilidade.SQL_PEDIDOS.replace("{onde}", ""))


class TestContrato:
    def test_rota_publicada(self):
        assert "/estoque-disponibilidade" in app.openapi()["paths"]

    def test_sql_do_erp_e_somente_leitura(self):
        for sql in (
            disponibilidade.SQL_CAMINHO,
            disponibilidade.SQL_CARTEIRA,
            disponibilidade.SQL_CATALOGO_PRODUTOS,
            disponibilidade.SQL_CATALOGO_CORES,
        ):
            erp.assert_read_only(sql.replace("{marcadores}", "?").replace("{onde}", ""))

    def test_a_compra_em_transito_so_olha_entrega_futura(self):
        assert "p.Data_Entrega >= getdate()" in disponibilidade.SQL_CAMINHO
        # pendencia: o que ja foi recebido nao entra como "a caminho"
        assert "Qtde_Recebida" in disponibilidade.SQL_CAMINHO

    def test_a_carteira_usa_a_view_valida(self):
        # `vw_saldocarteira`/`VW_RELSALCARTEIRA` vem do CFC, que esta vazio (Estudo 20).
        assert "Vw_Saldo_Pedido_Carteira_Qlik" in disponibilidade.SQL_CARTEIRA

    def test_caminho_usa_qtde_e_nao_metros(self):
        # `Cmt_Pedido_Itens.metros` esta zerado na base: a unidade esta em `Qtde`.
        assert "isnull(e.Qtde, i.Qtde)" in disponibilidade.SQL_CAMINHO
        assert "i.metros" not in disponibilidade.SQL_CAMINHO
