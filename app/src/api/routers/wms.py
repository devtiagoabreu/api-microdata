"""WMS: enderecos, alocacao de pecas e movimentos no Postgres local.

O modulo WMS **nao** roda no dgbcomex (Vercel): o front chama as rotas Next.js, que fazem
proxy autenticado para ca. A escrita vai para `public.wms_*` no warehouse local
(`DATABASE_URL_LOCAL`) e a leitura do estoque em aberto continua sendo o `raw` do ERP,
somente leitura (`cte_peca` menos `cte_baixa`).

Escopo: as rotas exigem `estoque:leitura` (o usuario de servico do dgbcomex ja tem). A
autorizacao por usuario final fica no dgbcomex; aqui a API confia no token de servico.

Auditoria: o dgbcomex manda o `usuarioId` do seu proprio `usuarios.id` no corpo do
movimento, e o identificador do rolo/peca e gravado tambem no movimento (`nro_rolo`/
`nro_peca`), para o historico sobreviver a saida da peca do estoque.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.api.auth.escopos import ESCOPO_ESTOQUE, exigir_escopo
from src.api.auth.usuarios import Usuario
from src.db import warehouse

router = APIRouter(tags=["wms"])

_dependente = Annotated[Usuario | None, Depends(exigir_escopo(ESCOPO_ESTOQUE))]

TIPOS_ENDERECO = ("PULMAO", "PICKING", "EXPEDICAO", "AVARIA")
TIPOS_MOVIMENTO = ("ENTRADA", "SAIDA", "TRANSFERENCIA", "AJUSTE")
LIMITE_MAX = 500


class Modelo(BaseModel):
    """Corpo em camelCase (o dgbcomex manda assim) e aceita snake_case tambem."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class PecaEntrada(Modelo):
    empresa: str | None = None
    nro_rolo: str
    nro_peca: str
    produto: str | None = None
    categoria: str | None = None
    cor: str | None = None
    desenho: str | None = None
    variante: str | None = None
    largura: str | None = None
    metros: float | None = None
    peso: float | None = None
    situacao: str | None = None
    lote_interno: str | None = None
    data_entrada: str | None = None


class NovoEndereco(Modelo):
    codigo: str
    tipo: str = "PULMAO"
    zona: str | None = None
    rua: str | None = None
    predio: str | None = None
    nivel: str | None = None
    apto: str | None = None
    capacidade: Decimal | None = None
    observacoes: str | None = None


class NovoMovimento(Modelo):
    tipo: str
    estoque_id: int | None = None
    endereco_destino_id: int | None = None
    usuario_id: int | None = None
    observacao: str | None = None
    peca: PecaEntrada | None = None


def _texto(valor: str | None) -> str | None:
    if valor is None:
        return None
    limpo = valor.strip()
    return limpo or None


def _decimal_texto(valor: Any) -> str | None:
    """Igual ao Drizzle: coluna `numeric` sai como string para nao perder escala."""
    return None if valor is None else f"{valor:f}"


def _float(valor: Any) -> float | None:
    return None if valor is None else float(valor)


def _data(valor: Any) -> str | None:
    return valor.isoformat() if valor is not None and hasattr(valor, "isoformat") else valor


def _endereco(linha: Any) -> dict[str, Any]:
    return {
        "id": linha["id"],
        "codigo": linha["codigo"],
        "tipo": linha["tipo"],
        "zona": linha["zona"],
        "rua": linha["rua"],
        "predio": linha["predio"],
        "nivel": linha["nivel"],
        "apto": linha["apto"],
        "capacidade": _decimal_texto(linha["capacidade"]),
        "ativo": linha["ativo"],
        "observacoes": linha["observacoes"],
        "createdAt": _data(linha["created_at"]),
        "updatedAt": _data(linha["updated_at"]),
    }


def _movimento(linha: Any) -> dict[str, Any]:
    return {
        "id": linha["id"],
        "tipo": linha["tipo"],
        "estoqueId": linha["estoqueId"],
        "nroRolo": linha["nroRolo"],
        "nroPeca": linha["nroPeca"],
        "origem": linha["origem"],
        "destino": linha["destino"],
        "usuarioId": linha["usuarioId"],
        "metros": _decimal_texto(linha["metros"]),
        "peso": _decimal_texto(linha["peso"]),
        "observacao": linha["observacao"],
        "createdAt": _data(linha["createdAt"]),
    }


def _existe_endereco(conn: Any, endereco_id: int) -> bool:
    return (
        conn.execute(
            text("select 1 from public.wms_enderecos where id = :id"),
            {"id": endereco_id},
        ).first()
        is not None
    )


SQL_MOVIMENTOS = """
select
    m.id,
    m.tipo,
    m.estoque_id            as "estoqueId",
    coalesce(m.nro_rolo, e.nro_rolo) as "nroRolo",
    coalesce(m.nro_peca, e.nro_peca) as "nroPeca",
    o.codigo                as origem,
    d.codigo                as destino,
    m.usuario_id            as "usuarioId",
    m.metros,
    m.peso,
    m.observacao,
    m.created_at            as "createdAt"
from public.wms_movimentos m
left join public.wms_estoque e on e.id = m.estoque_id
left join public.wms_enderecos o on o.id = m.endereco_origem_id
left join public.wms_enderecos d on d.id = m.endereco_destino_id
{onde}
order by m.created_at desc, m.id desc
{limite}
"""


def _movimento_por_id(conn: Any, movimento_id: int) -> dict[str, Any]:
    linha = conn.execute(
        text(SQL_MOVIMENTOS.format(onde="where m.id = :id", limite="limit 1")),
        {"id": movimento_id},
    ).mappings().one()
    return _movimento(linha)


def _inserir_movimento(
    conn: Any,
    *,
    tipo: str,
    estoque_id: int | None,
    nro_rolo: str | None,
    nro_peca: str | None,
    endereco_origem_id: int | None,
    endereco_destino_id: int | None,
    usuario_id: int | None,
    metros: Any = None,
    peso: Any = None,
    observacao: str | None = None,
) -> dict[str, Any]:
    linha = conn.execute(
        text(
            """
            insert into public.wms_movimentos (
                tipo, estoque_id, nro_rolo, nro_peca,
                endereco_origem_id, endereco_destino_id,
                usuario_id, metros, peso, observacao
            ) values (
                :tipo, :estoque_id, :nro_rolo, :nro_peca,
                :origem, :destino,
                :usuario_id, :metros, :peso, :observacao
            )
            returning id
            """
        ),
        {
            "tipo": tipo,
            "estoque_id": estoque_id,
            "nro_rolo": nro_rolo,
            "nro_peca": nro_peca,
            "origem": endereco_origem_id,
            "destino": endereco_destino_id,
            "usuario_id": usuario_id,
            "metros": metros,
            "peso": peso,
            "observacao": _texto(observacao),
        },
    ).scalar_one()
    return _movimento_por_id(conn, linha)


@router.get("/wms/dashboard")
def dashboard(usuario: _dependente) -> dict[str, Any]:
    """Resumo do armazem + pecas em aberto (somente leitura no `raw`)."""
    with warehouse.engine().connect() as conn:
        enderecos = conn.execute(
            text("select count(*)::int from public.wms_enderecos")
        ).scalar_one()
        ativos = conn.execute(
            text("select count(*)::int from public.wms_enderecos where ativo")
        ).scalar_one()
        alocadas = conn.execute(
            text(
                "select count(*)::int, coalesce(sum(metros), 0)::float8 "
                "from public.wms_estoque"
            )
        ).one()
        movimentos_hoje = conn.execute(
            text(
                "select count(*)::int from public.wms_movimentos "
                "where created_at >= date_trunc('day', now())"
            )
        ).scalar_one()
        em_aberto = conn.execute(
            text(SQL_CONTAR_ABERTAS.format(busca=""))
        ).scalar_one()

    return {
        "enderecos": enderecos,
        "enderecosAtivos": ativos,
        "pecasAlocadas": alocadas[0],
        "metrosAlocados": float(alocadas[1] or 0),
        "pecasEmAberto": em_aberto,
        "movimentosHoje": movimentos_hoje,
    }


@router.get("/wms/enderecos")
def listar_enderecos(usuario: _dependente) -> list[dict[str, Any]]:
    """Todos os enderecos, ordenados pelo codigo."""
    with warehouse.engine().connect() as conn:
        linhas = conn.execute(
            text("select * from public.wms_enderecos order by codigo")
        ).mappings()
        return [_endereco(linha) for linha in linhas]


@router.post("/wms/enderecos", status_code=status.HTTP_201_CREATED)
def criar_endereco(dados: NovoEndereco, usuario: _dependente) -> dict[str, Any]:
    """Cria um endereco. Codigo e unico; tipo invalido cai em `PULMAO` (paridade com o front)."""
    codigo = _texto(dados.codigo)
    if codigo is None:
        raise HTTPException(status_code=400, detail="Código do endereço é obrigatório")
    tipo = dados.tipo if dados.tipo in TIPOS_ENDERECO else "PULMAO"

    try:
        with warehouse.engine().begin() as conn:
            linha = conn.execute(
                text(
                    """
                    insert into public.wms_enderecos
                        (codigo, tipo, zona, rua, predio, nivel, apto, capacidade, observacoes)
                    values
                        (:codigo, :tipo, :zona, :rua, :predio, :nivel, :apto, :capacidade,
                         :observacoes)
                    returning *
                    """
                ),
                {
                    "codigo": codigo,
                    "tipo": tipo,
                    "zona": _texto(dados.zona),
                    "rua": _texto(dados.rua),
                    "predio": _texto(dados.predio),
                    "nivel": _texto(dados.nivel),
                    "apto": _texto(dados.apto),
                    "capacidade": dados.capacidade,
                    "observacoes": _texto(dados.observacoes),
                },
            ).mappings().one()
    except IntegrityError as erro:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um endereço com este código",
        ) from erro

    return _endereco(linha)


SQL_ABERTAS = """
select
    a.empresa,
    a.nro_rolo,
    a.nro_peca,
    a.produto,
    a.categoria,
    a.cor,
    a.desenho,
    a.variante,
    a.largura,
    cast(a.metros as double precision) as metros,
    cast(a.peso as double precision) as peso,
    a.situacao,
    a.lote_interno,
    to_char(a.data_entrada, 'YYYY-MM-DD') as data_entrada
from raw.cte_peca a
where not exists (
    select 1
    from raw.cte_baixa b
    where b.empresa = a.empresa
      and b.nro_rolo = a.nro_rolo
      and b.nro_peca = a.nro_peca
)
  and a.nro_rolo_origem is null
  and not exists (
    select 1
    from public.wms_estoque w
    where w.nro_rolo = a.nro_rolo
      and w.nro_peca = a.nro_peca
  )
{busca}
order by a.nro_rolo desc, a.nro_peca desc
limit :limite offset :offset
"""

SQL_CONTAR_ABERTAS = """
select count(*)::int
from raw.cte_peca a
where not exists (
    select 1
    from raw.cte_baixa b
    where b.empresa = a.empresa
      and b.nro_rolo = a.nro_rolo
      and b.nro_peca = a.nro_peca
)
  and a.nro_rolo_origem is null
  and not exists (
    select 1
    from public.wms_estoque w
    where w.nro_rolo = a.nro_rolo
      and w.nro_peca = a.nro_peca
  )
{busca}
"""

FILTRO_BUSCA = (
    "  and (a.nro_rolo ilike :busca or a.produto ilike :busca "
    "or a.cor ilike :busca or a.lote_interno ilike :busca)"
)


@router.get("/wms/estoque")
def listar_estoque(
    usuario: _dependente,
    busca: str = Query("", description="Rolo, produto, cor ou lote interno"),
    limite: int = Query(50, ge=1, le=LIMITE_MAX),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Pecas em aberto no ERP (sem baixa e ainda nao alocadas no WMS)."""
    termo = busca.strip()
    filtro = FILTRO_BUSCA if termo else ""
    params: dict[str, Any] = {"limite": limite, "offset": offset}
    if termo:
        params["busca"] = f"%{termo}%"

    sql = SQL_ABERTAS.format(busca=filtro)
    with warehouse.engine().connect() as conn:
        itens = [
            dict(linha)
            for linha in conn.execute(text(sql), params).mappings()
        ]
        total = conn.execute(
            text(SQL_CONTAR_ABERTAS.format(busca=filtro)), params
        ).scalar_one()

    return {"itens": itens, "total": total}


@router.get("/wms/estoque/alocado")
def listar_alocadas(usuario: _dependente) -> list[dict[str, Any]]:
    """Pecas alocadas, com o codigo do endereco."""
    with warehouse.engine().connect() as conn:
        linhas = conn.execute(
            text(
                """
                select
                    e.id,
                    e.nro_rolo     as "nroRolo",
                    e.nro_peca     as "nroPeca",
                    e.endereco_id  as "enderecoId",
                    a.codigo       as "enderecoCodigo",
                    e.metros,
                    e.peso
                from public.wms_estoque e
                join public.wms_enderecos a on a.id = e.endereco_id
                order by a.codigo, e.nro_rolo
                """
            )
        ).mappings()
        return [
            {
                "id": linha["id"],
                "nroRolo": linha["nroRolo"],
                "nroPeca": linha["nroPeca"],
                "enderecoId": linha["enderecoId"],
                "enderecoCodigo": linha["enderecoCodigo"],
                "metros": _decimal_texto(linha["metros"]),
                "peso": _decimal_texto(linha["peso"]),
            }
            for linha in linhas
        ]


@router.get("/wms/movimentos")
def listar_movimentos(
    usuario: _dependente,
    limite: int = Query(50, ge=1, le=LIMITE_MAX),
) -> list[dict[str, Any]]:
    """Historico de movimentos, mais recente primeiro."""
    with warehouse.engine().connect() as conn:
        linhas = conn.execute(
            text(SQL_MOVIMENTOS.format(onde="", limite="limit :limite")),
            {"limite": limite},
        ).mappings()
        return [_movimento(linha) for linha in linhas]


@router.post("/wms/movimentos", status_code=status.HTTP_201_CREATED)
def registrar_movimento(dados: NovoMovimento, usuario: _dependente) -> dict[str, Any]:
    """ENTRADA aloca; TRANSFERENCIA muda o endereco; SAIDA remove; AJUSTE so registra."""
    tipo = dados.tipo.strip().upper()
    if tipo not in TIPOS_MOVIMENTO:
        raise HTTPException(status_code=400, detail="Tipo de movimento inválido")

    if tipo == "ENTRADA":
        return _entrada(dados)

    if dados.estoque_id is None:
        raise HTTPException(status_code=400, detail="Peça alocada é obrigatória")

    with warehouse.engine().begin() as conn:
        peca = conn.execute(
            text("select * from public.wms_estoque where id = :id for update"),
            {"id": dados.estoque_id},
        ).mappings().first()
        if peca is None:
            raise HTTPException(status_code=404, detail="Peça alocada não encontrada")

        if tipo == "TRANSFERENCIA":
            destino = dados.endereco_destino_id
            if destino is None or not _existe_endereco(conn, destino):
                raise HTTPException(status_code=400, detail="Endereço de destino inválido")
            conn.execute(
                text(
                    "update public.wms_estoque "
                    "set endereco_id = :destino, updated_at = now() where id = :id"
                ),
                {"destino": destino, "id": peca["id"]},
            )
            movimento = _inserir_movimento(
                conn,
                tipo=tipo,
                estoque_id=peca["id"],
                nro_rolo=peca["nro_rolo"],
                nro_peca=peca["nro_peca"],
                endereco_origem_id=peca["endereco_id"],
                endereco_destino_id=destino,
                usuario_id=dados.usuario_id,
                metros=peca["metros"],
                peso=peca["peso"],
                observacao=dados.observacao,
            )
            return {"movimento": movimento}

        if tipo == "SAIDA":
            movimento = _inserir_movimento(
                conn,
                tipo=tipo,
                estoque_id=peca["id"],
                nro_rolo=peca["nro_rolo"],
                nro_peca=peca["nro_peca"],
                endereco_origem_id=peca["endereco_id"],
                endereco_destino_id=None,
                usuario_id=dados.usuario_id,
                metros=peca["metros"],
                peso=peca["peso"],
                observacao=dados.observacao,
            )
            conn.execute(
                text("delete from public.wms_estoque where id = :id"), {"id": peca["id"]}
            )
            return {"movimento": movimento}

        movimento = _inserir_movimento(
            conn,
            tipo=tipo,
            estoque_id=peca["id"],
            nro_rolo=peca["nro_rolo"],
            nro_peca=peca["nro_peca"],
            endereco_origem_id=peca["endereco_id"],
            endereco_destino_id=None,
            usuario_id=dados.usuario_id,
            metros=peca["metros"],
            peso=peca["peso"],
            observacao=dados.observacao,
        )
        return {"movimento": movimento}


def _entrada(dados: NovoMovimento) -> dict[str, Any]:
    destino = dados.endereco_destino_id
    peca = dados.peca
    if peca is None:
        raise HTTPException(status_code=400, detail="Dados da peça são obrigatórios")

    nro_rolo = _texto(peca.nro_rolo)
    nro_peca = _texto(peca.nro_peca)
    if nro_rolo is None or nro_peca is None:
        raise HTTPException(status_code=400, detail="Nro. Rolo e Nro. Peça são obrigatórios")

    with warehouse.engine().begin() as conn:
        if destino is None or not _existe_endereco(conn, destino):
            raise HTTPException(status_code=400, detail="Endereço de destino inválido")

        nova = conn.execute(
            text(
                """
                insert into public.wms_estoque (
                    endereco_id, empresa, nro_rolo, nro_peca, produto, categoria, cor,
                    desenho, variante, largura, metros, peso, situacao, lote_interno,
                    data_entrada
                ) values (
                    :endereco_id, :empresa, :nro_rolo, :nro_peca, :produto, :categoria, :cor,
                    :desenho, :variante, :largura, :metros, :peso, :situacao, :lote_interno,
                    :data_entrada
                )
                on conflict (nro_rolo, nro_peca) do nothing
                returning *
                """
            ),
            {
                "endereco_id": destino,
                "empresa": _texto(peca.empresa),
                "nro_rolo": nro_rolo,
                "nro_peca": nro_peca,
                "produto": _texto(peca.produto),
                "categoria": _texto(peca.categoria),
                "cor": _texto(peca.cor),
                "desenho": _texto(peca.desenho),
                "variante": _texto(peca.variante),
                "largura": _texto(peca.largura),
                "metros": peca.metros,
                "peso": peca.peso,
                "situacao": _texto(peca.situacao),
                "lote_interno": _texto(peca.lote_interno),
                "data_entrada": _texto(peca.data_entrada) or None,
            },
        ).mappings().first()

        if nova is None:
            raise HTTPException(status_code=409, detail="Esta peça já está alocada")

        movimento = _inserir_movimento(
            conn,
            tipo="ENTRADA",
            estoque_id=nova["id"],
            nro_rolo=nro_rolo,
            nro_peca=nro_peca,
            endereco_origem_id=None,
            endereco_destino_id=destino,
            usuario_id=dados.usuario_id,
            metros=peca.metros,
            peso=peca.peso,
            observacao=dados.observacao,
        )

    return {"movimento": movimento, "peca": _peca_alocada(nova)}


def _peca_alocada(linha: Any) -> dict[str, Any]:
    return {
        "id": linha["id"],
        "enderecoId": linha["endereco_id"],
        "empresa": linha["empresa"],
        "nroRolo": linha["nro_rolo"],
        "nroPeca": linha["nro_peca"],
        "produto": linha["produto"],
        "categoria": linha["categoria"],
        "cor": linha["cor"],
        "desenho": linha["desenho"],
        "variante": linha["variante"],
        "largura": linha["largura"],
        "metros": _decimal_texto(linha["metros"]),
        "peso": _decimal_texto(linha["peso"]),
        "situacao": linha["situacao"],
        "loteInterno": linha["lote_interno"],
        "dataEntrada": _data(linha["data_entrada"]),
        "createdAt": _data(linha["created_at"]),
        "updatedAt": _data(linha["updated_at"]),
    }


__all__ = ["router"]
