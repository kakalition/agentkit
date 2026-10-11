# agentkit

Opinionated building blocks for **PydanticAI v2 personal-assistant agents** —
extracted from the Artemis finance agent. It gives you, out of the box:

- **Orchestrator + specialists** — register sub-agents as delegation tools.
- **Typed deps + human-in-the-loop approvals** via PydanticAI deferred tools.
- **Durable history** in libSQL, keyed by conversation id.
- **Durable execution** (DBOS) on a local SQLite system DB — workflows, queues, cron.
- **MCP** client registry (prefixed toolsets, process-owned lifecycle) + server serving.
- **A2A** task-based server with a durable `TaskStore`, plus an outbound client.
- **CLI (Typer) and Telegram (aiogram)** helpers with Markdown rendering.
- **Resilience** (timeouts, retries, usage caps) and **free observability** (console / OTLP / Logfire).

## Install

```bash
uv add git+<repo>            # or: uv sync --extra dev
```

Requires Python 3.11–3.12.

## Quickstart

```python
from agentkit import AgentSettings, Orchestrator, Deps, build_runtime, build_model
from agentkit.runtime import repositories, build_deps
from agentkit.session import ChatRunner
from pydantic_ai import Agent

# 1) a specialist agent
notes = Agent(name="notes", deps_type=Deps, output_type=str, instructions="Manage notes.")

@notes.tool
async def add_note(ctx, text: str) -> str:
    ctx.deps.repos.session.add(...)  # your domain write
    return "saved"

# 2) an orchestrator that delegates to it
orchestrator = Orchestrator(name="assistant", instructions="Route to specialists.")
orchestrator.add_specialist(notes, tool_name="handle_notes", description="Add/list notes.")

# 3) run a turn with durable history
runtime = build_runtime(AgentSettings(owner_id="owner"))
with repositories(runtime) as repos:
    deps = build_deps(runtime, repos, model=build_model(runtime.settings))
    runner = ChatRunner(deps, agent=orchestrator.agent, conversation_id="cli:default")
    result = await runner.send("add a note: buy milk")
    print(result.output)
```

## Modules

| Module | Provides |
| --- | --- |
| `agentkit.config` | `AgentSettings`, `build_model`, `model_settings`, `usage_limits` |
| `agentkit.orchestrator` | `Orchestrator`, `make_delegate`, `delegate` |
| `agentkit.deps` / `agentkit.approvals` | `Deps`, `ApprovalRequest`, `approval_capability` |
| `agentkit.session` | `ChatRunner`, `load_history`, `save_new_messages` |
| `agentkit.runtime` / `agentkit.db` | `Runtime`, `repositories`, engine/repos/migrations |
| `agentkit.durability` | DBOS `init`, `register_queue`, `enqueue`, `apply_schedules` |
| `agentkit.mcp` | `MCPRegistry`, `MCPServerSpec`, `serve_mcp`, `first_out` |
| `agentkit.a2a` | `TaskAgentExecutor`, `build_a2a_app`, `A2AClient`, `SQLAlchemyTaskStore` |
| `agentkit.gateways` | `send_markdown`, `ApprovalBroker`, `is_allowed`, `build_cli` |
| `agentkit.observability` / `agentkit.guardrails` | `setup_logfire`, `is_loopback`, `warn_if_exposed` |

## Design notes

- **Delegation, not `as_tool`.** PydanticAI v2 removed `Agent.as_tool`; `Orchestrator`
  generates a tool per specialist that forwards `deps`/`usage`/`model`.
- **Money/domain logic is out of scope.** Keep domain repos in your app; subclass
  `agentkit.db.repositories.Repositories` and pass it via `build_runtime(..., repos_factory=...)`.
- **One writer.** `repositories()` serializes DB access with a process lock; local
  SQLite/libSQL tolerates a single writer.
- **Approvals default-deny** when no `deps.approve` is wired (safe over MCP/A2A).
- **DBOS workflows must be module-level** in your app; agentkit provides the
  infrastructure and re-exports the decorators you need.

## Tests

```bash
uv run pytest
uv run ruff check src tests
uv run mypy src/agentkit
```

MIT licensed.
