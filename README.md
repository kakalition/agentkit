# agentkit

**Composable building blocks for production PydanticAI assistant agents** —
CLI + Telegram, MCP + A2A, durable execution, and a durable cron/one-off
scheduler, on a single local process.

`agentkit` packages the plumbing every single-user assistant agent needs, so you
write the domain (your tools, prompts, data) and not the scaffolding: model
config with retries, an orchestrator that delegates to specialists,
human-in-the-loop approvals, durable conversation history, durable background
work, MCP/A2A interop, safe defaults, and channel gateways.

[![CI](https://github.com/kakalition/agentkit/actions/workflows/ci.yml/badge.svg)](https://github.com/kakalition/agentkit/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Coverage](https://img.shields.io/badge/coverage-76%25-brightgreen)

---

## Table of contents

- [Install](#install)
- [60-second agent](#60-second-agent)
- [Orchestrator + specialists](#orchestrator--specialists)
- [Durable scheduling](#durable-scheduling-cron--one-off)
- [Durability](#durability)
- [MCP](#mcp)
- [A2A](#a2a)
- [Persona (`SOUL.md`)](#persona-soulmd)
- [Run everything in one process](#run-everything-in-one-process)
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

Python 3.11–3.12. No external services: state lives in local SQLite/libSQL.

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

run_all([
    Service("a2a", lambda: serve_a2a(settings)),
    Service("mcp", lambda: serve_mcp(settings)),
    Service("bot", lambda: run_bot(settings)),
])
```

Daemon threads; blocks until SIGINT/SIGTERM; a crashing service doesn't take
down the others.

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
| `AGENT_HOME` | `~/.local/share/agentkit` | DB + artifacts |
| `DATABASE_URL` | local libSQL file | `sqlite+libsql://…` or other |
| `SOUL_FILE` | `<AGENT_HOME>/SOUL.md` | Persona |
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
uv run pytest --cov=agentkit        # 49 tests, ≥70% gate
uv run ruff check src tests
uv run mypy src/agentkit
uv build
```

Layout: `config`, `app`, `orchestrator`, `deps`, `approvals`, `session`, `soul`,
`runtime`, `durability`, `scheduler`, `supervise`, `observability`, `logging`,
`guardrails`, `policy`, `errors`, `health`, `db/`, `mcp/`, `a2a/`, `gateways/`.

## License

MIT.
