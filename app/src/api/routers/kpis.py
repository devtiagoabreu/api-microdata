"""Rotas de KPI do dashboard (contrato do legado, Doc 44 #4 a #14).

Cada rota lê um mart do warehouse local em vez de executar uma `usp` do `DBProDash`: o legado
fazia até 10 `EXEC` por request (`/dashboard-completo`), aqui a leitura é uma query por KPI sobre
`marts` — exceto os custos, que consultam `uspCustoAdmComparativo` no `DBProDash` (a procedure
agrega o rateio **ao vivo** de `sp_PagRel_CCusto_Niveis`, corrigindo o `Rel_CCusto_Niveis` que o
ETL espelha congelado; ver Doc 44 #7/#8), e o `/faturamento`, que lê o `vwFaturamento` ao vivo
para o mês atual bater sempre com o card de custos (o mart pode estar atrasado). As chaves do JSON
e as regras de janela continuam as do legado, inclusive as escolhas que parecem erro e não são
(ver Doc 44):

- a "janela de programmed" (`Vencimento >= 1º dia do mês corrente`, <= 2050-12-31) era aplicada
  pelas procedures, não pelas views, então ela mora aqui — e o mês de corte é o **corrente**,
  não o seguinte (medido contra `uspDashFinanceiroContas*Programado`);
- as rotas mensais de valor (`/faturamento`, `/contas-pagas`, `/descontos`, `/devolucoes`,
  `/estornos`) devolvem um **comparativo** com 4 janelas (`MesAtual`, `MesAnterior`, `AnoAtual`,
  `AnoAnterior`) para o card do BI — `AnoAtual` acumula de 1º/jan até o fim do mês de `data`;
  o `/faturamento` lê o `vwFaturamento` **ao vivo** (mesma fonte do custos), porque o mart
  `faturamento_diario` pode estar atrasado e divergir do card de custos;
- o "anual" de custos devolve `Faturamento`/`Administrativo` com `Total` (Σ 12 meses fechados) e
  `Media` (÷12), e `Armazenagem`/`Porc_Armazenagem` saíram do contrato (sempre 0 no legado); o
  "mensal" é o **mês atual** (grande) + `MesAnterior` (pequeno), sem o acúmulo histórico.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from src.api.auth.escopos import (
    ESCOPO_FATURAMENTO,
    ESCOPO_FINANCEIRO,
    exigir_escopo,
)
from src.api.auth.usuarios import Usuario
from src.db import erp, warehouse
from src.etl import publicar

router = APIRouter(tags=["kpis"])

_faturamento = Annotated[Usuario | None, Depends(exigir_escopo(ESCOPO_FATURAMENTO))]
_financeiro = Annotated[Usuario | None, Depends(exigir_escopo(ESCOPO_FINANCEIRO))]
# O dashboard junta os dois grupos, entao exige os dois escopos.
_dashboard = Annotated[
    Usuario | None, Depends(exigir_escopo(ESCOPO_FATURAMENTO, ESCOPO_FINANCEIRO))
]

LIMITE_VENCIMENTO = date(2050, 12, 31)


def _consultar(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with warehouse.engine().connect() as conn:
        return [dict(linha) for linha in conn.execute(text(sql), params or {}).mappings()]


def _primeiro_dia(valor: date) -> date:
    return valor.replace(day=1)


def _proximo_mes(valor: date) -> date:
    inicio = _primeiro_dia(valor)
    return date(inicio.year + (inicio.month == 12), inicio.month % 12 + 1, 1)


def _soma(sql: str, params: dict[str, Any] | None = None) -> float:
    linha = _consultar(sql, params)
    return float(list(linha[0].values())[0] or 0) if linha else 0.0


def _mes_anterior(valor: date) -> date:
    """Primeiro dia do mês imediatamente anterior ao mês de `valor`."""
    inicio = _primeiro_dia(valor)
    return date(inicio.year - (inicio.month == 1), inicio.month - 1 or 12, 1)


def _somatorio(mart: str, coluna: str, inicio: date, fim: date) -> float:
    """Σ de uma coluna diária do mart na janela [inicio, fim) — `fim` exclusiva."""
    return _soma(
        f"select sum({coluna}) from {mart} where data >= :inicio and data < :fim",
        {"inicio": inicio, "fim": fim},
    )


def _janelas_4(data: date) -> tuple[tuple[str, date, date], ...]:
    """As 4 janelas comparativas das rotas mensais (Doc 44 #6/#9/#10/#11).

    `MesAtual` e `MesAnterior` espelham a janela da `usp` legada (mês de `data`); `AnoAtual`
    acumula de 1º/jan do ano de `data` até o fim desse mês; `AnoAnterior` é o ano inteiro.
    """
    inicio_mes = _primeiro_dia(data)
    return (
        ("MesAtual", inicio_mes, _proximo_mes(inicio_mes)),
        ("MesAnterior", _mes_anterior(inicio_mes), inicio_mes),
        ("AnoAtual", date(data.year, 1, 1), _proximo_mes(inicio_mes)),
        ("AnoAnterior", date(data.year - 1, 1, 1), date(data.year, 1, 1)),
    )


def _comparativo(data: date, mart: str, coluna: str, rotulo: str) -> dict[str, dict[str, float]]:
    """4 janelas de valor lidas de um mart do warehouse (Doc 44 #6/#9/#10/#11)."""
    return {
        nome: {rotulo: _somatorio(mart, coluna, inicio, fim)}
        for nome, inicio, fim in _janelas_4(data)
    }


# ---------------------------------------------------------------- faturamento


def _faturamento_vivo(inicio: date, fim: date) -> float:
    """Σ(Vr_Total)+Σ(Acres_Desc) de `vwFaturamento` em [inicio, fim), a fonte viva do legado.

    O mart `faturamento_diario` espelha essas duas colunas, mas o ETL pode estar atrasado (ex.:
    sem o dia de ontem), fazendo o card divergir dos custos. Aqui lemos o mesmo `vwFaturamento`
    do `uspCustoAdmComparativo`, então mês atual/anterior batem sempre com o card de custos.
    """
    linhas = erp.query(
        "select coalesce(sum(Vr_Total), 0) + coalesce(sum(Acres_Desc), 0) as faturamento "
        "from DBProDash.dbo.vwFaturamento where Data_Nota >= ? and Data_Nota < ?",
        (inicio, fim),
    )
    return float(linhas[0]["faturamento"] or 0)


@router.get("/faturamento/{data}")
def faturamento(data: date, usuario: _faturamento) -> dict[str, Any]:
    """`uspFaturamento`: Σ(Vr_Total)+Σ(Acres_Desc) do mês de `data` + comparativo 4 janelas.

    Lê o `vwFaturamento` **ao vivo** (mesma fonte dos custos) em vez do mart, para o card
    "Faturamento" do BI mostrar o mesmo mês atual que o custos-administrativos-mensal.
    """
    return {
        nome: {"Faturamento": _faturamento_vivo(inicio, fim)}
        for nome, inicio, fim in _janelas_4(data)
    }


@router.get("/faturamento-dia/{data}")
def faturamento_dia(data: date, usuario: _faturamento) -> dict[str, float]:
    """`uspFaturamentoDia`: mesmo cálculo, por **dia** (`ISNULL(...,0)` no legado).

    Além do dia selecionado devolve `Ontem` (data − 1) e `Anteontem` (data − 2) numa
    única query, para o card diário do BI mostrar os 3 últimos dias sem 3 chamadas.
    """
    ontem = data - timedelta(days=1)
    anteontem = data - timedelta(days=2)
    linhas = _consultar(
        "select data, coalesce(sum(faturamento), 0) as total "
        "from marts.faturamento_diario "
        "where data in (:d0, :d1, :d2) group by data",
        {"d0": data, "d1": ontem, "d2": anteontem},
    )
    valores: dict[date, float] = {data: 0.0, ontem: 0.0, anteontem: 0.0}
    for linha in linhas:
        dia = linha["data"]
        if not isinstance(dia, date):
            dia = dia.date()
        valores[dia] = float(linha["total"] or 0)
    return {
        "Faturamento": valores[data],
        "Ontem": valores[ontem],
        "Anteontem": valores[anteontem],
    }


@router.get("/descontos/{data}")
def descontos(data: date, usuario: _faturamento) -> dict[str, Any]:
    """`uspDesconto`: Σ(Acres_Desc) do mês de `data` + comparativo com as 4 janelas."""
    return _comparativo(data, "marts.faturamento_diario", "desconto", "Desconto")


# --------------------------------------------------------------- contas pagas


@router.get("/contas-pagas/{data}")
def contas_pagas(data: date, usuario: _financeiro) -> dict[str, Any]:
    """`uspListagemBaixasPagar`: Σ das baixas pagas no mês de `data` + comparativo 4 janelas.

    No legado o `SELECT` estava comentado e a rota respondia `{}`, mas a `usp` devolve a coluna
    `ContasPagas` — é esse o contrato adotado aqui (Doc 44 #6, atualizado).
    """
    return _comparativo(data, "marts.contas_pagas_diario", "valor_pago", "ContasPagas")


# ------------------------------------------------------- devoluções/estornos


@router.get("/devolucoes/{data}")
def devolucoes(data: date, usuario: _faturamento) -> dict[str, Any]:
    """`uspDevolucao`: Σ(Vr_Contabil) das naturezas de devolução no mês de `data` + comparativo."""
    return _comparativo(data, "marts.devolucoes_diario", "valor", "Devolucao")


@router.get("/estornos/{data}")
def estornos(data: date, usuario: _faturamento) -> dict[str, Any]:
    """`uspEstorno`: Σ(Vr_Nota) por `Data_Emissao` no mês de `data` + comparativo."""
    return _comparativo(data, "marts.estornos_diario", "valor_nota", "Estorno")


# ------------------------------------------------------------- programmed


@router.get("/contas-receber-programado")
def contas_receber_programado(usuario: _financeiro) -> dict[str, Any]:
    """`uspDashFinanceiroContasReceberProgramado`: COUNT(QtdeDoc) e Σ(ValorTotal)."""
    return _programado("marts.financeiro_receber_programado", distinct=False)


@router.get("/contas-pagar-programado")
def contas_pagar_programado(usuario: _financeiro) -> dict[str, Any]:
    """`uspDashFinanceiroContasPagarProgramado`: COUNT(DISTINCT QtdeDoc) — diferença do legado."""
    return _programado("marts.financeiro_pagar_programado", distinct=True)


def _programado(origem: str, *, distinct: bool) -> dict[str, Any]:
    """Aplica a janela que as procedures aplicavam: vencimento de 1º/mês corrente até 2050-12-31.

    A regra real (medida contra `uspDashFinanceiroContas*Programado`) é `>= 1º dia do mês
    corrente`, não `>= 1º/mês seguinte`: o "programado" inclui os vencidos do próprio mês.
    O teto de 2050-12-31 nunca limita hoje (vencimento máximo é 2029) e fica como rede de
    segurança para não vazair registros com data zerada.

    Além do total, devolve `QtdeDocMes`/`ValorTotalMes` com a janela do **mês corrente**
    (vencimento entre 1º e o último dia do mês) para o card do BI mostrar o que vence
    neste mês ao lado do total programado.
    """
    contagem = "count(distinct qtde_doc)" if distinct else "count(*)"
    hoje = date.today()
    inicio_mes = _primeiro_dia(hoje)
    fim_mes = _proximo_mes(inicio_mes)
    linha = _consultar(
        f"""
        select {contagem} as documentos,
               coalesce(sum(valor_total), 0) as valor,
               {contagem} filter (where vencimento < :fim_mes) as documentos_mes,
               coalesce(sum(valor_total) filter (where vencimento < :fim_mes), 0) as valor_mes
          from {origem}
         where vencimento >= :inicio and vencimento <= :limite
        """,
        {"inicio": inicio_mes, "limite": LIMITE_VENCIMENTO, "fim_mes": fim_mes},
    )
    return {
        "QtdeDoc": int(linha[0]["documentos"] or 0),
        "ValorTotal": float(linha[0]["valor"] or 0),
        "QtdeDocMes": int(linha[0]["documentos_mes"] or 0),
        "ValorTotalMes": float(linha[0]["valor_mes"] or 0),
    }


# -------------------------------------------------------- custos administrativos


def _custos(referencia: date, anual: bool) -> dict[str, Any]:
    """`uspCustoAdmComparativo` no DBProDash: costos por janela com o dados vivos.

    A procedure nova agrega `Faturamento` (vwFaturamento) e `Administrativo` (baixas dos
    departamentos `1.1.1.1`/`1.1.1.2` do rateio ao vivo) para: mês atual, mês anterior,
    12 meses fechados, ano atual e ano anterior. Corrige o quirk do legado, onde o
    `Administrativo` somava o histórico inteiro (`Porc_Administrativo` de 1758% no mensal).

    - mensal = **mês atual** (grande) + `MesAnterior` (pequeno);
    - anual = Σ dos **12 meses fechados** devolvendo `Total` e `Media` (÷12). `Armazenagem` e
      `Porc_Armazenagem` saíram do contrato (sempre 0 no legado — Doc 44 #7/#8).
    """
    linhas = erp.query("exec DBProDash.dbo.uspCustoAdmComparativo ?", (referencia,))
    janelas = {linha["janela"]: linha for linha in linhas}

    def _medida(janela: str) -> dict[str, Any]:
        faturamento = float(janelas[janela]["Faturamento"] or 0)
        administrativo = float(janelas[janela]["Administrativo"] or 0)
        return {
            "Faturamento": faturamento,
            "Administrativo": administrativo,
            "Porc_Administrativo": administrativo / faturamento if faturamento else 0.0,
        }

    if anual:
        totais = _medida("ultimos_12_meses")
        return {
            "Faturamento": {
                "Total": totais["Faturamento"],
                "Media": totais["Faturamento"] / 12,
            },
            "Administrativo": {
                "Total": totais["Administrativo"],
                "Media": totais["Administrativo"] / 12,
            },
            "Porc_Administrativo": totais["Porc_Administrativo"],
        }
    atual = _medida("mes_atual")
    atual["MesAnterior"] = _medida("mes_anterior")
    return atual


@router.get("/custos-administrativos-anual")
def custos_administrativos_anual(usuario: _financeiro, data: date | None = None) -> dict[str, Any]:
    """`uspCustoAdmComparativo`: Σ dos 12 meses fechados — `Total` e `Media` (÷12).

    `data` (opcional, padrão hoje) ancora a janela na procedure.
    """
    return _custos(data or date.today(), anual=True)


@router.get("/custos-administrativos-mensal")
def custos_administrativos_mensal(
    usuario: _financeiro, data: date | None = None
) -> dict[str, Any]:
    """`uspCustoAdmComparativo`: **mês atual** + `MesAnterior` (dados vivos do rateio).

    `data` (opcional, padrão hoje) ancora a janela na procedure.
    """
    return _custos(data or date.today(), anual=False)


# ---------------------------------------------------------------- dashboard


@router.get("/dashboard-completo/{data}")
def dashboard_completo(data: date, usuario: _dashboard) -> dict[str, Any]:
    """Orquestração do legado (#4 a #13 em 10 `EXEC`); aqui uma leitura por KPI.

    Faturamento/descontos/devoluções/estornos/contas pagas usam o mês de `data`; os custos e os
    programados sao sempre relativos a hoje, como nas procedures (que nao recebem data).

    E aqui que o **sync on-demand** acontece (D4): antes de responder, os agregados pequenos que o
    front le no Neon sao republicados **se** o warehouse carregou depois da ultima publicacao.
    Desligado por `NEON_PUBLICAR_AUTOMATICO=false` (padrao) e best-effort: se o sync falhar, a
    resposta do KPI sai igual, lendo o warehouse local.
    """
    publicar.sincronizar_antes_do_dashboard()
    return {
        "data_consulta": data.isoformat(),
        "faturamento": faturamento(data, usuario),
        "faturamento_dia": faturamento_dia(data, usuario),
        "contas_pagas": contas_pagas(data, usuario),
        "custos_administrativos_anual": custos_administrativos_anual(usuario),
        "custos_administrativos_mensal": custos_administrativos_mensal(usuario),
        "descontos": descontos(data, usuario),
        "devolucoes": devolucoes(data, usuario),
        "estornos": estornos(data, usuario),
        "contas_receber_programado": contas_receber_programado(usuario),
        "contas_pagar_programado": contas_pagar_programado(usuario),
    }