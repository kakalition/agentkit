# Deployment

## Introduction

An agentkit service is one process by default. This page covers running it in
production: serving channels, containers, and hardening.

## The single-process model

`run_all(...)` supervises the worker (scheduler), the web UI, and every registered
channel on daemon threads, installs signal handlers, and shuts down gracefully.
There is no separate server to run for the common case.

```python
from agentkit import App

app = App(name="nudge", settings=Settings)
app.providers([NudgeProvider, TelegramProvider])
app.serve()                 # blocks; Ctrl-C to stop
```

```bash
agentkit serve              # boots bootstrap:app
agentkit serve --no-webui   # headless
```

## Channels

Register long-running services (Telegram, Slack, a queue consumer) as channels.
They run alongside the web UI and the scheduler:

```python
app.channel("telegram", telegram_channel)   # factory(app) -> Service
```

Channels auto-disable when unconfigured (e.g. no `TELEGRAM_BOT_TOKEN`), so the
same binary runs everywhere.

## Docker

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

ENV AGENTKIT_HOME=/data
VOLUME ["/data"]

EXPOSE 8765
CMD ["uv", "run", "agentkit", "serve"]
```

The database, artifacts, and logs all live under `AGENTKIT_HOME`, so one volume
persists everything.

## Behind a reverse proxy

Terminate TLS at a proxy and keep agentkit on loopback. If you must bind a public
interface, agentkit warns and you should add authentication:

```bash
WEBUI_HOST=127.0.0.1
A2A_HOST=127.0.0.1
```

## Configuration and secrets

Inject configuration through the environment (agentkit reads plain env vars). In
Kubernetes, mount secrets; on a PaaS, use its secret store. Never commit `.env`.

## Health checks

Probe liveness with the health helper (or the web UI's health route) so the
platform can restart a wedged process:

```yaml
livenessProbe:
  httpGet: { path: /healthz, port: 8765 }
```

## Scaling notes

- **State is local.** The database is SQLite/libSQL for a single host. For
  horizontal scale, point the runtime at a shared database and run one writer.
- **Long turns.** Enable [streaming](/guide/streaming) so proxies do not time out.
- **Durable jobs** survive restarts; make tasks [idempotent](/guide/scheduling).

## Graceful shutdown

`run_all` traps `SIGINT`/`SIGTERM`, stops services, and joins threads. In-flight
workflows are checkpointed by DBOS, so nothing is lost on restart.

::: tip Production checklist
- Secrets from a secret store, not `.env`
- `WEBUI_HOST`/`A2A_HOST` on loopback behind a proxy
- `OBSERVABILITY` enabled and pointed at a collector
- A [budget](/guide/budgets) on spend
- Health probe wired to the orchestrator
:::

## Containers

A single-node `Dockerfile` and `docker-compose.yml` ship at the repo root. The
compose file runs one `agent` process (with the scheduler) and one `queue:work`
worker sharing a volume; set `AGENTKIT_BOOTSTRAP` (e.g. `app:app`) and secrets in
a `.env`:

```bash
docker compose up -d
```

Keep exactly **one scheduler leader** (the `agent` service); workers can be
scaled with `--scale worker=N` because the queue is DB-backed.

## Metrics

Set `METRICS_ENABLED=true` to expose Prometheus metrics at `METRICS_PATH`
(default `/metrics`): turns (by outcome) and their latency, tool errors, queue
depth, scheduler runs, and estimated cost. Point Prometheus at `:8787/metrics`.

## Migrations & backups

```bash
agentkit migrate                 # create missing tables + reconcile drift
agentkit db:backup --out agent.db.bak   # WAL-safe (VACUUM INTO)
agentkit db:restore agent.db.bak --yes  # overwrite the current DB
agentkit health                  # per-dependency readiness
```

`GET /api/health` returns the same readiness checks (`db`, and `queue`/`vault`
when those layers are enabled). `/healthz` (liveness) and `/readyz` (readiness)
are also served on the A2A/standalone Starlette app.

## Postgres

SQLite/libSQL is the default and only required backend. Set
`DATABASE_URL=postgresql://…` (driver `asyncpg`, installed) for Postgres. Schema
creation and drift reconciliation work through the same `init_db` path. Keep the
single-writer assumption: run one scheduler/worker leader, not many.

## Ops runbook

1. **Degraded health** — `/api/health` lists the failing dependency; `agentkit
   health` shows the same locally. A failing `vault` check means
   `AGENTKIT_CREDENTIALS_KEY` is unset (the vault refuses to run without it).
2. **Stuck queue** — check depth via metrics (`agentkit_queue_depth`) or
   `agentkit queue:work --once`; requeue failed jobs from the web UI.
3. **Before an upgrade** — `agentkit db:backup`, then deploy; `agentkit migrate`
   runs non-destructively.
4. **Cost spike** — `agentkit_cost_usd_total` and the usage page; set a
   [budget](/guide/budgets).

Continue to [Artisan-style CLI →](/guide/cli)
