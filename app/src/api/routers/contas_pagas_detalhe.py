"""Detalhe de Contas Pagas: as baixas que somam o valor do card "Contas Pagas".

O card (`kpis.py`, `/contas-pagas/{data}`) soma `vwContasPagas`, que tem **duas**
colunas: `Data_Baixa` e `valorPago`. Não há fornecedor, documento nem banco ali —
por isso o card só mostra total. A lista vem da tabela por trás da view,
`DBMicrodata_DGB.dbo.Pag_Baixas`, que é a mesma que o `SELECT` original (hoje
comentado) da `uspListagemBaixasPagar` usava.

A reconciliação foi conferida no ERP: `Pag_Baixas` e `vwContasPagas` devolvem as
mesmas linhas e a mesma soma, com diferença R$ 0,00 em cada um dos 12 meses de
out/2025 a set/2026. Os joins com `Clientes_Principal` (fornecedor) e `Bancos`
são 1:1 — nenhum `(Codigo, Tipo)` nem `Nr_Bco_Bancos` duplicado — então não
duplicam linha nem alteram o total.

**Classificação por departamento/despesa.** `Pag_Baixas` não tem centro de custo:
quem sabe é a `sp_PagRel_CCusto_Niveis` (a mesma que alimenta o custo
administrativo, `custos_administrativos.py`), chamada com `@Tipo = 'B'` para as
baixas. A chave de junção é
`(Empresa, Documento+Serie, CodFornecedor, PArcela, Data_Baixa)` — a procedure
concatena documento e série num campo só. Conferido no ERP: em set/2026 as 118
baixas casam 118, sem sobra e sem divergência de valor nas linhas 1:1.

Quando duas baixas compartilham a chave (parcela repetida no mesmo dia), a
procedure devolve as duas linhas de rateio. Aí o item fica com a linha de maior
valor e `rateio=True`, para a tela não esconder isso: os grupos por departamento
somam o `Valor_Pago` da baixa, não o rateio, e continuam batendo com o total.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from src.api.auth.escopos import ESCOPO_FINANCEIRO, exigir_escopo
from src.api.auth.usuarios import Usuario
from src.db import erp

router = APIRouter(tags=["contas-pagas-detalhe"])

_financeiro = Annotated[Usuario | None, Depends(exigir_escopo(ESCOPO_FINANCEIRO))]

MESES_BR = (
    "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)

# Série mensal. Começa em 1º/jan de dois anos antes para cobrir `AnoAnterior`
# (ano inteiro) e ainda dar 24 meses de contexto na tela.
SQL_SERIE = (
    "select datefromparts(year(pb.Data_Baixa), month(pb.Data_Baixa), 1) as mes, "
    "       count(*) as lancamentos, "
    "       coalesce(sum(isnull(pb.Valor_Pago, 0)), 0) as total "
    "from DBMicrodata_DGB.dbo.Pag_Baixas pb "
    "where pb.Data_Baixa >= ? and pb.Data_Baixa < ? "
    "group by datefromparts(year(pb.Data_Baixa), month(pb.Data_Baixa), 1)"
)

# Os lançamentos do mês de referência, já com fornecedor e banco.
# `rtrim` nos char/varchar: o ERP devolve o nome do fornecedor preenchido com
# espaços até o tamanho do campo.
SQL_ITENS = """
select pb.Empresa as Empresa, pb.Documento as Documento,
       rtrim(pb.Serie) as Serie, pb.Tipo_Fornec as Tipo_Fornec,
       pb.Fornecedor as Fornecedor, rtrim(pb.Parcela) as Parcela,
       pb.Parcial as Parcial, pb.Data_Baixa as Data_Baixa,
       pb.Valor_Pago as Valor_Pago, pb.Juros_Pagos as Juros_Pagos,
       pb.Desconto_Recebido as Desconto_Recebido, pb.Valor_Liquido as Valor_Liquido,
       rtrim(pb.Nr_Banco) as Nr_Banco, rtrim(pb.Nr_Cheque) as Nr_Cheque,
       cp.Razao_Nome_Cliente as Razao_Nome_Cliente,
       rtrim(b.Nome_Bco_Bancos) as Nome_Bco_Bancos
from DBMicrodata_DGB.dbo.Pag_Baixas pb
left join DBMicrodata_DGB.dbo.Clientes_Principal cp
       on cp.Codigo = pb.Fornecedor and cp.Tipo = pb.Tipo_Fornec
    left join DBMicrodata_DGB.dbo.Bancos b on b.Nr_Bco_Bancos = pb.Nr_Banco
where pb.Data_Baixa >= ? and pb.Data_Baixa < ?
order by pb.Data_Baixa desc, pb.Documento
"""

# Despesa e departamento de cada baixa. Mesma procedure do custo administrativo,
# com todos os departamentos (os `@CodDpto*` em 0 = sem filtro) e sem filtro de
# empresa, porque `Pag_Baixas` também não filtra. O `'(''13'',''14'')'` do custo
# administrativo é o `@Empresa`; aqui vem vazio para pegar tudo que a tela lista.
SQL_CLASSIFICACAO = (
    "exec dbo.sp_PagRel_CCusto_Niveis "
    "'', ?, ?, 'B', 'D', ?, '', '', "
    "0,0,0,0,0,0,0,0,0,0,0,0,0, '', ''"
)



def _texto(valor: Any) -> str:
    return valor.strip() if isinstance(valor, str) else ""


def _numero(valor: Any) -> float:
    if valor is None or valor == "":
        return 0.0
    return float(valor)


def _data(valor: Any) -> str | None:
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return None


def _primeiro_dia(valor: date) -> date:
    return valor.replace(day=1)


def _proximo_mes(valor: date) -> date:
    inicio = _primeiro_dia(valor)
    return date(inicio.year + (inicio.month == 12), inicio.month % 12 + 1, 1)


def _somar_meses(base: date, meses: int) -> date:
    total = base.year * 12 + (base.month - 1) + meses
    return date(total // 12, total % 12 + 1, 1)


def _periodo(rotulo: str, ini: date, fim: date) -> dict[str, Any]:
    ultimo = date.fromordinal(fim.toordinal() - 1)
    return {
        "rotulo": rotulo,
        "inicio": ini.isoformat(),
        "fim": ultimo.isoformat(),
        "periodo": f"{ini:%d/%m/%Y} a {ultimo:%d/%m/%Y}",
    }


def _janelas(referencia: date) -> dict[str, tuple[date, date]]:
    """As mesmas 4 janelas de `_janelas_4` em `kpis.py`, com o fim exclusivo."""
    inicio_mes = _primeiro_dia(referencia)
    fim_mes = _proximo_mes(inicio_mes)
    return {
        "mes": (inicio_mes, fim_mes),
        "mes_anterior": (_somar_meses(inicio_mes, -1), inicio_mes),
        "ano_atual": (date(referencia.year, 1, 1), fim_mes),
        "ano_anterior": (date(referencia.year - 1, 1, 1), date(referencia.year, 1, 1)),
    }


def _item(linha: dict[str, Any]) -> dict[str, Any]:
    return {
        "empresa": _texto(linha.get("Empresa")),
        "documento": _texto(linha.get("Documento")),
        "serie": _texto(linha.get("Serie")),
        "fornecedor": _texto(linha.get("Fornecedor")),
        "razao_social": _texto(linha.get("Razao_Nome_Cliente")),
        "tipo_fornecedor": _texto(linha.get("Tipo_Fornec")),
        "parcela": _texto(linha.get("Parcela")),
        "parcial": _texto(linha.get("Parcial")),
        "data_baixa": _data(linha.get("Data_Baixa")),
        "banco": _texto(linha.get("Nome_Bco_Bancos")),
        "numero_banco": _texto(linha.get("Nr_Banco")),
        "cheque": _texto(linha.get("Nr_Cheque")),
        # Sem `abs()`: o card soma `Valor_Pago` com o sinal que vier. Não há
        # pagamento negativo em 2024-2026 (conferido no ERP), e normalizar aqui
        # abriria uma divergência de reconciliação sem causa.
        "valor": _numero(linha.get("Valor_Pago")),
        "juros": _numero(linha.get("Juros_Pagos")),
        "desconto": _numero(linha.get("Desconto_Recebido")),
        "valor_liquido": _numero(linha.get("Valor_Liquido")),
    }


def _agrupar(itens: list[dict[str, Any]], chave: str) -> list[dict[str, Any]]:
    mapa: dict[str, dict[str, Any]] = {}
    for item in itens:
        rotulo = item.get(chave) or "—"
        atual = mapa.setdefault(rotulo, {chave: rotulo, "lancamentos": 0, "valor": 0.0})
        atual["lancamentos"] += 1
        atual["valor"] += item["valor"]
    return sorted(mapa.values(), key=lambda g: -g["valor"])


def _data_curta(valor: Any) -> str:
    """`Data_Baixa` como `YYYY-MM-DD`, para montar a chave de junção."""
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return ""


def _codigo_departamento(linha: dict[str, Any]) -> str:
    return ".".join(str(linha.get(f"CodDpto{n}") or 0) for n in (1, 2, 3, 4))


def _chave_classificacao(
    empresa: str,
    documento: str,
    serie: str,
    fornecedor: str,
    parcela: str,
    data_baixa: str,
) -> tuple[str, str, str, str, str]:
    return (empresa, f"{documento}{serie}", fornecedor, parcela, data_baixa)


def _classificacoes(
    inicio: date, fim: date
) -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    """Despesa/departamento de cada baixa no período, indexados pela chave.

    A procedure devolve `Documento` já com a série grudada, e `Data_Baixa` como
    `smalldatetime`. Quando a chave repete (parcela duplicada no mesmo dia), vence
    a linha de maior valor e a baixa é marcada com `rateio`.
    """
    linhas = erp.ultimo_resultado(SQL_CLASSIFICACAO, (inicio, fim, fim))
    indice: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for linha in linhas:
        chave = (
            _texto(linha.get("Empresa")),
            _texto(linha.get("Documento")),
            _texto(linha.get("CodFornecedor")),
            _texto(linha.get("PArcela")),
            _data_curta(linha.get("Data_Baixa")),
        )
        classificacao = {
            "departamento": _texto(linha.get("DescDpto4")),
            "departamento_codigo": _codigo_departamento(linha),
            "despesa": _texto(linha.get("DescDesp1")),
            "despesa_2": _texto(linha.get("DescDesp2")),
        }
        valor = abs(_numero(linha.get("Valor_Baixado")))
        anterior = indice.get(chave)
        if anterior is None:
            indice[chave] = {**classificacao, "rateio": False, "valor_avaliado": valor}
            continue
        # Chave repetida: a procedure rateou entre linhas. A baixa fica com a linha
        # maior e oGroups somam o `Valor_Pago` da baixa, não o rateio.
        if valor > anterior["valor_avaliado"]:
            indice[chave] = {**classificacao, "rateio": True, "valor_avaliado": valor}
        else:
            anterior["rateio"] = True
    for classificacao in indice.values():
        classificacao.pop("valor_avaliado", None)
    return indice


@router.get("/contas-pagas-detalhe")
def contas_pagas_detalhe(
    usuario: _financeiro,
    data: date | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> dict[str, Any]:
    """As baixas de contas pagas do mês de referência e as 4 janelas do card.

    `data` (opcional, padrão hoje) ancora o mês: o card compara esse mês com o
    anterior, o acumulado do ano e o ano anterior.

    `data_inicio`/`data_fim` (ambos inclusive) recortam a lista e os grupos. Sem
    eles, a lista é o mês inteiro. Os cards são as janelas fixas do mês âncora — é
    o que o card do BI mede — e `periodo` diz o recorte que a tela está mostrando,
    para não haver dúvida entre o total do card e o da lista. O card "Mês atual"
    (`mes`) mede a janela do mês âncora, **não** a lista: com recorte, a lista é o
    período inteiro e inflaria o card.

    **Modo "Todos".** Quando `data` não vem, a âncora dos 4 cards fixos é hoje (a
    tela usa `referencia` para preencher a data final), mas a lista e os grupos
    são o intervalo `data_inicio`..`data_fim` inteiro — é o que a tela chama de
    "Todos os meses". `periodo` traz `total`/`lancamentos` do intervalo, para o
    card do período não depender de somar os itens na tela; `mes` continua sendo a
    janela de hoje, para o card "Mês atual" não herdar o total do período.

    Os lançamentos das outras três janelas entram como total e contagem, que é
    tudo que o card mostra.
    """
    referencia = data or date.today()
    janelas = _janelas(referencia)
    inicio_mes, fim_mes = janelas["mes"]

    if data_inicio and data_fim and data_inicio > data_fim:
        raise HTTPException(
            status_code=422, detail="data_inicio não pode ser depois de data_fim"
        )

    inicio_lista = data_inicio or inicio_mes
    fim_lista = (data_fim + timedelta(days=1)) if data_fim else fim_mes

    inicio_serie = date(referencia.year - 2, 1, 1)
    mensal: dict[tuple[int, int], dict[str, Any]] = {}
    for linha in erp.query(SQL_SERIE, (inicio_serie, max(fim_mes, fim_lista))):
        mes = linha["mes"]
        mensal[(mes.year, mes.month)] = {
            "total": float(linha["total"] or 0),
            "lancamentos": int(linha["lancamentos"] or 0),
        }

    def bloco(nome: str, rotulo: str) -> dict[str, Any]:
        ini, f = janelas[nome]
        valores = [
            dados
            for (ano, m), dados in mensal.items()
            if ini <= date(ano, m, 1) < f
        ]
        return {
            **_periodo(rotulo, ini, f),
            "total": sum(d["total"] for d in valores),
            "lancamentos": sum(d["lancamentos"] for d in valores),
        }

    linhas = erp.query(SQL_ITENS, (inicio_lista, fim_lista))
    classificacoes = _classificacoes(inicio_lista, fim_lista)
    itens = [_item(linha) for linha in linhas]
    for item in itens:
        classificacao = classificacoes.get(
            _chave_classificacao(
                item["empresa"],
                item["documento"],
                item["serie"],
                item["fornecedor"],
                item["parcela"],
                item["data_baixa"] or "",
            )
        )
        item.update(
            classificacao
            or {
                "departamento": "",
                "departamento_codigo": "",
                "despesa": "",
                "despesa_2": "",
                "rateio": False,
            }
        )
    total_lista = sum(item["valor"] for item in itens)

    # A primeira baixa *do que a consulta trouxe*. É o que a tela usa para nascer com
    # a data inicial preenchida: sem isso ela abriria vazia, e o seletor de meses não
    # teria de onde sair. Vem do conjunto retornado, não de uma query à parte.
    datas = [item["data_baixa"] for item in itens if item["data_baixa"]]
    min_data = min(datas) if datas else None

    # 24 meses terminando na referência, para dar contexto às 4 janelas.
    meses = []
    for passo in range(-23, 1):
        chave = _primeiro_dia(_somar_meses(inicio_mes, passo))
        dados = mensal.get((chave.year, chave.month), {"total": 0.0, "lancamentos": 0})
        meses.append(
            {
                "mes": f"{chave.year}-{chave.month:02d}",
                "rotulo": f"{MESES_BR[chave.month][:3]}/{chave.year}",
                "total": dados["total"],
                "lancamentos": dados["lancamentos"],
            }
        )

    recorte_total_mes = inicio_lista == inicio_mes and fim_lista == fim_mes
    return {
        "referencia": {
            **_periodo(
                MESES_BR[inicio_mes.month],
                inicio_mes,
                _proximo_mes(inicio_mes),
            ),
            "mes": f"{inicio_mes.year}-{inicio_mes.month:02d}",
        },
        # O recorte que a lista está mostrando. Igual ao mês âncora quando a tela
        # não mexeu nas datas; a tela mostra a faixa para não confundir com o card.
        # `total`/`lancamentos` são do intervalo — é o 5º card, o "período
        # selecionado", que acompanha as datas em vez das janelas fixas.
        "periodo": {
            **_periodo(
                "Período em exibição" if not recorte_total_mes else MESES_BR[inicio_mes.month],
                inicio_lista,
                fim_lista,
            ),
            "recorte": not recorte_total_mes,
            "total": total_lista,
            "lancamentos": len(itens),
        },
        # A primeira baixa do conjunto consultado, para a tela nascer com a data
        # inicial preenchida (e o seletor de meses saber onde começa).
        "min_data": min_data,
        # O card "Mês atual" mede a janela fixa do mês âncora (a mesma linha do
        # card do BI), não a lista: com "Todos" ou um recorte, a lista é o período
        # inteiro e o número do mês sairia inflado. Os itens/grupos continuam sendo
        # da lista, que é o recorte que a tela está mostrando.
        "mes": {
            **bloco(
                "mes",
                MESES_BR[inicio_mes.month],
            ),
            "itens": itens,
            "por_fornecedor": _agrupar(itens, "razao_social"),
            "por_banco": _agrupar(itens, "banco"),
            "por_empresa": _agrupar(itens, "empresa"),
            "por_departamento": _agrupar(itens, "departamento"),
            "por_despesa": _agrupar(itens, "despesa"),
        },
        "mes_anterior": bloco("mes_anterior", "Mês anterior"),
        "ano_atual": bloco("ano_atual", "Ano atual"),
        "ano_anterior": bloco("ano_anterior", "Ano anterior"),
        "meses": meses,
    }


__all__ = ["router"]
