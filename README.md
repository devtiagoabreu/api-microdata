# api-microdata

API + ETL que substituem a API legada `oraculum`: extraem do ERP **Microdata** (`DBMicrodata_DGB`,
SQL Server on-prem, **somente leitura**), montam um warehouse no **Postgres local** e publicam os
agregados pequenos de dashboard no **Neon**, onde o `dgbcomex` (Next.js) lê.

```
ERP DBMicrodata_DGB ──ETL──▶ Postgres local (raw/core/marts/etl) ──publicar-neon──▶ Neon (marts.*)
                                    ▲                                                    ▲
                                    └──────────── API FastAPI (17 rotas) ─────────────────┘
```

## Onde começar

| Se você quer… | Leia |
|---------------|------|
| Rodar a API | [Runbook §2–3](docs/arquitetura/46-runbook-operacao-e-cutover.md) |
| Saber o que cada rota devolve | [Contratos da API](docs/arquitetura/44-contratos-api-oraculum.md) |
| Entender a arquitetura | [Arquitetura alvo](docs/arquitetura/43-arquitetura-alvo-api.md) |
| Ver o plano e o que falta | [Plano de implementação](docs/arquitetura/45-plano-de-implementacao.md) |
| Operar de verdade (agendamento, backup, incidente) | [Runbook](docs/arquitetura/46-runbook-operacao-e-cutover.md) |

## Rodando

Dá dois cliques (ou `cmd /c`):

```
rodar-api.bat      sobe a API — ou avisa que já está no ar
parar-api.bat      derruba
```

Os dois scripts olham a porta **58245** antes de agir:

| Situação | O que acontece |
|----------|----------------|
| Porta livre | Sobe o uvicorn em segundo plano, espera `/health` responder (até 40s) e mostra warehouse + Neon |
| Já tem instância **da api-microdata** | Mostra o PID e sai — não sobe duas |
| Porta com **outro programa** | Avisa e **não encosta**; mostra o comando para liberar a porta |

O `HOST` no `rodar-api.bat` é `0.0.0.0` para outra máquina alcançar a API. Se o `dgbcomex` roda
na mesma máquina e você quiser restringir, troque para `127.0.0.1`. O log fica em
`app/logs/api.log`.

> A porta **58244** é do `oraculum` legado e **não deve ser tocada** — por isso os scripts são
> fixos na 58245. Firewall: regra `API-MICRODATA` liberando TCP 58245 em todos os perfis.

Manual, se preferir:

```powershell
cd app
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 58245
```

17 rotas: `/health`, 2 de auth (`/auth/login`, `/auth/eu`) e 14 de negócio. A auth é **falha fechada**
por padrão — sem usuário no Neon, tudo responde `401`. Antes de chamar rota de negócio:

```powershell
.\.venv\Scripts\python.exe -m src.cli usuario --email fulano@dgb.com.br --empresa 13 `
  --escopos faturamento:leitura,financeiro:leitura
```

Carga do ERP e publicação no Neon:

```powershell
.\.venv\Scripts\python.exe -m src.cli check                    # valida as watermarks
.\.venv\Scripts\python.exe -m src.cli bootstrap --tudo --incremental
.\.venv\Scripts\python.exe -m src.cli publicar-neon
```

## Desenvolvimento

```powershell
.\.venv\Scripts\python.exe -m pytest        # 192 testes
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m alembic current
```

Validação contra o ERP (`DBProDash` e as procedures do legado):

```powershell
.\.venv\Scripts\python.exe -m scripts.validar_api      # rotas x procedures
.\.venv\Scripts\python.exe -m scripts.validar_fase_d   # marts x DBProDash
```

O ERP é vivo: as duas rodadas aceitam pequenas divergências de churn. O critério de suspeita real é
a divergência **persistir depois** de `bootstrap --dominio <dominio>` — ver [runbook §9](docs/arquitetura/46-runbook-operacao-e-cutover.md).

## Regras que não se quebram

1. **O ERP é somente leitura.** Toda leitura passa por `src/db/erp.py`, que rejeita qualquer coisa
   fora de `SELECT`/`WITH`/`EXEC` de procedure na whitelist.
2. **O `public` do Neon é do `dgbcomex`.** A API só escreve em `marts`, `etl` e `auth`.
3. **Falha fechada na auth.** `API_AUTENTICACAO_EXIGIDA=true` é o padrão; desligar é só para o
   validador e a suíte de testes.
4. **Os dois marts pesados não sobem para o Neon.** `core.estoque_pecas_em_aberto` e
   `core.pedido_sugestao_rolos` são grão de peça/linha e ficam no warehouse local.

## Estado

Fases B–E concluídas (05/out/2026); D1–D6 decididos e entregues. Falta a Fase F — a parte que depende
de decisão de produto: apontar o `dgbcomex` para `marts.*`, período de sombra de 1–2 semanas e
desligar o `oraculum`. Ver [runbook §8](docs/arquitetura/46-runbook-operacao-e-cutover.md).