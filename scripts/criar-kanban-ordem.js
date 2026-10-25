const { Client } = require('pg');
(async()=>{
  const c = new Client({connectionString: process.env.DATABASE_URL_LOCAL});
  await c.connect();
  await c.query(create table if not exists public.wms_kanban_ordem (id bigserial primary key, tipo varchar(10) not null, chave varchar(80) not null, empresa varchar(10), pedido varchar(20), separacao_id bigint, coluna varchar(40) not null, posicao integer not null default 0, atualizado_em timestamp not null default now(), atualizado_por bigint, constraint uq_wms_kanban_ordem unique (tipo,chave,coluna)););
  await c.query(create index if not exists idx_wms_kanban_ordem_tipo_coluna on public.wms_kanban_ordem (tipo,coluna,posicao););
  console.log('ok');
  await c.end();
})();