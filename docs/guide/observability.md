# Observability

## Introduction

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

For finer-grained control, attach PydanticAI's instrumentation capability.
Instrumentation has no `AgentDefinition` field, so attach it in `configure`:

```python
from agentkit import AgentDefinition

class Notes(AgentDefinition):
    name = "notes"
    instructions = "…"

    def configure(self, agent):
        return agent.instrumentation()
```

Fluent equivalent: `Agent.make("notes").instructions("…").instrumentation().build()`.

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

## Drivers

### What a tracing driver is, in plain English

**Tracing** is keeping a **diary of what the agent did**. Each time the agent
starts a piece of work — handling a message, calling the model, running a tool —
it writes down an entry: when it started, when it finished, and what happened in
between. A single entry like that is called a **span**; the whole story of one
request, from first entry to last, is called a **trace**. You read the diary to
answer questions a plain log cannot: *which step was slow? which tool failed?
where did this turn's time and tokens go?*

The **tracing driver** is where those entries are written and shipped: to a
local UI you can browse, to your terminal, to a backend you run, or nowhere.
Because tracing on every step can be noisy, the driver is selected by a single
setting — and, unusually, the setting *is* the driver name (`observability`).
The tracer is reached through `app.tracer`, and `app.tracer.setup(settings)`
turns on the active driver.

### A runnable example

```python
from agentkit import App

app = App()   # reads OBSERVABILITY from the env / .env (default: phoenix)

# Default behavior: OBSERVABILITY=phoenix launches a local Arize Phoenix UI
# (self-hosted, no account) and exports spans to it; if Phoenix is not
# installed, spans fall back to the console.
enabled = app.tracer.setup(app.settings)   # -> True while tracing is on
print(enabled)

# Switch by setting an env var and rebuilding the app:
#   OBSERVABILITY=console  -> print spans to the terminal
#   OBSERVABILITY=otlp     -> export to your own collector (set OTLP_ENDPOINT)
#   OBSERVABILITY=off      -> disable tracing entirely
```

### Built-in drivers

The kind is `observability`, and the `OBSERVABILITY` setting names the driver
directly:

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `phoenix` (default) | Launches a local Arize Phoenix UI and exports spans to it. Falls back to printing spans on the console when the `phoenix` package is not installed. | Local, self-hosted tracing with no hosted account. |
| `console` | Prints spans to the terminal. | A quick look during development, with no backend to run. |
| `otlp` | Exports spans over OTLP to a backend you run — Arize Phoenix, Jaeger, Grafana Tempo, Langfuse, or an OpenTelemetry Collector. Set `OTLP_ENDPOINT` or `OTEL_EXPORTER_OTLP_ENDPOINT`. Needs the `observability` extra. | Sending traces to your existing observability stack. |
| `off` | Disables tracing. | When you want no tracing output or overhead. |

::: warning Local mode, always
agentkit runs the instrumenter in **local mode**: spans are never sent to any
hosted account. Export only ever goes to a backend *you* run.
:::

### How to select a driver

```bash
OBSERVABILITY=phoenix     # phoenix | console | otlp | off
OTLP_ENDPOINT=            # for OBSERVABILITY=otlp (or OTEL_EXPORTER_OTLP_ENDPOINT)
```

Selection follows the standard precedence: an explicit name passed in code
(`app.manager("observability").driver("console")`), then the setting, then the
default (`phoenix`). Because `observability` is typed, an invalid value fails at
settings load with a `ValidationError` rather than silently doing nothing.

### Override it just for your app

`app.extend(...)` registers a tracer scoped to this application only:

```python
from agentkit import DriverKind

app.extend(DriverKind.OBSERVABILITY, "acme", lambda app: AcmeTracer(app.settings))
```

Then select it with `OBSERVABILITY=acme`.

### Ship a reusable driver

Register it globally so any app can use it. A tracer only needs a `setup`
method that returns whether tracing is enabled:

```python
from agentkit import DriverKind, register_driver

@register_driver(DriverKind.OBSERVABILITY, "acme")
def _acme_tracer(app):
    return AcmeTracer(app.settings)
```

See [Contracts & Drivers](/guide/drivers) for the full contract.

### Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| No Phoenix UI after `OBSERVABILITY=phoenix` | The `phoenix` package is not installed; spans fall back to the console. |
| No spans at all | `OBSERVABILITY=off` is set. |
| `otlp` exports nothing | The `observability` extra is missing, or neither `OTLP_ENDPOINT` nor `OTEL_EXPORTER_OTLP_ENDPOINT` is set. |
| `ValidationError` when settings load | The `OBSERVABILITY` value is not one of `phoenix`, `console`, `otlp`, `off`. |
| A changed setting had no effect | The manager caches the driver; call `app.manager("observability").forget()` or restart the process. |
