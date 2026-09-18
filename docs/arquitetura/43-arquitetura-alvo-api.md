# Arquitetura alvo da nova API (legado `oraculum` → Neon)

> **Data:** 19/set/2026
> **Escopo:** design da nova API Python que substitui a API legada `docs/legado/oraculum`,
> partindo do recon dos 17 endpoints existentes e do plano de dados do [Estudo 22](../estudo/22-arquitetura-neon-etl.md).
> **Restrições:** `DBMicrodata_DGB` é produção **somente leitura** (sem objetos novos); Neon é o
> destino dos dados; o schema do Neon é **contrato** com o front `dgbcomex`.
> **Relações:** Estudos 11–13 (superfície/views), 21–22 (BI/Neon), 28–31 (faturamento, receber, pagar), 34 (estoque de peças), 41 (usuários/segurança), 42 (infra/RLS).

---

## 1. Situação atual (legado `oraculum`)

FastAPI (Python 3.13, `uvicorn`, porta 58244) que **lê o SQL Server a cada request**:

- `database.py` — uma conexão pyodbc por request (`DB_SERVER`, `DB_DATABASE=DBMicrodata_DGB`).
- `main.py` — **17 rotas**: 14 de negócio + 3 utilitárias (`/health`, `/procedures`,
  `/test-procedure/{name}`).
- 12 rotas executam procedures do **`DBProDash`** (BI on-prem) e 3 leem `DBMicrodata_DGB`
  (`/dados` via query inline; `/sugestao-rolos` e `/pdf/sugestao-rolos` via
  `uspEnderecamentoParaAtenderPedidoGeral`).
- Contrato JSON **implícito**: `column → value` sem tipagem; campos `char` com **padding** vazam
  (`Produto`, `Cor`); datas como string `DDMMYYYY`; valores com variante `*_Replace`
  (`Faturamento_Replace` troca `.` por `,` — pt-BR para tela).

### 1.1 Problemas que motivam a substituição

| # | Problema | Consequência |
|---|----------|--------------|
| 1 | Executa procs do `DBProDash` **que escrevem** (`uspRel_CCusto_Niveis*` fazem `TRUNCATE+INSERT`) | Escrita em BI on-prem a cada request; banco avulso que será descartado |
| 2 | `/test-procedure/{name}` = pass-through genérico de `EXEC` | Execução arbitrária de proc (risco/porta de fuga) — **não existe no alvo** |
| 3 | `/dados` faz `fetchall()` em `Cte_Peca` sem paginação | Carga de ~300k peças na memória por request |
| 4 | Data como string `DDMMYYYY` (`formatar_data_para_sql`) | Frágil, sem validação, fuso/ano ambíguo |
| 5 | Sem auth/CORS `*` (`allow_origins=["*"]`) | Qualquer origem lê o BI; sem conceito de usuário/empresa |
| 6 | Conta-pagas `/contas-pagas/{data}`: a proc está com o `SELECT` **comentado** | Retorna `{}` — endpoint vivo na rota, morto no dado |
| 7 | `/sugestao-rolos` executa proc com **cursor** e concatenação `FOR XML PATH` | Não reutilizável no Neon; lógica em SQL Server proprietário |
| 8 | KPI calculado **ao vivo** em cada chamada (mês a mês via `EOMONTH`) | Repete cálculo; pressão síncrona no ERP/BI |
| 9 | Formatos pt-BR no backend (`*_Replace`) | Apresentação misturada com dado; novo deve ser **tipado e neutro** |
| 10 | `test-procedure`/`/procedures` expõem inventário interno | Expor no alvo apenas o necessário |

---

## 2. Arquitetura alvo

`DBMicrodata_DGB (SQL Server, read-only) → ETL Python → Neon/PostgreSQL → dgbcomex`

```
DBMicrodata_DGB (ERP, on-prem, somente leitura)
        │  SELECT (watermark/identidade)
        ▼
   Runner ETL (Python) ────────────►  Neon / PostgreSQL (externo)
   (extract → raw → core → marts)        ├── raw   (espelho das fontes, sem regra)
        ▲                                ├── core  (regras portadas do DBProDash)
        │                                ├── marts (views de consumo dgbcomex + API)
        │                                └── etl   (watermark, execuções, auditoria)
        │
   API Python (FastAPI, serve Neon)          │  leitura DIRETA (Prisma/Drizzle)
   - endpoints compatíveis com oraculum      ▼
   - PDF sugestão-rolos (servidor)    dgbcomex (Next.js + Vercel)

DBProDash (on-prem) = PROTÓTIPO/referência de regra (deixa de ser lido em produção)
```

### 2.1 Papéis

| Componente | Papel |
|------------|-------|
| **ETL (Python)** | Extrai do ERP por watermark/identidade, transforma (trim de `char`, datas, tipos) e carrega `raw`; roda `core`/`marts`; grava auditoria em `etl.*`. Roda **próximo do ERP** (mesma rede on-prem, cron/agendador), pois o Neon não acessa `10.156.0.124`. |
| **API (FastAPI)** | Lê **somente o Neon** (nunca o ERP), re-expondo os **contratos do legado** com tipagem (Pydantic), auth (JWT), multiempresa por token e geração de PDF. |
| **`dgbcomex` (Next.js/Vercel)** | Camada de produto; lê Neon direto. Sem acesso ao ERP. |

> Decisão central: **nenhum request de usuário toca o SQL Server.** O ERP só é lido pelo job
> de ETL (janela/limite de conexões, fora do horário comercial para cargas grandes).
> Exceção documentada: `sugestao-rolos` pode consultar o **mart de peças em aberto**
> (refreshed incremental) ou, opcionalmente, ler o ERP on-demand via `SELECT` read-only
> (lógica em Python, **nunca** `EXEC` de proc).

### 2.2 Fluxo de dados

1. **Bootstrap**: carga full por tabela em ordem de dependência (cadastros → cabeçalhos → itens → logs).
2. **Incremental**: por coluna `watermark` (maior que o último valor persistido) ou, quando não houver,
   **recarga por documento-pai** (delete+insert do documento) — ver mapas do [Estudo 22 §4/§5](../estudo/22-arquitetura-neon-etl.md).
3. **Upsert** pela **chave natural do ERP** (após trim), nunca surrogate.
4. **`etl.watermark`** registra por tabela: coluna, último valor, execução, status, linhas, duração.
5. **Reconciliação** periódica (full leve) para baixas/exclusões sem flag (ex.: `CTE_Baixa`, `Pag_Baixas`).

### 2.3 Modelo de schemas no Neon

| Schema | Conteúdo | Quem lê |
|--------|----------|---------|
| `raw` | Espelho fiel das tabelas-fonte contratadas (colunas originais, `trim`), com colunas de rastreio | somente ETL |
| `core` | Regras portadas das views do `DBProDash` (`vwFaturamento`, `vwContasPagas`, `vwFinanceiroContasReceber/Pagar`, custos) | marts + API |
| `marts` | Views de consumo do `dgbcomex` e da API (KPIs diários, estoque em aberto) | dgbcomex + API |
| `etl` | `watermark`, `execucoes`, `erros`, versionamento | somente ETL |

Convenções (reaproveitando [Estudo 22 §7](../estudo/22-arquitetura-neon-etl.md)):
- identificadores `snake_case` minúsculos; chaves = chave natural do ERP após `trim`.
- datas em `date`/`timestamp`, valores em `numeric`, flags em `char(1)`/`text`.
- timezone padrão **`America/Sao_Paulo`** na gravação.
- **Somente `core`/`marts` são expostos**; `raw` e `etl` privados.

### 2.4 Camada de apresentação/API

- FastAPI + Pydantic (**mesmo JSON shape** dos endpoints atuais, porém tipado e com data ISO).
- **Auth**: JWT com `bcrypt`; escopos derivados de `Usuario_Acessos` (Sistema×Topico —
  [Estudo 41](../estudo/41-usuarios-acessos-seguranca.md)); multiempresa por token
  (padrão `SIS_UsuarioEmpresa` ↔ `Empresas.Id_Empresa`, [Estudo 42 §7](../estudo/42-infra-topologia-infraestrutura.md)).
- **Listagens grandes** (`/dados`): paginação por cursor.
- **PDF** (`/pdf/sugestao-rolos`): continua server-side (reportlab ou weasyprint), agora lendo do mart.
- **CORS** restrito às origens reais do front (nunca `*` com credentials).
- **`/test-procedure` e `/procedures`**: eliminados (exit do contrato).
- **Observabilidade**: `etl.execucoes` + logs estruturados próprios; não reutilizar `Conn_*`/`mic_*`.

---

## 3. Porte do legado para o Neon (referência rápida)

| Legado (`DBProDash`) | Alvo (Neon) |
|----------------------|-------------|
| Proc por request (`uspFaturamento`, `uspDesconto`, …) | **Mart pré-computado** (`marts.faturamento_diario` etc.); API só `SELECT` |
| `uspRel_CCusto_Niveis*` (`TRUNCATE+INSERT`) | Carga idempotente em `core`/`marts` (nunca `TRUNCATE` em produção de outro banco) |
| `EOMONTH`/`CONVERT(...,103)` | Janelas em Python (`dateutil`) sobre coluna `date` |
| `uspEnderecamentoParaAtenderPedidoGeral` (cursor + `FOR XML PATH`) | Reimplementação em Python/Postgres (janela `SUM(Metros) OVER`) |
| `STUFF(...FOR XML PATH())` (pivot de gavetas/rolos) | `string_agg` no Postgres ou agregação em Python |
| `REPLACE(v, '.', ',')` | Removido — formato neutro (numeric); pt-BR é tarefa do front |
| `GETDATE()`/fuso do servidor | `now()` UTC, exibição em `America/Sao_Paulo` |

SQL proprietário → padrões PostgreSQL: [checklist completo no Estudo 22 §6](../estudo/22-arquitetura-neon-etl.md).

---

## 4. Riscos e decisões em aberto

1. **Frequência do ETL do estoque de peças** (317k linhas): define se `sugestao-rolos` é
   mart com refresh diário ou leitura on-demand do ERP. Recomendação: **mart + refresh
   em horário de baixo movimento**, reservando on-demand (read-only) como fallback.
2. **Quando eliminar o `DBProDash`**: só após `core`/`marts` validados número a número
   contra os valores atuais (contrato de regra).
3. **Downtime/convergência**: o dgbcomex lê Neon direto; mudanças de `core`/`marts` são
   **aditivas e versionadas** (alembic) com etapa de transição (criar coluna nova antes de dropar).
4. **Runner ETL on-prem** precisa alcançar `10.156.0.124` (VPN/VM própria) — não roda na Vercel.
5. **Segredos** (ERP e Neon) apenas em `.env` gitignored; a API autentica no ERP read-only
   e no Neon como owner da camada própria.

---

## 5. Roadmap

| Fase | Entrega | Saída |
|------|---------|-------|
| A (design) | Este doc + [contratos](./44-contratos-api-oraculum.md) | Contratos JSON e marts proposto |
| B (scaffold) | Repo `app/`: FastAPI + ETL skeleton, `alembic`, schemas `raw/core/marts/etl` | Código da API |
| C (carga) | Bootstrap full + incremental das tabelas-fonte dos contratos | `raw` populado |
| D (marts) | Portar `vwFaturamento`/`vwContasPagas`/`vwFinanceiro*`/custos + estoque em aberto → `core`/`marts` | Números batendo com o on-prem |
| E (endpoints) | Re-expor os 14 contratos de negócio lendo Neon + PDF; auth; paginação | API substituta |
| F (cutover) | Ponto o dgbcomex para o Neon; desliga legado | Descomissionar `DBProDash` |

---

_Próximo documento: [44 — Contratos da API](./44-contratos-api-oraculum.md)._