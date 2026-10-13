"""Detalhe do custo administrativo (departamentos 1.1.1.1 e 1.1.1.2) para o BI.

O card "Custos Administrativos Mensal" mostra só o consolidado, porque
`uspCustoAdmComparativo` devolve uma linha por janela. Esta rota devolve **de onde
o número vem**: os lançamentos que compoem o custo, com documento, fornecedor,
despesa e departamento.

A origem é a mesma da procedure do card — `sp_PagRel_CCusto_Niveis`, executada com
`@Tipo = 'B'` (baixas) — filtrando os departamentos `1.1.1.1` e `1.1.1.2` que ela
mesma usa. Não há DDL no ERP: a procedure só monta o resultado em tabelas
temporárias da sessão.

O agregado do card soma `Valor_Baixado`; o detalhe soma o **valor absoluto** das mesmas
linhas, então a soma da lista bate com o número do card.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from src.api.auth.escopos import ESCOPO_FINANCEIRO, exigir_escopo
from src.api.auth.usuarios import Usuario
from src.db import erp

router = APIRouter(tags=["custos-administrativos-detalhe"])

_financeiro = Annotated[Usuario | None, Depends(exigir_escopo(ESCOPO_FINANCEIRO))]

# Mesmo par usado pela `uspCustoAdmComparativo` na CTE `adm`.
DEPARTAMENTOS = ("1.1.1.1", "1.1.1.2")

SQL_DETALHE = (
    "exec dbo.sp_PagRel_CCusto_Niveis "
    "'(''13'',''14'')', ?, ?, 'B', 'D', ?, '', '', "
    "0,0,0,0,0,0,0,0,0,0,0,0,0, '', ''"
)

# Faturamento mês a mês, com a mesma conta da `uspCustoAdmComparativo`
# (`SUM(Vr_Total) + SUM(Acres_Desc)` sobre `vwFaturamento`, sem filtro de empresa).
# Não viemos da procedure porque ela só devolve a janela agregada, e a tela precisa
# do mês a mês para desenhar a série ao lado do custo.
SQL_FATURAMENTO_MENSAL = """
select convert(char(7), cast(f.Data_Nota as date), 120) as Mes,
       sum(isnull(f.Vr_Total, 0)) + sum(isnull(f.Acres_Desc, 0)) as Faturamento
from DBProDash.dbo.vwFaturamento f
where cast(f.Data_Nota as date) >= ? and cast(f.Data_Nota as date) <= ?
group by convert(char(7), cast(f.Data_Nota as date), 120)
order by 1
"""


def _texto(valor: Any) -> str:
    """Os campos char/var do SQL Server vêm com espaço à direita."""
    return valor.strip() if isinstance(valor, str) else ""


def _numero(valor: Any) -> float:
    if valor is None or valor == "":
        return 0.0
    return float(valor) if not isinstance(valor, Decimal) else float(valor)


def _departamento(linha: dict[str, Any]) -> str:
    return ".".join(
        str(linha.get(f"CodDpto{n}") or 0) for n in (1, 2, 3, 4)
    )


def _janelas(referencia: date) -> tuple[tuple[date, date], tuple[date, date]]:
    """Mês atual e mês anterior, na mesma regra da `uspCustoAdmComparativo`."""
    ini = date(referencia.year, referencia.month, 1)
    fim_anterior = date(referencia.year, referencia.month, 1)
    # Dia 1 do mês anterior é o último dia do mês retrasado.
    fim = date.fromordinal(fim_anterior.toordinal() - 1)
    ini_anterior = date(fim.year, fim.month, 1)
    return (ini, referencia), (ini_anterior, fim)


def _buscar(ini: date, fim: date) -> list[dict[str, Any]]:
    linhas = erp.ultimo_resultado(SQL_DETALHE, (ini, fim, fim))
    return [
        linha
        for linha in linhas
        if _departamento(linha) in DEPARTAMENTOS
    ]


def _item(linha: dict[str, Any]) -> dict[str, Any]:
    return {
        "empresa": _texto(linha.get("Empresa")),
        "documento": _texto(linha.get("Documento")),
        "fornecedor": _texto(linha.get("CodFornecedor")),
        "razao_social": _texto(linha.get("Razao_Nome_Cliente")),
        "despesa": _texto(linha.get("DescDesp1")),
        "despesa_2": _texto(linha.get("DescDesp2")),
        "departamento": _departamento(linha),
        "departamento_nome": _texto(linha.get("DescDpto4")),
        "data_baixa": _data(linha.get("Data_Baixa")),
        "data_emissao": _data(linha.get("Data_Emissao")),
        "parcela": _texto(linha.get("PArcela")),
        "referente": _texto(linha.get("Referente")),
        # O rateio devolve o valor com sinal variando por `E_S` (entrada/saída). Como a
        # tela mostra *custo*, normalizamos para positivo: é o que faz a soma bater com
        # o R$ 170.459,83 do card e o que deixa a ordenação por maior valor correta.
        "valor": abs(_numero(linha.get("Valor_Baixado"))),
    }


def _data(valor: Any) -> str | None:
    """`Data_Baixa` chega como `date` (o pyodbc converte `smalldatetime`)."""
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return None


def _agrupar(itens: list[dict[str, Any]], chave: str) -> list[dict[str, Any]]:
    mapa: dict[str, dict[str, Any]] = {}
    for item in itens:
        rotulo = item.get(chave) or "—"
        atual = mapa.setdefault(
            rotulo, {chave: rotulo, "lancamentos": 0, "valor": 0.0}
        )
        atual["lancamentos"] += 1
        atual["valor"] += item["valor"]
    return sorted(mapa.values(), key=lambda g: -g["valor"])


def _periodo(rotulo: str, ini: date, fim: date) -> dict[str, Any]:
    br = f"{ini:%d/%m/%Y}"
    return {
        "rotulo": rotulo,
        "inicio": ini.isoformat(),
        "fim": fim.isoformat(),
        "periodo": br if ini == fim else f"{br} a {fim:%d/%m/%Y}",
        "mes": ini.strftime("%Y-%m"),
    }


def _mes_chave(valor: date) -> str:
    return f"{valor.year}-{valor.month:02d}"


def _somar_meses(base: date, meses: int) -> date:
    """Primeiro dia do mês `meses` à frente de `base`. `date()` estoura no mês 13."""
    total = base.year * 12 + (base.month - 1) + meses
    return date(total // 12, total % 12 + 1, 1)


MESES_BR = (
    "", "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
)


def _mes_rotulo(chave: str) -> str:
    ano, mes = chave.split("-")
    return f"{MESES_BR[int(mes)]}/{ano}"


@router.get("/custos-administrativos-detalhe")
def custos_administrativos_detalhe(
    usuario: _financeiro, data: date | None = None
) -> dict[str, Any]:
    """Lançamentos que formam o custo administrativo, do mês atual e do anterior.

    `data` (opcional, padrão hoje) ancora a janela: qualquer dia do mês desejado.

    O mês corrente vai de 1º até `data`, igual à `uspCustoAdmComparativo`: só entra
    o que o ERP já considera pago até agora, e é por isso que ele aparece zerado
    enquanto não houver baixa no mês.
    """
    referencia = data or date.today()
    (ini_atual, fim_atual), (ini_ant, fim_ant) = _janelas(referencia)

    def bloco(rotulo: str, ini: date, fim: date) -> dict[str, Any]:
        itens = [_item(linha) for linha in _buscar(ini, fim)]
        return {
            **_periodo(rotulo, ini, fim),
            "total": sum(item["valor"] for item in itens),
            "lancamentos": len(itens),
            "itens": itens,
            "por_departamento": _agrupar(itens, "departamento_nome"),
            "por_despesa": _agrupar(itens, "despesa"),
            "por_fornecedor": _agrupar(itens, "razao_social"),
        }

    return {
        "departamentos": list(DEPARTAMENTOS),
        "mes_atual": bloco("Mês atual", ini_atual, fim_atual),
        "mes_anterior": bloco("Mês anterior", ini_ant, fim_ant),
    }


def _janela_12_meses(referencia: date) -> tuple[date, date]:
    """Os 12 meses fechados, na mesma regra da janela `ultimos_12_meses`.

    A `uspCustoAdmComparativo` usa `EOMONTH(@ref, -13) + 1 dia` até `EOMONTH(@ref, -1)`,
    ou seja: do dia 1º do mês 12 meses atrás até o último dia do mês anterior.
    """
    inicio = date(referencia.year - 1, referencia.month, 1)
    fim = date.fromordinal(date(referencia.year, referencia.month, 1).toordinal() - 1)
    return inicio, fim


@router.get("/custos-administrativos-anual-detalhe")
def custos_administrativos_anual_detalhe(
    usuario: _financeiro, data: date | None = None
) -> dict[str, Any]:
    """Os 12 meses fechados do custo administrativo, mês a mês e linha a linha.

    `data` (opcional, padrão hoje) ancora a janela: a referência é sempre o mês
    corrente, e a série vai do mês 12 meses atrás até o mês anterior.

    A soma dos itens e a soma da série batem exatamente com os R$ 9.906.460,70 e
    R$ 27.522.110,17 do card "Média - Custo administrativo 12 meses" (conferido no
    ERP com diferença R$ 0,00). Não chamamos a `uspCustoAdmComparativo` aqui porque
    ela devolve só o agregado da janela, e a tela precisa do mês a mês; a conta do
    faturamento é a mesma dela, copiada para `SQL_FATURAMENTO_MENSAL`.
    """
    referencia = data or date.today()
    inicio, fim = _janela_12_meses(referencia)

    itens = [_item(linha) for linha in _buscar(inicio, fim)]
    for item in itens:
        # `data_baixa` define o mês na série: é o campo que a procedure soma por janela.
        baixa = item["data_baixa"]
        item["mes"] = _mes_chave(date.fromisoformat(baixa)) if baixa else ""

    faturamento = {
        linha["Mes"]: float(linha["Faturamento"] or 0)
        for linha in erp.query(SQL_FATURAMENTO_MENSAL, (inicio, fim))
    }

    # A série cobre os 12 meses mesmo sem lançamento (o custo pode ser zero).
    por_mes: dict[str, dict[str, Any]] = {
        _mes_chave(_somar_meses(inicio, m)): {"administrativo": 0.0, "lancamentos": 0}
        for m in range(12)
    }
    for item in itens:
        if item["mes"] in por_mes:
            por_mes[item["mes"]]["administrativo"] += item["valor"]
            por_mes[item["mes"]]["lancamentos"] += 1

    meses = []
    for chave in sorted(por_mes):
        administrativo = por_mes[chave]["administrativo"]
        fat_mes = faturamento.get(chave, 0.0)
        meses.append(
            {
                "mes": chave,
                "rotulo": _mes_rotulo(chave),
                "administrativo": administrativo,
                "faturamento": fat_mes,
                "porcentagem": administrativo / fat_mes if fat_mes else None,
                "lancamentos": por_mes[chave]["lancamentos"],
            }
        )

    total = sum(item["valor"] for item in itens)
    faturamento_total = sum(linha["faturamento"] for linha in meses)

    return {
        "departamentos": list(DEPARTAMENTOS),
        "janela": {
            **_periodo("12 meses fechados", inicio, fim),
            "rotulo": f"{_mes_rotulo(meses[0]['mes'])} a {_mes_rotulo(meses[-1]['mes'])}",
            "meses": len(meses),
        },
        "administrativo": {
            "total": total,
            "media": total / len(meses),
            "lancamentos": len(itens),
        },
        "faturamento": {
            "total": faturamento_total,
            "media": faturamento_total / len(meses),
            "porcentagem": total / faturamento_total if faturamento_total else None,
        },
        "meses": meses,
        "por_departamento": _agrupar(itens, "departamento_nome"),
        "por_despesa": _agrupar(itens, "despesa"),
        "por_fornecedor": _agrupar(itens, "razao_social"),
        "itens": itens,
    }


__all__ = ["router"]
