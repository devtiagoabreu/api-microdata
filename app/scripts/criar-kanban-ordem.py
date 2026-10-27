from sqlalchemy import text
from src.db.warehouse import engine

DDL = """
create table if not exists public.wms_kanban_ordem (
  id bigserial primary key,
  tipo varchar(10) not null,
  chave varchar(80) not null,
  empresa varchar(10),
  pedido varchar(20),
  separacao_id bigint,
  coluna varchar(40) not null,
  posicao integer not null default 0,
  atualizado_em timestamp not null default now(),
  atualizado_por bigint,
  constraint uq_wms_kanban_ordem unique (tipo, chave, coluna)
)
"""

INDICE = """
create index if not exists idx_wms_kanban_ordem_tipo_coluna
  on public.wms_kanban_ordem (tipo, coluna, posicao)
"""

with engine().begin() as conn:
    conn.execute(text(DDL))
    conn.execute(text(INDICE))
print("ok")
