"""Neon dgbcomex: detalhe do faturamento para a tela de detalhe do BI (D7).

O card de Faturamento do BI ganhou uma tela de detalhe (12 meses, com numero da nota,
pedido, romaneio, data, cliente, representante, quantidade e valor por item). A fonte
primaria continua o ERP ao vivo (query de detalhe de `vwFaturamento` + `Fat_Pedido` +
`Fat_Vend_Pedido` + `Rec_Vendedores`), mas o volume (~5 mil itens em 12 meses) compensa
guardar no Neon: a tela carrega a base uma vez, atualiza so o delta e, entre as
atualizacoes, le do cache do navegador (IndexedDB).

- `faturamento_detalhe`: grao de **item de nota** (empresa + pedido + item + numero da
  nota). Todos os campos de texto sao `text` porque os campos char/var do SQL Server vem
  com espacos no final e a API ja entrega trimmed; os numericos seguem como `numeric`.
- `faturamento_detalhe_estado`: linha unica (`id = 1`) com o marcador de sincronizacao -
  `carga_completa`, `contagem` (itens no Neon) e `ultima_data` (maior `Data_Nota`
  carregada), que e o watermark do `sync` diferencial.

Revision ID: 1005_neon_faturamento_detalhe
Revises: 1004_neon_escopos
Create Date: 2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

revision: str = "1005_neon_faturamento_detalhe"
down_revision: str | None = "1004_neon_escopos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DETALHE = """
create table if not exists marts.faturamento_detalhe (
    empresa              text not null,
    pedido               text not null,
    item                 integer not null,
    nr_nota              text not null,
    data_nota            date,
    cliente              text,
    nome_cliente         text,
    cod_produto          text,
    metros               numeric,
    vr_unitario          numeric,
    vr_total             numeric,
    acres_desc           numeric,
    peso                 numeric,
    vr_nota              numeric,
    romaneio             text,
    representante_codigo text,
    representante        text,
    atualizado_em        timestamptz not null default now(),
    primary key (empresa, pedido, item, nr_nota)
)
"""

ESTADO = """
create table if not exists marts.faturamento_detalhe_estado (
    id             integer primary key check (id = 1),
    carga_completa boolean not null default false,
    contagem       bigint not null default 0,
    ultima_data    date,
    atualizado_em  timestamptz not null default now()
)
"""


def _engine():
    from src.db import neon

    return neon.engine()


def upgrade() -> None:
    with _engine().begin() as conn:
        conn.execute(sa.text(DETALHE))
        conn.execute(
            sa.text(
                "create index if not exists faturamento_detalhe_data_idx "
                "on marts.faturamento_detalhe (data_nota)"
            )
        )
        conn.execute(sa.text(ESTADO))
        conn.execute(
            sa.text(
                "insert into marts.faturamento_detalhe_estado (id) values (1) "
                "on conflict (id) do nothing"
            )
        )
        conn.execute(
            sa.text(
                "COMMENT ON TABLE marts.faturamento_detalhe IS "
                "'itens de nota do faturamento (12 meses) para a tela de detalhe do BI'"
            )
        )
        conn.execute(
            sa.text(
                "COMMENT ON TABLE marts.faturamento_detalhe_estado IS "
                "'marcador de sync do detalhe: watermark ultima_data e contagem'"
            )
        )


def downgrade() -> None:
    with _engine().begin() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS marts.faturamento_detalhe_estado"))
        conn.execute(sa.text("DROP TABLE IF EXISTS marts.faturamento_detalhe"))