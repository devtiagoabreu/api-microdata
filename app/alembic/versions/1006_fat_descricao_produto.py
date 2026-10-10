"""Neon dgbcomex: descricao e unidade do produto no detalhe do faturamento.

O `vwFaturamento` nao traz descricao de produto — ela vive na tabela `Produtos` do
ERP, casada pelo `Codigo` de 6 digitos. Sem estas colunas a tela de detalhe do BI
mostra so `000014`, sem o nome do tecido.

- `descricao_produto`: nome do produto (veludo confort, belga, ...).
- `unidade_produto`: unidade comercial do produto (MT, KG, ...). Os produtos
  têxteis faturados por metro vem como MT, o que confirma o R$/m da tabela de
  produtos do front.

Os dois sao `text` porque a API ja entrega o valor aparado; produto fora do
catalogo fica com `null` em vez de sumir do detalhe.

O revision id tem 32 caracteres no maximo: `alembic_version.version_num` e
varchar(32) e um id maior faz o upgrade falhar no final.

Revision ID: 1006_fat_descricao_produto
Revises: 1005_neon_faturamento_detalhe
Create Date: 2026-10-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

revision: str = "1006_fat_descricao_produto"
down_revision: str | None = "1005_neon_faturamento_detalhe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _engine():
    from src.db import neon

    return neon.engine()


def upgrade() -> None:
    with _engine().begin() as conn:
        conn.execute(
            sa.text(
                "alter table marts.faturamento_detalhe "
                "add column if not exists descricao_produto text"
            )
        )
        conn.execute(
            sa.text(
                "alter table marts.faturamento_detalhe "
                "add column if not exists unidade_produto text"
            )
        )
        conn.execute(
            sa.text(
                "create index if not exists faturamento_detalhe_produto_idx "
                "on marts.faturamento_detalhe (cod_produto)"
            )
        )


def downgrade() -> None:
    with _engine().begin() as conn:
        conn.execute(sa.text("drop index if exists faturamento_detalhe_produto_idx"))
        conn.execute(
            sa.text("alter table marts.faturamento_detalhe drop column if exists unidade_produto")
        )
        conn.execute(
            sa.text("alter table marts.faturamento_detalhe drop column if exists descricao_produto")
        )