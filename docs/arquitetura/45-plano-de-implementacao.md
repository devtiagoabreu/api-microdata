# Plano de implementação (do design à troca da API legada)

> **Data:** 19/set/2026
> **Situação:** conclusão da **Fase A (design)** — estudos 03–42 + Docs 43/44. Este documento
> detalha **tudo o que vamos fazer** dali em diante: decisões pendentes, tarefas por fase,
> estrutura de código, ordem de execução e critérios de aceite.
> **Não é design congelado:** será corrigido à medida que a implementação levantar fatos novos
> (como nos estudos).

---

## 1. Onde estamos e para onde vamos

Concluído (Fase A):
- Mapa de módulos do ERP (estudos 03–42) e arquitetura-alvo ([Doc 43](./43-arquitetura-alvo-api.md)).
- Contratos da API legada → Neon ([Doc 44](./44-contratos-api-oraculum.md)) e plano de dados/ETL
  ([Estudo 22](../estudo/22-arquitetura-neon-etl.md)).

A partir daqui, **na ordem**, faremos:

```
B. Scaffold do projeto (app/)      → código base + schemas Neon
C. ETL: bootstrap raw + incremental → dados no Neon
D. core/marts (regras de negócio)  → o "DBProDash" portado
E. Endpoints da API lendo Neon    → substitui o oraculum (14 contratos)
F. Cutover e descomissionamento   → dgbcomex no Neon, DBProDash fora
```

Regra transversal (manter sempre): **nunca** escrever no `DBMicrodata_DGB`; credenciais só em
`.env` gitignored; schema `core`/`marts` do Neon = contrato (mudanças aditivas e versionadas);
**o `public` do Neon é do app dgbcomex** (drizzle) — o api-microdata não altera nada lá e cria
somente `raw`/`core`/`marts`/`etl`.

---

## 2. Decisões pendentes (confirmar antes de codar)

| # | Decisão | Opções | Recomendação | Bloqueia |
|---|---------|--------|--------------|----------|
| D1 | **Neon**: criar projeto/database/branch | Branches por fase (dev/prod) | ✔ **resolvida**: Neon `dgbcomex` já criado e migrado (118 tabelas em `public`) | B,C |
| D2 | **Credenciais** do Neon | `DATABASE_URL` no `.env` local (gitignored) | ✔ **resolvida**: `DATABASE_URL` (+ `DB_*` do ERP) no `app/.env` e no `dgbcomex/.env.local` | B |
| D3 | **Runner do ETL** | VM on-prem (mesma rede do ERP) / máquina dev / CI | VM on-prem com cron; máquina dev para desenvolver | C |
| D4 | **Frequência do ETL** | diária / horária / on-demand | diária fora do expediente; estoque de peças pode ter janela extra | C,D |
| D5 | **Auth do alvo** | reusar tabela `usuario` (senha em **texto claro** — ruim) vs auth nova JWT+bcrypt | **auth nova** (JWT+bcrypt), escopos derivados de `Usuario_Acessos` | E |
| D6 | **Multiempresa** | `Codigo_Empresas` (`char(2)`) imbutido por token vs header | empresa do token (padrão `SIS_UsuarioEmpresa`); suportar `?empresa=13` p/ dev | E |
| D7 | **`/contas-pagas`** | reabrir como resumo vs lista vs manter `{}` | **resumo** `{ValorPago, QtdeBaixas}` do mês + lista paginada | E |
| D8 | **PDF** | reportlab (mantém) vs weasyprint | reportlab (mesmo layout, zero refactor) | E |

> Toda decisão tem impacto documentável: confirmar com o usuário **antes** de iniciar a fase que
> ela bloqueia (coluna "Bloqueia"). As recomendações são o default a adotar se não houver objeção.

---

## 3. Fase B — Scaffold do projeto (`app/`)

Objetivo: esqueleto executável com schemas no Neon (vazio) e convenções prontas.

### 3.1 Estrutura de código

```
app/
├─ pyproject.toml              # deps: fastapi, uvicorn, pydantic(-settings), pyodbc,
│                              #       psycopg[binary], SQLAlchemy, alembic, reportlab,
│                              #       bcrypt, PyJWT, python-dateutil, python-dotenv
├─ alembic/                    # migrations do Neon — SOMENTE schemas raw/core/marts/etl
│  └─ env.py                   # public NÃO é gerenciado aqui (é do app dgbcomex/drizzle)
├─ .env                        # gitignored (DB_* do ERP + DATABASE_URL do Neon)
├─ src/
│  ├─ config.py                # pydantic-settings; carrega .env
│  ├─ db/
│  │  ├─ erp.py                # pyodbc → DBMicrodata_DGB (somente leitura)
│  │  └─ neon.py               # engine SQLAlchemy + pooling Neon (schemas raw/core/marts/etl)
│  ├─ integracao/              # leitura de public (produto dgbcomex) via marts, sem DDL/DML ali
│  ├─ etl/
│  │  ├─ bootstrap.py          # carga full em ordem de dependência
│  │  ├─ incremental.py        # por watermark / por documento-pai
│  │  ├─ reconcile.py          # reconciliação (baixas/exclusões sem flag)
│  │  ├─ extract/              # 1 módulo por domínio (faturamento, estoque, financeiro…)
│  │  ├─ transform/            # trim de char, tipos, datas, timezone
│  │  └─ load/                 # upsert no Neon (chave natural do ERP)
│  └─ api/
│     ├─ main.py               # FastAPI; CORS restrito; docs OpenAPI
│     ├─ auth/                 # JWT + bcrypt + escopos (D5)
│     ├─ routers/              # 1 módulo por grupo de rotas (dashboard, estoque, pdf)
│     ├─ schemas/              # Pydantic = contrato (mesmo JSON do legado, tipado)
│     └─ pdf/                  # sugestao_rolos → PDF (reportlab)
```

### 3.2 Migrations iniciais (alembic)

| Migration | Cria |
|-----------|------|
| `0001_etl` | schema `etl` + `etl.watermark` (tabela, coluna, ultimo_valor, ultima_exec, status, linhas, levou_s) + `etl.execucoes` + `etl.erros` |
| `0002_raw` | schema `raw` + tabelas das fontes (espelho, `trim`), vazio |
| `0003_core` | schema `core` + regras (faturamento, contas pagas, financeiro programado, estoque em aberto) |
| `0004_marts` | schema `marts` + views de consumo (KPIs diários) |

Critério de aceite B: `alembic upgrade head` sobe os 4 schemas; `/health` responde no Neon; ETL
consegue conectar no ERP (read-only).

---

## 4. Fase C — ETL: bootstrap `raw` + incremental

Objetivo: dados das fontes dos contratos no `raw` (sem regra), confiáveis e idempotentes.

### 4.1 Tabelas-fonte por domínio (contratos da Doc 44)

| Domínio | Tabelas-fonte (ERP) | Watermark/estratégia (referência) |
|---------|---------------------|-----------------------------------|
| Cadastros | `Clientes_Principal`, `Produtos`, `Produtos_Tecidos`, `Fornecedores` (view), `Rec_Vendedores`, `Condicoes_Pagto`, `Sistemas/Usuarios` (p/ auth) | `Ult_Atualizacao`/full — Estudo 22 §5 |
| Faturamento | `Fat_Pedido`, `Fat_Itens_Pedido`, `Fat_Nat_Pedido`, `Fat_Parc_Pedido` | conferir watermark (`Data_Nota`/`Ult_*`) — Estudo 29 |
| Contas a pagar | `NF_Entradas`, `NFE_Parcelas`, `Pag_Baixas`, `Pag_Historicos`, `Pag_Operacoes`, `Bancos` + rateios `NFE_CCustos_*`, `Pag_DespesasReceitas`, `Pag_CCusto_Departamento` | `Data_Hora`/`Data_Hora_Baixa`; itens sem data por pai — Estudo 31 |
| Contas a receber | `Notas_Fiscais_Rec`, `Notas_Fiscais_Parcelas`, `Rec_Baixas` | `Data_Hora`/`Vencimento` — Estudo 30 |
| Fiscal/CFOP (devoluções/estornos) | `Liv_Saidas`, `Liv_SaiProd`, `Liv_Entradas`, `Liv_EntProd` (mapa de CFOP de devolução) | `Data_Hora` por documento — Estudo 35 |
| Estoque de peças (dados + sugestão de rolos) | `Cte_Peca`, `CTE_Baixa`, `Vw_Car_Itens_Pedido` (pedido), `Car_Pedido`, `Car_Itens_Pedido` | `Alt_Data`/`Data_Hora`; peça em aberto = antijoin — Estudo 34 |

> Antes de implementar, **conferir a coluna watermark exata** de cada tabela nova (Fat_*, Pag_*,
> Rec_*, Liv_* já mapeados no Estudo 22; confirmar `Fat_*` no Estudo 29) — mesmo método dos estudos.

### 4.2 Ordem de carga (dependências)

1. Cadastros (`Clientes_Principal`, `Produtos`/`Produtos_Tecidos`, vendedores, cond. pagto, bancos).
2. Cabeçalhos (`Car_Pedido`, `Fat_Pedido`, `NF_Entradas`, `Notas_Fiscais_Rec`, `Liv_Saidas`/`Liv_Entradas`).
3. Itens/parcelas (`Fat_Itens_Pedido`, `NFE_Parcelas`, `Notas_Fiscais_Parcelas`, `Liv_SaiProd`/`Liv_EntProd`).
4. Baixas/logs (`Pag_Baixas`, `Rec_Baixas`, rateios, `CTE_Baixa`).
5. Estoque de peças (`Cte_Peca` — a maior, ~317k; full fora do expediente).

### 4.3 Regras de carga

- **Upsert** pela chave natural do ERP (após `trim` de `char`).
- **Incremental**: `WHERE watermark > etl.watermark.ultimo_valor`; **filhos sem data**: recarga por
  documento-pai (delete+insert do documento).
- **Idempotente/reprocessável**; registra em `etl.execucoes` (status, linhas, duração, erro).
- **Reconciliação** periódica (full leve) para baixas sem flag (`CTE_Baixa`, `Pag_Baixas`, `Rec_Baixas`).
- Timezone **`America/Sao_Paulo`** na gravação; datas `date`/`timestamp`.

Critério de aceite C: cada tabela do `raw` com contagem batendo com a do ERP (amostras) e
`etl.watermark` avançando nas execuções posteriores.

---

## 5. Fase D — `core`/`marts` (regras portadas)

Objetivo: reproduzir no Neon o que o `DBProDash` faz hoje, validado número a número.

Portar as regras (da Doc 44 §2.2 e Estudos 12/29/30/31):

| Mart/core | Regra a portar (fonte atual) |
|-----------|------------------------------|
| `core.estoque_pecas_em_aberto` | `Cte_Peca` antijoin `CTE_Baixa` + `Nro_Rolo_Origem IS NULL` (= `VW_CTE_PECA_EM_ABERTO`) |
| `core.sugestao_rolos` | janela `SUM(Metros) OVER (gaveta, tear DESC, rolo DESC)` até `Qtde_Saldo` (Vw_Car_Itens_Pedido) — reimplementar em Python |
| `marts.faturamento_diario` | `vwFaturamento` → `SUM(Vr_Total)+SUM(Acres_Desc)` por `Data_Nota` (QMP `Base_Calc` P/M) |
| `marts.contas_pagas_diario` | `vwContasPagas` → baixas por `Data_Baixa`, Empresa `'13'`, Tipo_Entidade A/F |
| `marts.custos_por_departamento_mensal` | relatório de centro de custo/departamento (hoje `Rel_CCusto_Niveis` + `vwContasPagasCentroCusto*`) |
| `marts.devolucoes_diario` | `vwListagemDeEntradasSaidasPorCFOP` com CFOP de devolução (1.201/1.156/1.202/2.202) |
| `marts.estornos_diario` | `vwListagemDeEstornos` → `SUM(Vr_Nota)` por `Data_Emissao` |
| `core.financeiro_receber/pagar_programado` | `vwFinanceiroContasReceber/Pagar` → vencimento > fim do mês anterior |
| `marts` KPI-final | Faturamento, Desconto, Devolução, Estorno, Receber/Pagar programado, Custos admin + razão |

Validação D: para amostras (mês corrente + 12 meses), KPIs do Neon **iguais** aos do `DBProDash`
(divergência < 0.01); para estoque, 10 pedidos reais com mesma sugestão de rolos. Só então os
endpoints voltam a ser confiáveis.

---

## 6. Fase E — Endpoints da API (substitui o `oraculum`)

Objetivo: os 14 contratos de negócio + health, lendo **apenas do Neon**, com auth.

| Grupo | Rotas |
|-------|-------|
| Estoques | `GET /dados` (paginação por cursor), `GET /sugestao-rolos/{pedido}`, `GET /pdf/sugestao-rolos/{pedido}` |
| KPI | `GET /faturamento/{data}`, `/faturamento-dia/{data}`, `/contas-pagas/{data}`, `/custos-administrativos-anual|mensal`, `/descontos/{data}`, `/devolucoes/{data}`, `/estornos/{data}`, `/contas-receber|pagar-programado` |
| Agregado | `GET /dashboard-completo/{data}` (alias que lê os marts) |
| Infra | `GET /health` (sonda Neon + status `etl.watermark`) |

Entregáveis da fase:
1. **Auth** (D5/D6): login, JWT curto, `bcrypt`; escopos por rota derivados dos tópicos.
2. **Schemas Pydantic** idênticos em forma ao legado, porém tipados, `trim`, datas ISO.
3. **Data de entrada**: aceita ISO; legacy `DDMMYYYY` em modo deprecado (log de aviso).
4. **Erros padronizados**; CORS restrito às origens do `dgbcomex`.
5. **PDF** (reportlab) servido do mart (404 quando não há material).
6. **Teste de contrato**: script que bate KPI ONDE/legado × Neon e compara JSON (mesmo p/ `/dados`).

Critério de aceite E: contrato automático passando; latência de `/dashboard-completo` muito menor
que a do legado (unica leitura, não 10 procs); auth bloqueando rota sem escopo.

---

## 7. Fase F — Cutover e descomissionamento

1. Apontar o `dgbcomex` (repo separado, Next.js/Vercel) para o **Neon** via `DATABASE_URL` (pooled);
   congelar leitura do legado.
2. Período de sombra: manter o legado no ar (read-only) 1–2 semanas comparando os mesmos KPIs.
3. Desligar o `oraculum`; remover proc escreve/DBProDash do uso; **não** excluir `DBProDash`
   (pode haver consulta ocasional) — apenas deixar de ser fonte.
4. Documentar contrato final + runbook de ETL (cron, reconciliação, monitor).

Critério de aceite F: `dgbcomex` operando só no Neon; legado desligado sem perda de tela.

---

## 8. Próximas ações imediatas (ordem)

- [x] Neon `dgbcomex` criado e **`public` migrado** (118 tabelas) via `npm run db:migrate:all` no repo dgbcomex.
- [x] Seed do dgbcomex executado no Neon (4 usuários demo + menus).
- [ ] Confirmar **decisões D3–D4** (runner do ETL, frequência) — necessárias p/ começar a carga.
- [ ] Criar `app/` com pyproject + venv + deps; `.env` com `DATABASE_URL`.
- [ ] Alembic: migrations 0001–0004 (schemas vazios) e subir no Neon de dev.
- [ ] Módulo `db/erp.py` (conexão read-only) + prova de conceito de extract de 1 domínio (ex. `Fat_Pedido`).
- [ ] Implementar ETL incremental + `etl.watermark`; bootstrap dos cadastros → faturamento → financeiro → estoque.
- [ ] PORTAR regras `core`/`marts` e validar KPIs (Fase D).
- [ ] Endpoints + auth + PDF (Fase E); testar contrato contra legado.
- [ ] Cutover (Fase F) e documentação final.

---

## 9. Riscos que vão ditar o ritmo

- **Volume**: `Cte_Peca` (~317k) e itens de romaneio dominam a carga — agendar fora do expediente.
- **Watermarks ausentes**: tabelas sem coluna de data exigem recarga por pai (já previsto).
- **Dependência de rede**: runner do ETL precisa alcançar `10.156.0.124` (ERP on-prem).
- **Auth nova**: migrar usuários/escopos (do `Usuario_Acessos`) é trabalho próprio — iniciar cedo.
- **Contrato do front**: mudanças em `core`/`marts` do Neon quebram o `dgbcomex` — aditivo e versionado.
- **`public` compartilhado**: o Neon já tem dados do produto (118 tabelas em `public`); o
  api-microdata só tem esquemas próprios e **nunca** altera `public` — integrações ficam em `marts`.
- **Bootstrap do Neon já feito** (setup): estrutura do `public` criada por `scripts/migrate.js`
  + `apply-drizzle-migrations.js` + seed (4 usuários demo) — nada disso é responsabilidade do
  api-microdata.

---

_Estado: Fase A concluída. Próximo checkpoint: decisões D1–D8 → Fase B (scaffold `app/`)._