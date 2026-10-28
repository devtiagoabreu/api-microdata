from sqlalchemy import text

from src.db.warehouse import engine

DDL = """
create table if not exists public.wms_coletor_sincronizacao (
    id bigserial primary key,
    empresa varchar(10),
    pedido varchar(20),
    separacao_id bigint,
    tipo_operacao varchar(20) not null,
    payload jsonb,
    status varchar(20) not null default 'PENDENTE',
    tentativas integer not null default 0,
    erro text,
    criado_em timestamptz not null default now(),
    processado_em timestamptz
);

create index if not exists idx_wms_coletor_sincronizacao_status
    on public.wms_coletor_sincronizacao (status, criado_em);

create table if not exists public.wms_coletor_config (
    id integer not null default 1 primary key,
    ultimo_sync timestamptz,
    ultima_carga_em timestamptz,
    versao_app varchar(20)
);

insert into public.wms_coletor_config (id, ultimo_sync, ultima_carga_em, versao_app)
select 1, null, null, '1.0.0'
where not exists (select 1 from public.wms_coletor_config where id = 1);
"""

with engine().begin() as conn:
    conn.execute(text(DDL))
print("ok")
