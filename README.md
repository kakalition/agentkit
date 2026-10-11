# agentkit

**The batteries-included framework for production PydanticAI assistant agents.**
Write your domain; agentkit ships the rest — durable conversation history, an
orchestrator with specialists, human-in-the-loop approvals, durable execution
and scheduling, MCP + A2A interop, safe defaults, gateway channels, and a
built-in **operator web UI** that every agent gets for free.

`agentkit` packages the plumbing every single-user (self-hosted) assistant needs,
so you ship the product and not the scaffolding: model config with timeouts and
retries, durable history, background work, token accounting, a hash-chained
audit log, structured redacted logs, readiness probes, and a loopback web
console for exploring and operating the running agent.

[![CI](https://github.com/kakalition/agentkit/actions/workflows/ci.yml/badge.svg)](https://github.com/kakalition/agentkit/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Coverage](https://img.shields.io/badge/coverage-76%25-brightgreen)

---

## Highlights

- **One process, one command.** `run_all(...)` supervises the worker, A2A, MCP,
  bot, and web UI in a single local process — no server to run.
- **Durable by default.** Conversation history and background work run on DBOS
  over local SQLite: turns, jobs, cron and one-off schedules survive restarts.
- **An operator console in the box.** Every agent serves a Vite + React +
  shadcn/ui web UI at `http://127.0.0.1:8787`: chat, conversations, usage, audit,
  A2A tasks, durable workflows, schedules, persona, config, and artifacts.
- **Agents that delegate.** `Orchestrator` gives you an agent that routes to
  specialist sub-agents as tools.
- **Safe by construction.** Approvals default-deny; loopback binds; secrets and
  amounts are redacted from logs; every material action is audited.
- **Interop, both ways.** Consume and serve MCP servers and A2A agents.
- **Local-first.** No hosted account, no external services; state is files.

## Table of contents

- [Highlights](#highlights)
- [Install](#install)
- [60-second agent](#60-second-agent)
- [Orchestrator + specialists](#orchestrator--specialists)
- [Durable scheduling](#durable-scheduling-cron--one-off)
- [Durability](#durability)
- [MCP](#mcp)
- [A2A](#a2a)
- [Persona (`SOUL.md`)](#persona-soulmd)
- [Run everything in one process](#run-everything-in-one-process)
- [Operator web UI](#operator-web-ui)
- [Observability](#observability-self-hosted-no-account)
- [Production features](#production-features)
- [Configuration](#configuration-agentsettings)
- [Design notes](#design-notes)
- [Development](#development)
- [License](#license)

## Install

```bash
uv add agentkit
# optional extras
uv add "agentkit[observability-phoenix]"   # local trace UI (default observability)
uv add "agentkit[prices]"                  # yfinance
```

Python 3.11–3.12. No external services: state lives in local SQLite/libSQL, one
dir per agent under `~/.agentkit/<agent_name>`.

### Quickstart

```bash
agentkit workspace list                      # where agents live
agentkit webui                               # operator console for the current agent
```

Every agent that calls `run_all(..., settings=settings)` serves the web UI
automatically on `http://127.0.0.1:8787`.

## 60-second agent

```python
import asyncio
from pydantic_ai import Agent
from agentkit import AgentApp, AgentSettings, Deps

notes = Agent(name="notes", deps_type=Deps, output_type=str,
              instructions="Manage the owner's notes.")

@notes.tool
async def add_note(ctx, text: str) -> str:
    """Save a note."""
    ctx.deps.extras.setdefault("notes", []).append(text)
    return f"saved: {text}"

app = AgentApp.build(agent=notes, settings=AgentSettings(owner_id="owner"))
print(asyncio.run(app.run("add a note: buy milk")).output)
```

## Orchestrator + specialists

PydanticAI v2 removed `Agent.as_tool`; `Orchestrator` generates one delegation
tool per specialist.

```python
from agentkit import Orchestrator

orchestrator = (
    Orchestrator(name="assistant", instructions="Route to the right specialist.")
    .add_specialist(notes, tool_name="handle_notes", description="Add/list notes.")
    .add_specialist(calendar, tool_name="handle_calendar", description="Manage events.")
)
agent = orchestrator.agent
```

## Durable scheduling (cron *and* one-off)

Jobs live in the database and are fired by a DBOS cron tick with a deterministic
workflow id, so each run happens **exactly once** across restarts.

```python
from agentkit import scheduler

@scheduler.task("digest")
def send_digest(*, period: str = "last-month") -> None: ...

scheduler.init_scheduler()                                   # once at startup
scheduler.schedule_cron("weekly", "0 8 * * 1", "digest", args={"period": "last-month"})
scheduler.schedule_once("reminder", "2026-11-01T09:00", "digest")
scheduler.list_jobs(); scheduler.remove_job("reminder")
```

## Durability

Long/background work runs on **DBOS Transact** on a local SQLite *system
database* (`$AGENT_HOME/dbos.sqlite`) — no server, unlike Temporal.

```python
from agentkit import durability
from dbos import DBOS

@DBOS.step(retries_allowed=True, max_attempts=3)
def fetch(...): ...

@DBOS.workflow()
def nightly(...): ...

durability.init(queues=["agentkit"])
durability.enqueue("agentkit", nightly, ...)
```

`agentkit.durability` exposes the pieces a lightweight app needs:
`workflow`/`step`, `sleep` (durable timers), queues, schedules, and workflow
management (`list_workflows`, `get_workflow`, `cancel_workflow`,
`resume_workflow`, `failed_workflows`) plus `client()` (a standalone
`DBOSClient`). Workflow-context-only primitives (`send`/`recv`,
`set_event`/`get_event`, `fork_workflow`) are intentionally not wrapped.

## MCP

```python
from agentkit.mcp import MCPRegistry, MCPServerSpec

registry = MCPRegistry([
    MCPServerSpec(name="chart", command="uv", args=["run", "--directory", CHART_DIR, "apollo-charting"]),
    MCPServerSpec(name="pdf",   url="http://127.0.0.1:8000/mcp"),
], log_dir=home / "logs")

async with registry:                       # entered once, closed on shutdown
    result = await registry.call_tool("chart", "render_chart", {"spec": spec, "force": True})
    await agent.run("...", toolsets=registry.toolsets())
```

Serve an MCP server with `agentkit.mcp.serve_mcp(app, transport="streamable-http")`.

## A2A

```python
from agentkit.a2a import build_a2a_app, build_card, TaskAgentExecutor, SQLAlchemyTaskStore, A2AClient

card = build_card(name="MyAgent", description="…", url="http://127.0.0.1:9000",
                  skills=[{"id": "notes", "name": "Notes", "tags": ["notes"]}])
app = build_a2a_app(
    card=card,
    executor=TaskAgentExecutor(answer=my_answer_fn),   # async (text) -> str
    task_store=SQLAlchemyTaskStore(runtime),
    healthz=lambda: True,
)
text = await A2AClient().call_agent("http://127.0.0.1:9000", "how much did I spend?")
```

## Persona (`SOUL.md`)

The agent's identity/behaviour is a Markdown file, not code:

```python
from agentkit import load_soul, ensure_soul, compose_instructions

ensure_soul()                                     # <AGENT_HOME>/SOUL.md if missing
instructions = compose_instructions(load_soul(), "Route requests to specialists.")
```

## Run everything in one process

```python
from agentkit import Service, run_all

run_all(
    [
        Service("a2a", lambda: serve_a2a(settings)),
        Service("mcp", lambda: serve_mcp(settings)),
        Service("bot", lambda: run_bot(settings)),
    ],
    settings=settings,          # enables the auto-appended web UI
    runtime=runtime,
    webui_answer=my_answer,      # optional: (conversation_id, text) -> ChatResult
)
```

Daemon threads; blocks until SIGINT/SIGTERM; a crashing service doesn't take
down the others. When `settings.webui_enabled` is set, the web UI is appended
automatically (use `webui=False` to opt out).

## Operator web UI

Every agent normally gets an operator UI at `http://127.0.0.1:8787` (loopback,
no auth, single operator) showing **only the hosting agent**:

- **Inspect**: conversations + chat, usage, audit (hash-chain verify), A2A tasks,
  durable workflows.
- **Manage**: schedules (cron/once CRUD), workflow cancel/resume, SOUL persona,
  config (secrets masked), artifacts.

Storage runs under `workspace_root` (default `~/.agentkit`), one dir per agent:

```
~/.agentkit/<agent_name>/
  agent.db      conversations, messages, jobs, usage, audit, a2a
  dbos.sqlite   durable workflows
  SOUL.md, artifacts/, logs/
```

Manage it from the CLI:

```bash
agentkit workspace list
agentkit workspace migrate calliope     # move legacy ~/.local/share data
agentkit webui                          # standalone UI for the current env
```

The SPA source lives in `web/` (Vite + React + shadcn/ui). Build it with
`cd web && bun install && bun run build`; until then a fallback page is served
and the JSON API under `/api` stays fully usable.

## Observability (self-hosted, no account)

**On by default** with a local **Arize Phoenix** UI (`OBSERVABILITY=phoenix`).
Spans go to a backend you run via OpenTelemetry; nothing is sent to any hosted
service (PydanticAI is instrumented through `logfire` in local mode only).

```bash
OBSERVABILITY=phoenix uv run myapp         # default: Phoenix on localhost:6006
OBSERVABILITY=console uv run myapp         # terminal spans
OBSERVABILITY=otlp OTLP_ENDPOINT=http://127.0.0.1:4318/v1/traces uv run myapp
```

Falls back to console if Phoenix isn't installed. `otlp` works with Jaeger,
Grafana Tempo, Langfuse, or a collector.

### Structured logging

```python
from agentkit import setup_logging, request_context, get_logger

setup_logging(settings)                     # JSON when settings.log_json
with request_context() as rid:              # correlation id for the turn
    get_logger("turn").info("handling %s", text)
```

Secrets and monetary amounts are redacted from all log output.

## Production features

| Area | API |
| --- | --- |
| **Logging** | `setup_logging`, `request_context`, `get_logger` (redaction built in) |
| **Token accounting** | automatic per-turn recording → `repos.usage.totals()` |
| **Audit log** | `repos.audit.append(action, …)` + `verify()` (hash chain) |
| **Tool RBAC / approval policy** | `ToolPolicy(allow=…, deny=…, require_approval=…)` |
| **Guardrails** | `scan_injection`, `wrap_untrusted`, `redact`, `check_egress` |
| **Error taxonomy** | `InvalidInput`, `NotFound`, `Conflict`, `PermissionDenied`, `DependencyMissing`, `RateLimited`, `UpstreamError` |
| **Health** | `health_routes([db_check(runtime)])` → `/healthz` + `/readyz`; `install_signal_handlers` |
| **Dead letters** | `durability.failed_workflows(queue=…)` |
| **Queues** | `durability.init(queues={"work": {"worker_concurrency": 4}})` |

## Configuration (`AgentSettings`)

| Var | Default | Purpose |
| --- | --- | --- |
| `AGENT_NAME` / `OWNER_ID` / `OWNER_NAME` | `assistant` / `owner` / `Owner` | Identity |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | – | Any OpenAI-compatible endpoint |
| `MODEL_NAME` | `openai:gpt-4o-mini` | Model id |
| `MODEL_TIMEOUT` / `MODEL_RETRIES` | `60` / `2` | Transport resilience |
| `USAGE_REQUEST_LIMIT` / `USAGE_TOTAL_TOKENS_LIMIT` | (unlimited) | Per-run caps |
| `AGENTKIT_HOME` | `~/.agentkit` | Workspace root (`<root>/<AGENT_NAME>`) |
| `AGENT_HOME` | `<AGENTKIT_HOME>/<AGENT_NAME>` | Explicit home override |
| `DATABASE_URL` | local libSQL file | `sqlite+libsql://…` or other |
| `SOUL_FILE` | `<AGENT_HOME>/SOUL.md` | Persona |
| `WEBUI_ENABLED` / `WEBUI_HOST` / `WEBUI_PORT` | `true` / `127.0.0.1` / `8787` | Operator UI |
| `OBSERVABILITY` | `phoenix` | `phoenix` \| `console` \| `otlp` \| `off` |
| `LOG_LEVEL` / `LOG_JSON` | `INFO` / `false` | Logging |
| `A2A_HOST` / `A2A_PORT` / `A2A_PUBLIC_URL` | `127.0.0.1` / `9000` | A2A |
| `MCP_HOST` / `MCP_PORT` | `127.0.0.1` / `8765` | MCP HTTP |

Subclass `AgentSettings` to add app fields.

## Design notes

- **Delegation, not `as_tool`.** `Orchestrator` writes the delegation tool.
- **One writer.** `repositories()` serializes DB access with a process lock;
  schema bootstrap uses the same lock. WAL + busy-timeout are set.
- **Infra vs domain.** agentkit owns only `conversations`, `messages`,
  `a2a_tasks`, `scheduled_jobs`, `usage_records`, `audit_log`. Domain tables
  belong to your app; subclass `Repositories` and pass `repos_factory`.
- **DBOS workflows must be module-level** — agentkit provides infra + decorators.
- **Approvals default-deny** without an approver.
- **Loopback by default**; servers warn when bound elsewhere.

## Development

```bash
uv sync --extra dev --extra observability
uv run pytest --cov=agentkit        # 84 tests, ≥70% gate
uv run ruff check src tests
uv run mypy src/agentkit
uv build
```

Layout: `config`, `app`, `orchestrator`, `deps`, `approvals`, `session`, `soul`,
`runtime`, `durability`, `scheduler`, `supervise`, `workspace`, `cli`,
`observability`, `logging`, `guardrails`, `policy`, `errors`, `health`,
`db/`, `mcp/`, `a2a/`, `gateways/`, `webui/` (backend) + `web/` (SPA).

## License

MIT.
