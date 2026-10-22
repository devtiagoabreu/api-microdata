"""WMS na api-microdata: enderecos, alocacao e movimentos no Postgres local.

A suite roda contra o `dgbcomex_warehouse` real (como as demais), mas so com dados de teste
identificados por um sufixo aleatorio: no teardown as linhas criadas sao apagadas. O estoque
em aberto vem do `raw` (ERP), que nao e tocado.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from src.api.auth import tokens
from src.api.auth.escopos import ESCOPO_ESTOQUE
from src.api.auth.usuarios import Usuario
from src.api.main import app
from src.config import get_settings
from src.db import warehouse

client = TestClient(app)


@pytest.fixture
def sufixo() -> str:
    return uuid4().hex[:10].upper()


@pytest.fixture
def limpar(sufixo: str):
    """Remove tudo que o teste criou (movimentos, estoque e enderecos)."""
    marcador = f"TESTE-WMS-{sufixo}"
    yield marcador
    with warehouse.engine().begin() as conn:
        conn.execute(
            text("delete from public.wms_movimentos where nro_rolo like :padrao"),
            {"padrao": f"{marcador}%"},
        )
        conn.execute(
            text("delete from public.wms_estoque where nro_rolo like :padrao"),
            {"padrao": f"{marcador}%"},
        )
        conn.execute(
            text("delete from public.wms_enderecos where codigo like :padrao"),
            {"padrao": f"{marcador}%"},
        )


def _endereco(codigo: str, tipo: str = "PULMAO", **extra: Any) -> dict[str, Any]:
    return {"codigo": codigo, "tipo": tipo, **extra}


def _entrada(marcador: str, endereco_id: int, **extra: Any) -> dict[str, Any]:
    return {
        "tipo": "ENTRADA",
        "enderecoDestinoId": endereco_id,
        "usuarioId": 42,
        "peca": {
            "empresa": "13",
            "nroRolo": marcador,
            "nroPeca": "1",
            "produto": "TECIDO",
            "cor": "PRETO",
            "largura": "1,40",
            "metros": 12.5,
            "peso": 3.2,
            "loteInterno": marcador,
            "dataEntrada": "2026-01-02",
        },
        **extra,
    }


class TestEnderecos:
    def test_lista(self):
        resposta = client.get("/wms/enderecos")
        assert resposta.status_code == 200
        assert isinstance(resposta.json(), list)

    def test_codigo_obrigatorio(self):
        resposta = client.post("/wms/enderecos", json={"codigo": "   "})
        assert resposta.status_code == 400
        assert "obrigat" in resposta.json()["detail"]

    def test_tipo_invalido_cai_em_pulmao(self, limpar):
        resposta = client.post(
            "/wms/enderecos", json=_endereco(limpar, tipo="INVALIDO")
        )
        assert resposta.status_code == 201
        assert resposta.json()["tipo"] == "PULMAO"
        assert resposta.json()["capacidade"] is None

    def test_capacidade_numerica_sai_como_texto(self, limpar):
        resposta = client.post(
            "/wms/enderecos", json=_endereco(limpar, capacidade=1500.5)
        )
        assert resposta.status_code == 201
        assert resposta.json()["capacidade"] == "1500.50"

    def test_codigo_duplicado_da_409(self, limpar):
        assert client.post("/wms/enderecos", json=_endereco(limpar)).status_code == 201
        resposta = client.post("/wms/enderecos", json=_endereco(limpar))
        assert resposta.status_code == 409
        assert "código" in resposta.json()["detail"]


class TestFluxoDeMovimentos:
    def test_entrada_transferencia_ajuste_saida(self, limpar):
        marcador = limpar
        origem = client.post("/wms/enderecos", json=_endereco(f"{marcador}-A")).json()
        destino = client.post("/wms/enderecos", json=_endereco(f"{marcador}-B")).json()

        entrada = client.post("/wms/movimentos", json=_entrada(marcador, origem["id"]))
        assert entrada.status_code == 201, entrada.text
        corpo = entrada.json()
        assert corpo["movimento"]["tipo"] == "ENTRADA"
        assert corpo["movimento"]["destino"] == origem["codigo"]
        assert corpo["peca"]["enderecoId"] == origem["id"]
        assert corpo["peca"]["largura"] == "1,40"
        estoque_id = corpo["peca"]["id"]

        alocadas = client.get("/wms/estoque/alocado").json()
        assert any(item["id"] == estoque_id for item in alocadas)

        # A peca alocada deixa de aparecer como disponivel.
        abertas = client.get(f"/wms/estoque?busca={marcador}").json()
        assert abertas == {"itens": [], "total": 0}

        transferencia = client.post(
            "/wms/movimentos",
            json={
                "tipo": "TRANSFERENCIA",
                "estoqueId": estoque_id,
                "enderecoDestinoId": destino["id"],
                "usuarioId": 42,
            },
        )
        assert transferencia.status_code == 201, transferencia.text
        movimento = transferencia.json()["movimento"]
        assert movimento["origem"] == origem["codigo"]
        assert movimento["destino"] == destino["codigo"]

        alocadas = client.get("/wms/estoque/alocado").json()
        assert next(i for i in alocadas if i["id"] == estoque_id)["enderecoId"] == destino["id"]

        ajuste = client.post(
            "/wms/movimentos",
            json={"tipo": "AJUSTE", "estoqueId": estoque_id, "observacao": "conferido"},
        )
        assert ajuste.status_code == 201, ajuste.text

        saida = client.post(
            "/wms/movimentos",
            json={"tipo": "SAIDA", "estoqueId": estoque_id, "usuarioId": 42},
        )
        assert saida.status_code == 201, saida.text
        assert saida.json()["movimento"]["nroRolo"] == marcador

        alocadas = client.get("/wms/estoque/alocado").json()
        assert all(item["id"] != estoque_id for item in alocadas)

        historico = client.get("/wms/movimentos?limite=20").json()
        do_teste = [m for m in historico if m["nroRolo"] == marcador]
        assert [m["tipo"] for m in do_teste] == ["SAIDA", "AJUSTE", "TRANSFERENCIA", "ENTRADA"]
        assert all(m["usuarioId"] in (42, None) for m in do_teste)

    def test_entrada_duplicada_da_409(self, limpar):
        endereco = client.post("/wms/enderecos", json=_endereco(limpar)).json()
        primeira = client.post("/wms/movimentos", json=_entrada(limpar, endereco["id"]))
        assert primeira.status_code == 201
        repetida = client.post("/wms/movimentos", json=_entrada(limpar, endereco["id"]))
        assert repetida.status_code == 409
        assert "já está alocada" in repetida.json()["detail"]

    def test_entrada_sem_peca_da_400(self):
        resposta = client.post("/wms/movimentos", json={"tipo": "ENTRADA"})
        assert resposta.status_code == 400
        assert "obrigat" in resposta.json()["detail"]

    def test_entrada_com_endereco_inexistente_da_400(self, limpar):
        resposta = client.post("/wms/movimentos", json=_entrada(limpar, 999_999))
        assert resposta.status_code == 400
        assert "Endereço" in resposta.json()["detail"]

    def test_transferencia_com_endereco_inexistente_da_400(self, limpar):
        endereco = client.post("/wms/enderecos", json=_endereco(limpar)).json()
        estoque_id = client.post(
            "/wms/movimentos", json=_entrada(limpar, endereco["id"])
        ).json()["peca"]["id"]

        resposta = client.post(
            "/wms/movimentos",
            json={"tipo": "TRANSFERENCIA", "estoqueId": estoque_id, "enderecoDestinoId": 999_999},
        )
        assert resposta.status_code == 400

    def test_peca_inexistente_da_404(self):
        resposta = client.post("/wms/movimentos", json={"tipo": "SAIDA", "estoqueId": 999_999})
        assert resposta.status_code == 404

    def test_tipo_invalido_da_400(self):
        resposta = client.post("/wms/movimentos", json={"tipo": "X", "estoqueId": 1})
        assert resposta.status_code == 400


class TestDashboard:
    def test_resumo(self):
        resposta = client.get("/wms/dashboard")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert set(corpo) == {
            "enderecos",
            "enderecosAtivos",
            "pecasAlocadas",
            "metrosAlocados",
            "pecasEmAberto",
            "movimentosHoje",
        }
        assert corpo["pecasEmAberto"] > 0
        assert isinstance(corpo["metrosAlocados"], float)


class TestEscopo:
    @pytest.fixture
    def ligado(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(get_settings(), "api_autenticacao_exigida", True)

    def _headers(self, monkeypatch: pytest.MonkeyPatch, escopos: list[str]) -> dict[str, str]:
        usuario = Usuario(
            id=1,
            email="teste@exemplo.com.br",
            nome="Teste",
            papeis=["leitura"],
            empresa="13",
            ativo=True,
            escopos=escopos,
        )
        monkeypatch.setattr("src.api.auth.dependencias.usuarios.por_id", lambda _: usuario)
        token = tokens.emitir(
            usuario_id=usuario.id,
            email=usuario.email,
            papeis=usuario.papeis,
            empresa=usuario.empresa,
        )
        return {"Authorization": f"Bearer {token}"}

    @pytest.mark.parametrize(
        "metodo,rota,corpo",
        [
            ("GET", "/wms/dashboard", None),
            ("GET", "/wms/enderecos", None),
            ("GET", "/wms/estoque", None),
            ("GET", "/wms/estoque/alocado", None),
            ("GET", "/wms/movimentos", None),
            ("POST", "/wms/enderecos", {"codigo": "X"}),
            ("POST", "/wms/movimentos", {"tipo": "AJUSTE", "estoqueId": 1}),
        ],
    )
    def test_sem_estoque_leitura_da_403(self, ligado, monkeypatch, metodo, rota, corpo):
        cabecalho = self._headers(monkeypatch, escopos=[])
        resposta = client.request(metodo, rota, headers=cabecalho, json=corpo)
        assert resposta.status_code == 403, rota

    def test_com_estoque_leitura_responde(self, ligado, monkeypatch):
        cabecalho = self._headers(monkeypatch, escopos=[ESCOPO_ESTOQUE])
        assert client.get("/wms/dashboard", headers=cabecalho).status_code == 200
