"""Arquivamento de pedidos e ordens de separacao do WMS (idempotente)."""

from sqlalchemy import text

from src.db.warehouse import engine

SQL = """
alter table public.wms_separacoes
    add column if not exists arquivada_em timestamptz,
    add column if not exists arquivada_por bigint;

create table if not exists public.wms_pedidos_arquivados (
    empresa varchar(10) not null,
    pedido varchar(20) not null,
    situacao_id bigint,
    arquivado_em timestamptz not null default now(),
    arquivado_por bigint,
    primary key (empresa, pedido)
);

create index if not exists idx_wms_pedidos_arquivados_data
    on public.wms_pedidos_arquivados (arquivado_em desc);

create index if not exists idx_wms_separacoes_arquivada
    on public.wms_separacoes (arquivada_em)
    where arquivada_em is not null;
"""

with engine().begin() as conn:
    conn.execute(text(SQL))

print("ok")
