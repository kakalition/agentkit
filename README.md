# agentkit

**Opinionated building blocks for PydanticAI assistant agents** — CLI + Telegram,
MCP + A2A, durable execution, and a durable cron/one-off scheduler.

`agentkit` packages the non-domain plumbing you keep rewriting for single-user
assistant agents: model config with retries, an orchestrator that delegates to
specialist agents, human-in-the-loop approvals, durable conversation history,
durable background work, MCP/A2A interop, and channel gateways. You bring the
domain (your repos, tools, prompts).

[![CI](https://github.com/kakalition/agentkit/actions/workflows/ci.yml/badge.svg)](https://github.com/kakalition/agentkit/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Install

```bash
uv add agentkit           # or: pip install agentkit
```

Python 3.11–3.12. Optional extras: `agentkit[observability]` (Logfire/OTel),
`agentkit[prices]` (yfinance).

## 30-second agent

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

## Durable scheduling (cron **and** one-off)

Jobs are stored in the database and fired by a DBOS cron tick, with a
deterministic workflow id so each run happens **exactly once** across restarts.

```python
from agentkit import scheduler

@scheduler.task("digest")
def send_digest(*, period: str = "last-month") -> None:
    ...

scheduler.init_scheduler()                                   # once at startup
scheduler.schedule_cron("weekly", "0 8 * * 1", "digest", args={"period": "last-month"})
scheduler.schedule_once("reminder", "2026-11-01T09:00", "digest")

scheduler.list_jobs()      # -> [{name, kind, schedule, task, args, enabled, run_count}, ...]
scheduler.remove_job("reminder")
```

Run a durable worker process (`scheduler.init_scheduler()` then keep the process
alive) to execute the queue and the minute tick.

## Durability

Long/background work runs on **DBOS Transact** on a local SQLite *system
database* (`$AGENT_HOME/dbos.sqlite`) — no server, unlike Temporal. Wrap your own
workflows/steps:

```python
from agentkit import durability
from dbos import DBOS

@DBOS.step(retries_allowed=True, max_attempts=3)
def fetch(...): ...

@DBOS.workflow()
def nightly(...):
    ...

durability.init(queues=["agentkit"])
durability.enqueue("agentkit", nightly, ...)
```

## MCP

**Client** — own N prefixed toolsets for the process lifetime:

```python
from agentkit.mcp import MCPRegistry, MCPServerSpec

registry = MCPRegistry([
    MCPServerSpec(name="chart", command="uv", args=["run", "--directory", CHART_DIR, "apollo-charting"]),
    MCPServerSpec(name="pdf",   url="http://127.0.0.1:8000/mcp"),
], log_dir=home / "logs")

async with registry:
    result = await registry.call_tool("chart", "render_chart", {"spec": spec, "force": True})
    schema = await registry.read_resource("chart", "charting://schema")
    await agent.run("...", toolsets=registry.toolsets())
```

**Server** — `agentkit.mcp.serve_mcp(fastmcp_app, transport="streamable-http", host="127.0.0.1", port=8765)`.

## A2A

Task-based server with a durable store, plus an outbound client:

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

# outbound
text = await A2AClient().call_agent("http://127.0.0.1:9000", "how much did I spend?")
```

## Gateways

```python
from agentkit.gateways import send_markdown, ApprovalBroker, is_allowed, build_cli, entrypoint
```

- `send_markdown` renders Markdown → Telegram entities (telegramify-markdown) and
  falls back to plain text.
- `ApprovalBroker` resolves approvals from inline buttons.
- `build_cli()` + `entrypoint(app)` give you a Typer app with observability wired.

## Approvals (human-in-the-loop)

```python
from agentkit import Deps, ApprovalRequest, approval_capability
from pydantic_ai import Agent

agent = Agent(name="a", deps_type=Deps, output_type=str,
              instructions="…", capabilities=[approval_capability])

@agent.tool(requires_approval=True)
async def delete_everything(ctx) -> str: ...
```

Wire `Deps.approve` (CLI prompt, Telegram buttons). With no approver, gated tools
are **denied by default** — safe for MCP/A2A where there is no interactive user.

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
| `OBSERVABILITY` | `console` | `console` \| `otlp` \| `phoenix` \| `off` |
| `A2A_HOST` / `A2A_PORT` / `A2A_PUBLIC_URL` | `127.0.0.1` / `9000` | A2A |
| `MCP_HOST` / `MCP_PORT` | `127.0.0.1` / `8765` | MCP HTTP |

Subclass `AgentSettings` to add app fields (e.g. Artemis adds `price_source`).

## Observability (self-hosted, no account)

**On by default** (`OBSERVABILITY=console`). Spans are exported through
**OpenTelemetry** to a backend you run; nothing is sent to any hosted service.
PydanticAI's instrumentation is activated via the `logfire` library in local mode
(`send_to_logfire=False`) — no token, no account.

```bash
OBSERVABILITY=console uv run myapp     # spans to the terminal
OBSERVABILITY=phoenix uv run myapp     # launch a local Phoenix UI (zero config)
# or point at any backend you run:
OBSERVABILITY=otlp OTLP_ENDPOINT=http://127.0.0.1:4318/v1/traces uv run myapp
```

`phoenix` launches **Arize Phoenix** locally (`http://localhost:6006`) and sends
spans to it — no account. `otlp` works with Phoenix, **Jaeger**, **Grafana
Tempo**, **Langfuse**, or an OpenTelemetry Collector. Requires
`agentkit[observability]` (and `agentkit[observability-phoenix]` for `phoenix`).

### Structured logging

```python
from agentkit import setup_logging, request_context, get_logger

setup_logging(settings)                     # JSON when settings.log_json
with request_context() as rid:              # correlation id for the turn
    get_logger("turn").info("handling %s", text)
```

Secrets and monetary amounts are redacted from all log output.

## Persona (`SOUL.md`)

The agent's identity/behaviour is a Markdown file, not code:

```python
from agentkit import load_soul, ensure_soul, compose_instructions

ensure_soul()                                     # writes <AGENT_HOME>/SOUL.md if missing
instructions = compose_instructions(load_soul(), "Route requests to specialists.")
```

Set `SOUL_FILE` to point at a custom path; `compose_instructions` merges the
persona with your routing/tool instructions.

## Run the whole stack in one process

```python
from agentkit import Service, run_all

run_all([
    Service("a2a", lambda: serve_a2a(settings)),
    Service("mcp", lambda: serve_mcp(settings)),
    Service("bot", lambda: run_bot(settings)),
])
```

Services run on daemon threads; `run_all` blocks until SIGINT/SIGTERM. A
crashing service does not take down the others.

## Production features

| Area | API |
| --- | --- |
| **Logging** | `setup_logging`, `request_context`, `get_logger` (redaction built in) |
| **Token accounting** | automatic per-turn recording in `ChatRunner` → `repos.usage.totals()` |
| **Audit log** | `repos.audit.append(action, target=…, detail=…)` + `verify()` (hash chain) |
| **Tool RBAC / approval policy** | `ToolPolicy(allow=…, deny=…, require_approval=…)` |
| **Guardrails** | `scan_injection`, `wrap_untrusted`, `redact`, `check_egress` |
| **Error taxonomy** | `InvalidInput`, `NotFound`, `Conflict`, `PermissionDenied`, `DependencyMissing`, `RateLimited`, `UpstreamError` |
| **Health** | `health_routes([db_check(runtime)])` → `/healthz` + `/readyz`; `install_signal_handlers` |
| **Dead letters** | `durability.failed_workflows(queue=…)` |
| **Queues** | `durability.init(queues={"work": {"worker_concurrency": 4}})` |

## Design notes

- **Delegation, not `as_tool`.** v2 removed it; `Orchestrator` writes the tool.
- **One writer.** `repositories()` serializes DB access with a process lock;
  local SQLite/libSQL tolerates a single writer. WAL + busy-timeout are set.
- **Infra vs domain.** `agentkit.db.models` owns only `conversations`, `messages`,
  `a2a_tasks`, `scheduled_jobs`. Domain tables belong to your app; subclass
  `Repositories` and pass `repos_factory` to `build_runtime`.
- **DBOS workflows must be module-level** — agentkit provides the infra + the
  decorators; your app defines the workflows.
- **Approvals default-deny** without an approver.

## Development

```bash
uv sync --extra dev
uv run pytest            # 26 tests
uv run ruff check src tests
uv run mypy src/agentkit
uv build                 # sdist + wheel
```

Layout: `config`, `app`, `orchestrator`, `deps`, `approvals`, `session`,
`runtime`, `durability`, `scheduler`, `observability`, `guardrails`, `db/`,
`mcp/`, `a2a/`, `gateways/`.

## License

MIT.
