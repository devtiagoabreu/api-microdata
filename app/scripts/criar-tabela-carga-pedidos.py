"""Tabela de estado da carga de pedidos do WMS (idempotente)."""

from sqlalchemy import text

from src.db.warehouse import engine

SQL = """
create table if not exists public.wms_carga_pedidos_estado (
    id integer not null default 1,
    carga_completa boolean not null default false,
    contagem integer not null default 0,
    ultima_data timestamptz,
    atualizado_em timestamptz not null default now(),
    primary key (id)
);

create or replace function public.wms_set_carga_pedidos_estado(
    p_carga_completa boolean,
    p_contagem integer,
    p_ultima_data timestamptz
) returns void language plpgsql as $$
begin
    insert into public.wms_carga_pedidos_estado
        (id, carga_completa, contagem, ultima_data, atualizado_em)
    values (1, p_carga_completa, p_contagem, p_ultima_data, now())
    on conflict (id) do update
        set carga_completa = excluded.carga_completa,
            contagem = excluded.contagem,
            ultima_data = excluded.ultima_data,
            atualizado_em = now();
end;
$$;

create or replace function public.wms_get_carga_pedidos_estado()
returns table (
    carga_completa boolean,
    contagem integer,
    ultima_data timestamptz,
    atualizado_em timestamptz
) language sql as $$
    select carga_completa, contagem, ultima_data, atualizado_em
    from public.wms_carga_pedidos_estado
    where id = 1;
$$;
"""

with engine().begin() as conn:
    conn.execute(text(SQL))

print("ok")
