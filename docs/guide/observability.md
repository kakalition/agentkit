# Observability

You cannot operate what you cannot see. agentkit emits structured logs, traces
every model and tool call, and ships an operator web UI for inspecting live state.

## Structured logging

```python
from agentkit import get_logger, setup_logging

setup_logging(settings)                 # called for you by the CLI
log = get_logger("notes")
log.info("exported %s notes", count)
```

Logs carry correlation ids and redact secrets and monetary amounts automatically.

```bash
LOG_LEVEL=INFO
LOG_JSON=false        # set true for machine-readable logs
```

## Traces: Phoenix / OpenTelemetry

Enable self-hosted span export with a single variable:

```bash
OBSERVABILITY=phoenix        # phoenix | otlp | console | off
OTLP_ENDPOINT=               # for a custom OTLP collector
```

Phoenix runs locally — no hosted account. `setup_observability(settings)` is
called for you by `agentkit serve`; call it yourself in custom entry points:

```python
from agentkit.observability import setup_observability

setup_observability(settings)   # → True if enabled
```

## The operator web UI

Every agent gets an in-core web console (`agentkit serve` serves it, and
`run_all` auto-appends it). It is scoped to the hosting agent and covers:

- **Overview** — recent activity and health;
- **Chat** — talk to the agent directly;
- **Conversations** — browse and search history;
- **Scheduler** — manage durable jobs;
- **Workflows** — inspect DBOS runs;
- **Usage** — tokens and cost over time;
- **Audit** — the hash-chained log;
- **A2A** — task history;
- **Persona** — edit `SOUL.md`;
- **Config** — view resolved settings;
- **Artifacts** — generated files.

```python
app.serve()                    # web UI on by default
app.serve(webui=False)         # or not
```

```bash
WEBUI_ENABLED=true
WEBUI_HOST=127.0.0.1
WEBUI_PORT=8787
```

## Health and readiness

`agentkit.health` exposes liveness/readiness helpers used by the web UI and A2A
surfaces, so a supervisor can probe the process.

## The instrumentation capability

For finer-grained control, attach PydanticAI's instrumentation capability:

```python
agent = Agent.make("notes").instructions("…").instrumentation().build()
```

## What to watch

| Signal | Where |
| --- | --- |
| Turn latency | spans (`turn` / model request) |
| Tool usage | `tool.start` / `tool.end` events |
| Cost & tokens | `UsageRepo.totals()`, the Usage tab |
| Failures | workflow dead-letter, `errors` taxonomy codes |
| Safety | audit log, `guardrails.injection` events |

::: tip Correlate everything
Every conversation id flows through logs, events, spans, and the audit log, so a
single id lets you reconstruct a whole turn across surfaces.
:::

Continue to [Scheduling & Durability →](/guide/scheduling)
