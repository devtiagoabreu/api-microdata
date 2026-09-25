# Arquitetura da nova API (fase de design)

Documentos de **design** da nova API Python que substitui a API legada (`docs/legado/oraculum`),
alinhados ao plano de dados do [Estudo 22](../estudo/22-arquitetura-neon-etl.md).

| # | Documento | Conteúdo | Status |
|---|-----------|----------|--------|
| 43 | [Arquitetura alvo da nova API](./43-arquitetura-alvo-api.md) | Legado `oraculum` → **Postgres local** (warehouse `raw`/`core`/`marts`/`etl`) + **Neon enxuto** (só agregados pequenos de dashboard; `public` do app intocado), ETL incremental, sync on-demand via API | ✔ |
| 44 | [Contratos da API](./44-contratos-api-oraculum.md) | 17 rotas do legado mapeadas → fonte ERP → mart Neon → contrato JSON | ✔ |
| 45 | [Plano de implementação](./45-plano-de-implementacao.md) | Tudo a fazer (fases B–F), decisões pendentes (D1–D8), estrutura do `app/`, ordem de execução, critérios de aceite | ✔ |

Contexto nos estudos: [Estudo 21 (BI/DBProDash)](../estudo/21-bi-power-bi.md),
[Estudo 22 (arquitetura Neon/ETL)](../estudo/22-arquitetura-neon-etl.md),
[Estudo 41 (usuários/segurança)](../estudo/41-usuarios-acessos-seguranca.md),
[Estudo 42 (infra/RLS)](../estudo/42-infra-topologia-infraestrutura.md).