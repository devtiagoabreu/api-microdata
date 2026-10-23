"""WMS na api-microdata: pedidos liberados, ordens de separacao e estoque em aberto.

A suite roda contra o `dgbcomex_warehouse` real (como as demais) e contra o `raw` (ERP,
somente leitura). Para nao sujar dados, cada teste escolhe um pedido liberado sem ordem
ativa e apaga no teardown as ordens que criou (cascade em pecas/eventos).
"""

from __future__ import annotations

from typing import Any

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

SQL_ABERTA = """
    not exists (
        select 1
        from raw.cte_baixa b
        where b.empresa = a.empresa
          and b.nro_rolo = a.nro_rolo
          and b.nro_peca = a.nro_peca
    )
    and a.nro_rolo_origem is null
"""


def _cenario() -> dict[str, Any] | None:
    """Pedido liberado (status 2) com saldo e uma peca em aberto compativel com um item."""
    sql = f"""
        select
            i.empresa,
            i.pedido,
            i.item,
            i.produto,
            a.nro_rolo,
            a.nro_peca
        from raw.car_itens_pedido i
        join raw.car_pedido p
          on p.empresa = i.empresa and p.pedido = i.pedido
        join lateral (
            select a.empresa, a.nro_rolo, a.nro_peca
            from raw.cte_peca a
            where {SQL_ABERTA}
              and a.empresa = i.empresa
              and a.produto is not distinct from i.produto
              and a.situacao is not distinct from i.situacao
              and a.cor is not distinct from i.cor
              and a.desenho is not distinct from i.desenho
              and a.variante is not distinct from i.variante
              and a.categoria is not distinct from i.categoria
              and not exists (
                  select 1
                  from public.wms_separacao_pecas sp
                  where sp.empresa = a.empresa
                    and sp.nro_rolo = a.nro_rolo
                    and sp.nro_peca = a.nro_peca
                    and sp.status in ('RESERVADA', 'SEPARADA')
              )
            order by a.gaveta nulls last, a.nro_rolo, a.nro_peca
            limit 1
        ) a on true
        where p.status = '2'
          and coalesce(p.status_ped, '') <> 'E'
          and coalesce(i.status_item, '') <> 'E'
          and (i.qtde - coalesce(i.qtde_romaneio, 0) - coalesce(i.qtde_acerto, 0)) > 0
          and not exists (
              select 1
              from public.wms_separacoes s
              where s.empresa = i.empresa
                and s.pedido = i.pedido
                and s.status in ('LIBERADO', 'EM_SEPARACAO')
          )
        order by i.empresa, i.pedido, i.item
        limit 1
    """
    with warehouse.engine().connect() as conn:
        linha = conn.execute(text(sql)).mappings().first()
    return dict(linha) if linha else None


@pytest.fixture
def cenario() -> Any:
    dados = _cenario()
    if dados is None:
        pytest.skip("Sem pedido liberado com peca compativel no ambiente local")
    dados["criadas"] = []
    yield dados
    if dados["criadas"]:
        with warehouse.engine().begin() as conn:
            for separacao_id in dados["criadas"]:
                conn.execute(
                    text("delete from public.wms_separacoes where id = :id"),
                    {"id": separacao_id},
                )


def _criar(dados: dict[str, Any], **extra: Any) -> dict[str, Any]:
    corpo = {
        "empresa": dados["empresa"],
        "pedido": dados["pedido"],
        "usuarioId": 7,
        **extra,
    }
    resposta = client.post("/wms/separacoes", json=corpo)
    assert resposta.status_code == 201, resposta.text
    ordem = resposta.json()
    dados["criadas"].append(ordem["id"])
    return ordem


def _peca(dados: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "empresa": dados["empresa"],
        "nroRolo": dados["nro_rolo"],
        "nroPeca": dados["nro_peca"],
        **extra,
    }


def _adicionar(ordem: dict[str, Any], dados: dict[str, Any]) -> Any:
    return client.post(
        f"/wms/separacoes/{ordem['id']}/pecas",
        json={"item": dados["item"], "pecas": [_peca(dados)], "usuarioId": 7},
    )


class TestDashboard:
    def test_resumo(self):
        resposta = client.get("/wms/dashboard")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert set(corpo) == {
            "pedidosLiberados",
            "separacoesLiberadas",
            "separacoesEmAndamento",
            "separacoesConcluidas",
            "pecasReservadas",
            "metrosReservados",
            "pecasEmAberto",
            "gavetas",
        }
        assert corpo["pedidosLiberados"] > 0
        assert corpo["pecasEmAberto"] > 0
        assert isinstance(corpo["metrosReservados"], float)


class TestGavetas:
    def test_lista_catalogo_do_erp(self):
        resposta = client.get("/wms/gavetas?limite=5")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["total"] > 0
        assert len(corpo["itens"]) <= 5
        gaveta = corpo["itens"][0]
        assert set(gaveta) == {
            "codigo",
            "descricao",
            "grupoGaveta",
            "zona",
            "setor",
            "fazSugestao",
            "estoquePlano",
            "confirmarTransferencia",
            "pecas",
            "metros",
        }

    def test_busca_por_codigo(self):
        codigo = client.get("/wms/gavetas?limite=1").json()["itens"][0]["codigo"]
        corpo = client.get(f"/wms/gavetas?busca={codigo}").json()
        assert any(item["codigo"] == codigo for item in corpo["itens"])


class TestPedidos:
    def test_lista_backlog(self):
        resposta = client.get("/wms/pedidos?limite=5")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["total"] > 0
        pedido = corpo["itens"][0]
        assert pedido["status"] == "2"
        assert pedido["separacaoStatus"] in (
            "SEM_SEPARACAO",
            "LIBERADO",
            "EM_SEPARACAO",
            "SEPARADO",
        )

    def test_filtro_sem_separacao(self):
        corpo = client.get("/wms/pedidos?statusSeparacao=SEM_SEPARACAO&limite=5").json()
        assert all(item["separacaoStatus"] == "SEM_SEPARACAO" for item in corpo["itens"])

    def test_detalhe_com_itens(self, cenario):
        resposta = client.get(
            f"/wms/pedidos/{cenario['empresa']}/{cenario['pedido']}"
        )
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["pedido"] == cenario["pedido"]
        assert corpo["separacaoStatus"] == "SEM_SEPARACAO"
        assert any(item["item"] == cenario["item"] for item in corpo["itens"])

    def test_pedido_inexistente_da_404(self):
        resposta = client.get("/wms/pedidos/13/INEXISTENTE")
        assert resposta.status_code == 404


class TestFluxoSeparacao:
    def test_criar_listar_detalhar(self, cenario):
        ordem = _criar(cenario)
        assert ordem["status"] == "LIBERADO"
        assert ordem["pedido"] == cenario["pedido"]
        assert ordem["totalPecas"] == 0

        lista = client.get(f"/wms/separacoes?busca={cenario['pedido']}").json()
        assert any(item["id"] == ordem["id"] for item in lista["itens"])

        detalhe = client.get(f"/wms/separacoes/{ordem['id']}").json()
        assert detalhe["id"] == ordem["id"]
        assert detalhe["pecas"] == []
        assert detalhe["itens"]

    def test_pedido_com_ordem_ativa_da_409(self, cenario):
        _criar(cenario)
        resposta = client.post(
            "/wms/separacoes",
            json={"empresa": cenario["empresa"], "pedido": cenario["pedido"]},
        )
        assert resposta.status_code == 409
        assert "ativa" in resposta.json()["detail"]

    def test_pedido_inexistente_da_400(self):
        resposta = client.post(
            "/wms/separacoes", json={"empresa": "13", "pedido": "INEXISTENTE"}
        )
        assert resposta.status_code == 400
        assert "liberado" in resposta.json()["detail"]

    def test_adicionar_peca_reserva_e_some_do_estoque(self, cenario):
        ordem = _criar(cenario)
        resposta = _adicionar(ordem, cenario)
        assert resposta.status_code == 201, resposta.text
        corpo = resposta.json()
        assert corpo["adicionadas"] == 1
        assert corpo["separacao"]["status"] == "EM_SEPARACAO"
        assert corpo["separacao"]["totalPecas"] == 1

        detalhe = client.get(f"/wms/separacoes/{ordem['id']}").json()
        peca = detalhe["pecas"][0]
        assert peca["nroRolo"] == cenario["nro_rolo"]
        assert peca["nroPeca"] == cenario["nro_peca"]
        assert peca["status"] == "RESERVADA"
        assert peca["baixadoNoErp"] is False

        busca = (
            f"/wms/estoque?busca={cenario['nro_rolo']}"
            f"&subLote=&limite=500"
        )
        estoque = client.get(busca).json()
        assert all(
            not (
                item["nro_rolo"] == cenario["nro_rolo"]
                and item["nro_peca"] == cenario["nro_peca"]
            )
            for item in estoque["itens"]
        )

        disponiveis = client.get(
            f"/wms/separacoes/{ordem['id']}/itens/{cenario['item']}/pecas?limite=500"
        ).json()
        assert all(
            not (
                item["nro_rolo"] == cenario["nro_rolo"]
                and item["nro_peca"] == cenario["nro_peca"]
            )
            for item in disponiveis["itens"]
        )

    def test_peca_duplicada_da_409(self, cenario):
        ordem = _criar(cenario)
        assert _adicionar(ordem, cenario).status_code == 201
        repetida = _adicionar(ordem, cenario)
        assert repetida.status_code == 409
        assert "reservada" in repetida.json()["detail"]

    def test_peca_incompativel_da_400(self, cenario):
        outra = _peca_incompativel(cenario)
        if outra is None:
            pytest.skip("Sem peca em aberto incompativel no ambiente local")
        ordem = _criar(cenario)
        resposta = client.post(
            f"/wms/separacoes/{ordem['id']}/pecas",
            json={"item": cenario["item"], "pecas": [outra], "usuarioId": 7},
        )
        assert resposta.status_code == 400
        assert "indisponível" in resposta.json()["detail"]

    def test_concluir_mantem_pecas_bloqueadas(self, cenario):
        ordem = _criar(cenario)
        assert _adicionar(ordem, cenario).status_code == 201
        peca_id = client.get(f"/wms/separacoes/{ordem['id']}").json()["pecas"][0]["id"]

        concluida = client.post(
            f"/wms/separacoes/{ordem['id']}/concluir", json={"usuarioId": 7}
        )
        assert concluida.status_code == 200, concluida.text
        corpo = concluida.json()
        assert corpo["status"] == "SEPARADO"
        assert corpo["concluidoPor"] == 7

        detalhe = client.get(f"/wms/separacoes/{ordem['id']}").json()
        assert detalhe["pecas"][0]["status"] == "SEPARADA"

        remover = client.delete(
            f"/wms/separacoes/{ordem['id']}/pecas/{peca_id}?usuarioId=7"
        )
        assert remover.status_code == 409

        # Concluir de novo e idempotente.
        assert (
            client.post(f"/wms/separacoes/{ordem['id']}/concluir", json={}).status_code
            == 200
        )

    def test_concluir_sem_pecas_da_400(self, cenario):
        ordem = _criar(cenario)
        resposta = client.post(f"/wms/separacoes/{ordem['id']}/concluir", json={})
        assert resposta.status_code == 400
        assert "peça" in resposta.json()["detail"]

    def test_iniciar_e_idempotente(self, cenario):
        ordem = _criar(cenario)
        primeira = client.post(f"/wms/separacoes/{ordem['id']}/iniciar", json={"usuarioId": 3})
        assert primeira.status_code == 200
        assert primeira.json()["status"] == "EM_SEPARACAO"
        assert primeira.json()["iniciadoPor"] == 3
        segunda = client.post(f"/wms/separacoes/{ordem['id']}/iniciar", json={})
        assert segunda.status_code == 200
        assert segunda.json()["status"] == "EM_SEPARACAO"

    def test_cancelar_libera_pecas(self, cenario):
        ordem = _criar(cenario)
        assert _adicionar(ordem, cenario).status_code == 201

        cancelada = client.post(
            f"/wms/separacoes/{ordem['id']}/cancelar",
            json={"motivo": "cliente desistiu", "usuarioId": 9},
        )
        assert cancelada.status_code == 200, cancelada.text
        corpo = cancelada.json()
        assert corpo["status"] == "CANCELADO"
        assert corpo["motivoCancelamento"] == "cliente desistiu"
        assert corpo["canceladoPor"] == 9
        assert corpo["totalPecas"] == 0

        disponiveis = client.get(
            f"/wms/separacoes/{ordem['id']}/itens/{cenario['item']}/pecas?limite=500"
        )
        # Ordem cancelada ainda pode listar pecas disponiveis para o item.
        assert disponiveis.status_code == 200
        assert any(
            item["nro_rolo"] == cenario["nro_rolo"]
            and item["nro_peca"] == cenario["nro_peca"]
            for item in disponiveis.json()["itens"]
        )

    def test_remover_peca_em_separacao(self, cenario):
        ordem = _criar(cenario)
        assert _adicionar(ordem, cenario).status_code == 201
        peca_id = client.get(f"/wms/separacoes/{ordem['id']}").json()["pecas"][0]["id"]

        removida = client.delete(
            f"/wms/separacoes/{ordem['id']}/pecas/{peca_id}?usuarioId=7"
        )
        assert removida.status_code == 200, removida.text
        assert removida.json()["separacao"]["totalPecas"] == 0

        # Depois de liberada, pode ser reservada de novo.
        assert _adicionar(ordem, cenario).status_code == 201

    def test_ordem_inexistente_da_404(self):
        assert client.get("/wms/separacoes/999999").status_code == 404
        assert (
            client.post("/wms/separacoes/999999/iniciar", json={}).status_code == 404
        )


def _peca_incompativel(dados: dict[str, Any]) -> dict[str, Any] | None:
    sql = f"""
        select a.empresa, a.nro_rolo, a.nro_peca
        from raw.cte_peca a
        where {SQL_ABERTA}
          and a.produto is distinct from :produto
          and not exists (
              select 1
              from public.wms_separacao_pecas sp
              where sp.empresa = a.empresa
                and sp.nro_rolo = a.nro_rolo
                and sp.nro_peca = a.nro_peca
                and sp.status in ('RESERVADA', 'SEPARADA')
          )
        order by a.nro_rolo
        limit 1
    """
    with warehouse.engine().connect() as conn:
        linha = conn.execute(
            text(sql), {"produto": dados["produto"]}
        ).mappings().first()
    return (
        {
            "empresa": linha["empresa"],
            "nroRolo": linha["nro_rolo"],
            "nroPeca": linha["nro_peca"],
        }
        if linha
        else None
    )


class TestEstoque:
    def test_lista_em_aberto(self):
        corpo = client.get("/wms/estoque?limite=5").json()
        assert corpo["total"] > 0
        assert len(corpo["itens"]) <= 5
        item = corpo["itens"][0]
        assert item["nro_rolo"]
        assert isinstance(item["metros"], (int, float)) or item["metros"] is None

    def test_filtro_gaveta(self):
        gaveta = client.get("/wms/gavetas?limite=1").json()["itens"][0]["codigo"]
        corpo = client.get(f"/wms/estoque?gaveta={gaveta}&limite=500").json()
        assert all(item["gaveta"] == gaveta for item in corpo["itens"])


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
            ("GET", "/wms/gavetas", None),
            ("GET", "/wms/pedidos", None),
            ("GET", "/wms/estoque", None),
            ("GET", "/wms/separacoes", None),
            ("POST", "/wms/separacoes", {"empresa": "13", "pedido": "X"}),
        ],
    )
    def test_sem_estoque_leitura_da_403(self, ligado, monkeypatch, metodo, rota, corpo):
        cabecalho = self._headers(monkeypatch, escopos=[])
        resposta = client.request(metodo, rota, headers=cabecalho, json=corpo)
        assert resposta.status_code == 403, rota

    def test_com_estoque_leitura_responde(self, ligado, monkeypatch):
        cabecalho = self._headers(monkeypatch, escopos=[ESCOPO_ESTOQUE])
        assert client.get("/wms/dashboard", headers=cabecalho).status_code == 200
