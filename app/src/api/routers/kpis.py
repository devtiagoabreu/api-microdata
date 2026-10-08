"""Rotas de KPI do dashboard (contrato do legado, Doc 44 #4 a #14).

Todas as rotas de valor lêem o **ERP ao vivo** (views do `DBProDash`/`Microdata`, as mesmas
fontes das `usp` do legado) em vez dos marts do warehouse local: o ETL roda em lote e os marts
podem ficar atrasados (ex.: sem o dia de ontem), e o BI precisa de dados frescos no momento em
que o usuário carrega a tela. O warehouse continua alimentando a publicação no Neon
(`src.etl.publicar`) e as rotas de estoque (`/dados`, `/sugestao-rolos`).

As chaves do JSON e as regras de janela continuam as do legado, inclusive as escolhas que
parecem erro e não são (ver Doc 44):

- a "janela de programmed" (`Vencimento >= 1º dia do mês corrente`, <= 2050-12-31) era aplicada
  pelas procedures, não pelas views, então ela mora aqui — e o mês de corte é o **corrente**,
  não o seguinte (medido contra `uspDashFinanceiroContas*Programado`);
- as rotas mensais de valor (`/faturamento`, `/contas-pagas`, `/descontos`, `/devolucoes`,
  `/estornos`) devolvem um **comparativo** com 4 janelas (`MesAtual`, `MesAnterior`, `AnoAtual`,
  `AnoAnterior`) para o card do BI — `AnoAtual` acumula de 1º/jan até o fim do mês de `data`;
  como as 4 janelas são alinhadas ao mês, uma única query agrupada por mês no ERP cobre as 4
  num único scan;
- o "anual" de custos devolve `Faturamento`/`Administrativo` com `Total` (Σ 12 meses fechados) e
  `Media` (÷12), e `Armazenagem`/`Porc_Armazenagem` saíram do contrato (sempre 0 no legado); o
  "mensal" é o **mês atual** (grande) + `MesAnterior` (pequeno), sem o acúmulo histórico — a
  `uspCustoAdmComparativo` agrega o rateio **ao vivo** de `sp_PagRel_CCusto_Niveis`.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from src.api.auth.escopos import (
    ESCOPO_FATURAMENTO,
    ESCOPO_FINANCEIRO,
    exigir_escopo,
)
from src.api.auth.usuarios import Usuario
from src.db import erp
from src.etl import publicar

router = APIRouter(tags=["kpis"])

_faturamento = Annotated[Usuario | None, Depends(exigir_escopo(ESCOPO_FATURAMENTO))]
_financeiro = Annotated[Usuario | None, Depends(exigir_escopo(ESCOPO_FINANCEIRO))]
# O dashboard junta os dois grupos, entao exige os dois escopos.
_dashboard = Annotated[
    Usuario | None, Depends(exigir_escopo(ESCOPO_FATURAMENTO, ESCOPO_FINANCEIRO))
]

LIMITE_VENCIMENTO = date(2050, 12, 31)


def _primeiro_dia(valor: date) -> date:
    return valor.replace(day=1)


def _proximo_mes(valor: date) -> date:
    inicio = _primeiro_dia(valor)
    return date(inicio.year + (inicio.month == 12), inicio.month % 12 + 1, 1)


def _mes_anterior(valor: date) -> date:
    """Primeiro dia do mês imediatamente anterior ao mês de `valor`."""
    inicio = _primeiro_dia(valor)
    return date(inicio.year - (inicio.month == 1), inicio.month - 1 or 12, 1)


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


def _comparativo_vivo(data: date, sql: str, rotulo: str) -> dict[str, dict[str, float]]:
    """As 4 janelas do comparativo somadas de uma única consulta mensal **ao vivo** no ERP.

    A `sql` recebe `(inicio, fim)` e devolve `mes` (1º do mês) + `total`. As janelas de
    `_janelas_4` são todas alinhadas ao mês, então o intervalo de [1º/jan do ano anterior,
    1º/mês seguinte) as cobre todas num único scan — leitura fresca sem depender do ETL.
    """
    linhas = erp.query(sql, (date(data.year - 1, 1, 1), _proximo_mes(data)))
    mensal: dict[tuple[int, int], float] = {}
    for linha in linhas:
        mes = linha["mes"]
        chave = (mes.year, mes.month)
        mensal[chave] = mensal.get(chave, 0.0) + float(linha["total"] or 0)

    def soma(inicio: date, fim: date) -> float:
        return sum(
            valor
            for (ano, mes), valor in mensal.items()
            if inicio <= date(ano, mes, 1) < fim
        )

    return {
        nome: {rotulo: soma(inicio, fim)}
        for nome, inicio, fim in _janelas_4(data)
    }


# ---------------------------------------------------------------- faturamento
# Consultas mensais no ERP: uma por KPI, reutilizadas pelas 4 janelas do comparativo.

SQL_FATURAMENTO_MENSAL = (
    "select datefromparts(year(Data_Nota), month(Data_Nota), 1) as mes, "
    "coalesce(sum(Vr_Total), 0) + coalesce(sum(Acres_Desc), 0) as total "
    "from DBProDash.dbo.vwFaturamento "
    "where Data_Nota >= ? and Data_Nota < ? "
    "group by datefromparts(year(Data_Nota), month(Data_Nota), 1)"
)

SQL_DESCONTOS_MENSAL = (
    "select datefromparts(year(Data_Nota), month(Data_Nota), 1) as mes, "
    "coalesce(sum(Acres_Desc), 0) as total "
    "from DBProDash.dbo.vwFaturamento "
    "where Data_Nota >= ? and Data_Nota < ? "
    "group by datefromparts(year(Data_Nota), month(Data_Nota), 1)"
)

SQL_CONTAS_PAGAS_MENSAL = (
    "select datefromparts(year(Data_Baixa), month(Data_Baixa), 1) as mes, "
    "coalesce(sum(valorPago), 0) as total "
    "from DBProDash.dbo.vwContasPagas "
    "where Data_Baixa >= ? and Data_Baixa < ? "
    "group by datefromparts(year(Data_Baixa), month(Data_Baixa), 1)"
)

SQL_DEVOLUCOES_MENSAL = (
    "select datefromparts(year(Data), month(Data), 1) as mes, "
    "coalesce(sum(Vr_CONtabil), 0) as total "
    "from DBProDash.dbo.vwListagemDeEntradasSaidasPorCFOP "
    "where Nova_CFOP in ('1.201-1', '1.201-2', '1.202-1', '2.202-1') "
    "and Data >= ? and Data < ? "
    "group by datefromparts(year(Data), month(Data), 1)"
)

SQL_ESTORNOS_MENSAL = (
    "select datefromparts(year(Data_Emissao), month(Data_Emissao), 1) as mes, "
    "coalesce(sum(Vr_Nota), 0) as total "
    "from DBProDash.dbo.vwListagemDeEstornos "
    "where Data_Emissao >= ? and Data_Emissao < ? "
    "group by datefromparts(year(Data_Emissao), month(Data_Emissao), 1)"
)


@router.get("/faturamento/{data}")
def faturamento(data: date, usuario: _faturamento) -> dict[str, Any]:
    """`uspFaturamento`: Σ(Vr_Total)+Σ(Acres_Desc) do mês de `data` + comparativo 4 janelas.

    Lê o `vwFaturamento` **ao vivo** (mesma fonte dos custos): o card "Faturamento" do BI
    mostra o mesmo mês atual do custos-administrativos-mensal mesmo sem ETL recente.
    """
    return _comparativo_vivo(data, SQL_FATURAMENTO_MENSAL, "Faturamento")


@router.get("/faturamento-dia/{data}")
def faturamento_dia(data: date, usuario: _faturamento) -> dict[str, float]:
    """`uspFaturamentoDia`: mesmo cálculo, por **dia** (`ISNULL(...,0)` no legado).

    Além do dia selecionado devolve `Ontem` (data − 1) e `Anteontem` (data − 2) numa única
    query **ao vivo** no `vwFaturamento` — o mart pode não ter o dia ainda, e o card diário
    do BI precisa do valor de hoje no momento em que o usuário carrega.
    """
    ontem = data - timedelta(days=1)
    anteontem = data - timedelta(days=2)
    linhas = erp.query(
        "select cast(Data_Nota as date) as dia, "
        "coalesce(sum(Vr_Total), 0) + coalesce(sum(Acres_Desc), 0) as total "
        "from DBProDash.dbo.vwFaturamento "
        "where Data_Nota >= ? and Data_Nota < ? "
        "group by cast(Data_Nota as date)",
        (anteontem, data + timedelta(days=1)),
    )
    valores: dict[date, float] = {data: 0.0, ontem: 0.0, anteontem: 0.0}
    for linha in linhas:
        dia = linha["dia"]
        valores[date(dia.year, dia.month, dia.day)] = float(linha["total"] or 0)
    return {
        "Faturamento": valores[data],
        "Ontem": valores[ontem],
        "Anteontem": valores[anteontem],
    }


@router.get("/descontos/{data}")
def descontos(data: date, usuario: _faturamento) -> dict[str, Any]:
    """`uspDesconto`: Σ(Acres_Desc) do mês de `data` + comparativo com as 4 janelas."""
    return _comparativo_vivo(data, SQL_DESCONTOS_MENSAL, "Desconto")


# --------------------------------------------------------------- contas pagas


@router.get("/contas-pagas/{data}")
def contas_pagas(data: date, usuario: _financeiro) -> dict[str, Any]:
    """`uspListagemBaixasPagar`: Σ das baixas pagas no mês de `data` + comparativo 4 janelas.

    No legado o `SELECT` estava comentado e a rota respondia `{}`, mas a `usp` devolve a coluna
    `ContasPagas` — é esse o contrato adotado aqui (Doc 44 #6, atualizado).
    """
    return _comparativo_vivo(data, SQL_CONTAS_PAGAS_MENSAL, "ContasPagas")


# ------------------------------------------------------- devoluções/estornos


@router.get("/devolucoes/{data}")
def devolucoes(data: date, usuario: _faturamento) -> dict[str, Any]:
    """`uspDevolucao`: Σ(Vr_Contabil) das naturezas de devolução no mês de `data` + comparativo."""
    return _comparativo_vivo(data, SQL_DEVOLUCOES_MENSAL, "Devolucao")


@router.get("/estornos/{data}")
def estornos(data: date, usuario: _faturamento) -> dict[str, Any]:
    """`uspEstorno`: Σ(Vr_Nota) por `Data_Emissao` no mês de `data` + comparativo."""
    return _comparativo_vivo(data, SQL_ESTORNOS_MENSAL, "Estorno")


# ------------------------------------------------------------- programmed
# A janela do mês entra na query (CASE) — as views não filtram, as procedures filtravam.

SQL_RECEBER_PROGRAMADO = (
    "select count(*) as documentos, coalesce(sum(ValorTotal), 0) as valor, "
    "sum(case when Vencimento < ? then 1 else 0 end) as documentos_mes, "
    "coalesce(sum(case when Vencimento < ? then ValorTotal else 0 end), 0) as valor_mes "
    "from DBProDash.dbo.vwFinanceiroContasReceber "
    "where Vencimento >= ? and Vencimento <= ?"
)

SQL_PAGAR_PROGRAMADO = (
    "select count(distinct case when Vencimento < ? then cast(QtdeDoc as varchar(60)) end) "
    "as documentos_mes, "
    "coalesce(sum(case when Vencimento < ? then ValorTotal else 0 end), 0) as valor_mes, "
    "count(distinct cast(QtdeDoc as varchar(60))) as documentos, "
    "coalesce(sum(ValorTotal), 0) as valor "
    "from DBProDash.dbo.vwFinanceiroContasPagar "
    "where Vencimento >= ? and Vencimento <= ?"
)


@router.get("/contas-receber-programado")
def contas_receber_programado(usuario: _financeiro) -> dict[str, Any]:
    """`uspDashFinanceiroContasReceberProgramado`: COUNT(QtdeDoc) e Σ(ValorTotal) ao vivo."""
    return _programado(SQL_RECEBER_PROGRAMADO)


@router.get("/contas-pagar-programado")
def contas_pagar_programado(usuario: _financeiro) -> dict[str, Any]:
    """`uspDashFinanceiroContasPagarProgramado`: COUNT(DISTINCT QtdeDoc) — diferença do legado."""
    return _programado(SQL_PAGAR_PROGRAMADO)


def _programado(sql: str) -> dict[str, Any]:
    """Títulos em aberto **ao vivo** no ERP com a janela que as procedures aplicavam.

    A regra real (medida contra `uspDashFinanceiroContas*Programado`) é `>= 1º dia do mês
    corrente`, não `>= 1º/mês seguinte`: o "programado" inclui os vencidos do próprio mês.
    O teto de 2050-12-31 nunca limita hoje (vencimento máximo é 2029) e fica como rede de
    segurança para não vazair registros com data zerada.

    Além do total, devolve `QtdeDocMes`/`ValorTotalMes` com a janela do **mês corrente**
    (vencimento entre 1º e o último dia do mês) para o card do BI mostrar o que vence
    neste mês ao lado do total programado.
    """
    hoje = date.today()
    inicio_mes = _primeiro_dia(hoje)
    fim_mes = _proximo_mes(inicio_mes)
    linha = erp.query(sql, (fim_mes, fim_mes, inicio_mes, LIMITE_VENCIMENTO))[0]
    return {
        "QtdeDoc": int(linha["documentos"] or 0),
        "ValorTotal": float(linha["valor"] or 0),
        "QtdeDocMes": int(linha["documentos_mes"] or 0),
        "ValorTotalMes": float(linha["valor_mes"] or 0),
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
    resposta do KPI sai igual — cada KPI lê o ERP ao vivo, sem depender do warehouse.
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