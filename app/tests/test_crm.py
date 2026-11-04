"""Testes das rotas de CRM: documentos do ERP (pedidos e faturamentos) para o dgbcomex.

O CRM precisa listar pedidos/notas do ERP para vincular a pessoa/oportunidade. As rotas leem
a carga do ERP no warehouse local (schema `raw`), entao os testes usam um engine falso: nao
dependem da carga estar made e checam o contrato (filtros, mapeamento, paginacao, corte de
empresa) que o CRM consome.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.auth.usuarios import Usuario
from src.api.main import app
from src.api.routers import crm

client = TestClient(app)


class _FakeMappings:
    def __init__(self, linhas: list[dict[str, Any]]):
        self.linhas = linhas

    def __iter__(self):
        return iter(self.linhas)

    def one_or_none(self) -> dict[str, Any] | None:
        return self.linhas[0] if self.linhas else None

    def first(self) -> dict[str, Any] | None:
        return self.linhas[0] if self.linhas else None


class _FakeResult:
    def __init__(self, linhas: list[dict[str, Any]]):
        self.linhas = linhas

    def scalar(self) -> Any:
        if not self.linhas:
            return None
        linha = self.linhas[0]
        if isinstance(linha, dict):
            valores = list(linha.values())
            return valores[0] if len(valores) == 1 else linha
        return linha

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self.linhas)


class _FakeConn:
    def __init__(self, respostas: dict[str, list[dict[str, Any]]]):
        self.respostas = respostas
        self.sqls: list[str] = []
        self.params: list[dict[str, Any]] = []

    def execute(self, sql: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        texto = str(sql)
        self.sqls.append(texto)
        self.params.append(params or {})
        for chave, linhas in self.respostas.items():
            if chave in texto:
                return _FakeResult(linhas)
        return _FakeResult([])

    def __enter__(self) -> _FakeConn:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class _FakeEngine:
    def __init__(self, respostas: dict[str, list[dict[str, Any]]]):
        self.conn = _FakeConn(respostas)

    def connect(self) -> _FakeConn:
        return self.conn


@pytest.fixture
def sem_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_AUTENTICACAO_EXIGIDA", "false")


def _ligar(
    monkeypatch: pytest.MonkeyPatch, respostas: dict[str, list[dict[str, Any]]]
) -> _FakeEngine:
    engine = _FakeEngine(respostas)
    monkeypatch.setattr(crm.warehouse, "engine", lambda: engine)
    return engine


LINHA_PEDIDO = {
    "empresa": "13",
    "pedido": "00006979",
    "cliente": "61.174.572/0001-81",
    "cliente_nome": "  LINOFORTE MOVEIS  ",
    "data_pedido": date(2026, 10, 30),
    "data_entrega": date(2026, 11, 10),
    "status": "2",
    "status_ped": " ",
    "cond_pagto": "04",
    "pedido_representante": None,
    "pedido_id": "abc123",
    "itens": 2,
    "quantidade": "100.0000",
    "valor_total": "5200.0000",
}

LINHA_ITEM_PEDIDO = {
    "item": 1,
    "produto": "000012",
    "situacao": "001",
    "cor": "00007",
    "desenho": None,
    "qtde": "100.0000",
    "unid": "MT  ",
    "vr_unitario": "6.5000000000",
    "vr_total": "650.0000",
    "status_item": " ",
    "data_entrega": date(2026, 11, 10),
}

LINHA_FATURAMENTO = {
    "empresa": "13",
    "pedido": "013294",
    "nr_nota": "012531",
    "serie": "1  55",
    "cliente": "08.661.014/0001-68",
    "cliente_nome": "CLIENTE NOTA",
    "data_nota": date(2026, 10, 5),
    "data_emissao": date(2026, 10, 5),
    "vr_nota": "4584.2600",
    "soma_itens": "4584.2600",
    "nosso_pedido": "00006783",
    "status_gravado": "S",
    "cond_pagto_extenso": None,
    "itens": 1,
    "quantidade": "300.0000",
    "valor_total": "4584.2600",
}

LINHA_ITEM_FATURAMENTO = {
    "item": 1,
    "cod_produto": "000015",
    "des_produto": "VELUDINHO",
    "unidade": "MT",
    "qtde": "300.0000",
    "metros": "300.0000",
    "vr_unitario": "15.2800000000",
    "vr_total": "4584.0000",
    "acres_desc": "0.2600",
}


class TestContrato:
    def test_rotas_publicadas(self):
        rotas = set(app.openapi()["paths"])
        for rota in (
            "/crm/pedidos",
            "/crm/pedidos/{empresa}/{pedido}",
            "/crm/faturamentos",
            "/crm/faturamentos/{empresa}/{pedido}/{nr_nota}",
        ):
            assert rota in rotas, rota

    def test_le_o_warehouse_local_e_nao_o_erp(self):
        assert "raw.car_pedido" in crm.SQL_PEDIDOS
        assert "raw.fat_pedido" in crm.SQL_FATURAMENTOS
        assert "DBMicrodata" not in crm.SQL_PEDIDOS
        assert "DBMicrodata" not in crm.SQL_FATURAMENTOS


class TestPedidos:
    def test_devolve_documento_com_cliente_e_totais(self, monkeypatch, sem_auth):
        _ligar(
            monkeypatch,
            {
                "count(*)": [{"total": 1}],
                "left join raw.car_itens_pedido": [LINHA_PEDIDO],
            },
        )
        resposta = client.get("/crm/pedidos")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["paginacao"]["total"] == 1
        item = corpo["itens"][0]
        assert item["pedido"] == "00006979"
        assert item["cliente_cnpj"] == "61.174.572/0001-81"
        assert item["cliente_nome"] == "LINOFORTE MOVEIS"
        assert item["data_pedido"] == "2026-10-30"
        assert item["valor_total"] == 5200.0
        assert item["quantidade"] == 100.0

    def test_filtro_de_cnpj_compara_apenas_digitos(self, monkeypatch, sem_auth):
        engine = _ligar(monkeypatch, {"count(*)": [{"total": 0}]})
        client.get("/crm/pedidos", params={"cnpj": "61.174.572/0001-81"})
        sql = " ".join(engine.conn.sqls)
        assert "regexp_replace(p.cliente" in sql
        params = [p for p in engine.conn.params if "cnpj" in p]
        assert params and params[0]["cnpj"] == "61174572000181"

    def test_busca_cobre_pedido_e_nome_do_cliente(self, monkeypatch, sem_auth):
        engine = _ligar(monkeypatch, {"count(*)": [{"total": 0}]})
        client.get("/crm/pedidos", params={"busca": "tecelagem"})
        sql = " ".join(engine.conn.sqls)
        assert "p.pedido ilike :busca" in sql
        assert "c.razao_nome_cliente ilike :busca" in sql
        params = [p for p in engine.conn.params if "busca" in p]
        assert params and params[0]["busca"] == "%tecelagem%"

    def test_pagina_zero_e_recusada(self, sem_auth):
        resposta = client.get("/crm/pedidos", params={"pagina": 0})
        assert resposta.status_code == 422

    def test_detalhe_soma_os_itens(self, monkeypatch, sem_auth):
        _ligar(
            monkeypatch,
            {
                "from raw.car_pedido p left join": [LINHA_PEDIDO],
                "from raw.car_itens_pedido i": [LINHA_ITEM_PEDIDO],
            },
        )
        resposta = client.get("/crm/pedidos/13/00006979")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["pedido"] == "00006979"
        assert len(corpo["itens"]) == 1
        assert corpo["itens"][0]["produto"] == "000012"
        assert corpo["itens"][0]["unidade"] == "MT"
        assert corpo["valor_total"] == 650.0

    def test_detalhe_inexistente_devolve_404(self, monkeypatch, sem_auth):
        _ligar(monkeypatch, {"from raw.car_pedido p left join": []})
        resposta = client.get("/crm/pedidos/13/99999999")
        assert resposta.status_code == 404

    def test_empresa_diferente_da_do_token_e_recusada(self):
        usuario = Usuario(
            id=1,
            email="bi@dgbcomex.com",
            nome="Bi",
            papeis=["leitura"],
            empresa="13",
            ativo=True,
            escopos=["estoque:leitura", "faturamento:leitura"],
        )
        with pytest.raises(HTTPException) as erro:
            crm.detalhe_pedido("01", "0001", empresa_consultada="01", usuario=usuario)
        assert erro.value.status_code == 403


class TestFaturamentos:
    def test_devolve_nota_com_cliente_e_valor(self, monkeypatch, sem_auth):
        _ligar(
            monkeypatch,
            {
                "count(*)": [{"total": 1}],
                "left join raw.fat_itens_pedido": [LINHA_FATURAMENTO],
            },
        )
        resposta = client.get("/crm/faturamentos")
        assert resposta.status_code == 200
        item = resposta.json()["itens"][0]
        assert item["nr_nota"] == "012531"
        assert item["cliente_cnpj"] == "08.661.014/0001-68"
        assert item["data_nota"] == "2026-10-05"
        assert item["valor_nota"] == 4584.26

    def test_detalhe_soma_itens_com_acrescimo(self, monkeypatch, sem_auth):
        _ligar(
            monkeypatch,
            {
                "from raw.fat_pedido p left join": [LINHA_FATURAMENTO],
                "from raw.fat_itens_pedido i": [LINHA_ITEM_FATURAMENTO],
            },
        )
        resposta = client.get("/crm/faturamentos/13/013294/012531")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["itens"][0]["descricao"] == "VELUDINHO"
        assert corpo["valor_total"] == pytest.approx(4584.26)

    def test_detalhe_inexistente_devolve_404(self, monkeypatch, sem_auth):
        _ligar(monkeypatch, {"from raw.fat_pedido p left join": []})
        resposta = client.get("/crm/faturamentos/13/013294/999999")
        assert resposta.status_code == 404
