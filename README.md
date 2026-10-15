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
![Coverage](https://img.shields.io/badge/coverage-79%25-brightgreen)

---

## Highlights

- **A framework front door.** An `App` container with service providers
  (`register`/`boot`), a fluent `Agent` builder, short facades
  (`Memory`/`Schedule`/`DB`/`Events`/`Log`), lifecycle events + turn middleware,
  per-concern config, discoverable **skills** (`SKILL.md`), an Artisan-style
  `make:*` CLI, and a thin `Model`/`DB` layer — all additive over the building
  blocks below.
- **One process, one command.** `run_all(...)` supervises the worker, A2A, MCP,
  bot, and web UI in a single local process — no server to run.
- **Durable by default.** Conversation history and background work run on DBOS
  over local SQLite: turns, jobs, cron and one-off schedules survive restarts.
- **An operator console in the box.** Every agent serves a Vite + React +
  shadcn/ui web UI at `http://127.0.0.1:8787`: chat, conversations, usage, audit,
  A2A tasks, durable workflows, schedules, persona, config, and artifacts.
- **Agents that delegate.** `Orchestrator`/`Supervisor` route to specialist
  sub-agents as tools; a registry of local/A2A **handles**, a **mailbox**
  (`send`/`ask`/`broadcast`) and **handoff** let agents discover and talk to each
  other, emitting `agent.*` lifecycle events.
- **Async by default.** The data layer speaks `async`/`await` end to end
  (`sqlite+aiosqlite`), so concurrent turns, sub-agents and channels share one
  event loop; the engine/repositories/ORM/web UI/CLI are all async.
- **Multi-provider models.** `MODEL_NAME=provider:model` builds OpenAI,
  Anthropic, Google, Groq, Mistral, Ollama or any OpenAI-compatible endpoint
  (extend with `register_model_provider`).
- **Typed memory.** Facts/preferences/people/dates with a hybrid
  similarity+recency+importance recall, an owner **profile**, and a daily durable
  `memory:consolidate` task (dedupe/summarize/prune).
- **Full stack in one call.** `Agent.make(...).full()` expands to persona +
  memory + skills + HITL + safety; `App(...).fullstack()` boots config sections,
  schedules and any configured **channels** (Telegram, Slack, Email, Discord) —
  unconfigured layers stay idle.
- **Safe by construction.** Approvals default-deny; loopback binds; secrets and
  amounts are redacted from logs; every material action is audited.
- **Interop, both ways.** Consume and serve MCP servers and A2A agents.
- **Local-first.** No hosted account, no external services; state is files.

## Table of contents

- [Highlights](#highlights)
- [Install](#install)
- [60-second agent](#60-second-agent)
- [Framework front door (Laravel-style)](#framework-front-door-laravel-style)
- [Advanced primitives](#advanced-primitives)
- [Orchestrator + specialists](#orchestrator--specialists)
- [The full stack, in one call](#the-full-stack-in-one-call)
- [Async by default](#async-by-default)
- [Durable scheduling](#durable-scheduling-cron--one-off)
- [Durability](#durability)
- [MCP](#mcp)
- [A2A](#a2a)
- [Persona (`SOUL.md`)](#persona-soulmd)
- [Skills (`SKILL.md`)](#skills-skillmd)
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

Scaffold a project — a bare, sane skeleton you own and edit:

```bash
agentkit new my-agent && cd my-agent
cp .env.example .env          # set OPENAI_API_KEY
uv sync
agentkit tinker               # chat with your agent
```

Or work in an existing project:

```bash
agentkit workspace list                      # where agents live
agentkit webui                               # operator console for the current agent
```

Every agent that calls `run_all(..., settings=settings)` serves the web UI
automatically on `http://127.0.0.1:8787`.

## 60-second agent

```python
import asyncio
from pydantic_ai import RunContext
from agentkit import Agent, AgentSettings, App, Deps

async def add_note(ctx: RunContext[Deps], text: str) -> str:
    """Save a note."""
    ctx.deps.extras.setdefault("notes", []).append(text)
    return f"saved: {text}"

notes = (
    Agent.make("notes", deps_type=Deps)
    .instructions("Manage the owner's notes.")
    .memory()
    .tool(add_note)
    .output(str)
)
app = App(name="notes", settings=AgentSettings(owner_id="owner"), discover=False)
app.agent(notes)
app.boot()
print(asyncio.run(app.run("add a note: buy milk")).output)
```

`agentkit.Agent` here is the fluent **builder**; internal code that wants the raw
PydanticAI agent keeps `from pydantic_ai import Agent`. The legacy
`AgentApp.build(agent=..., settings=...)` still works as a deprecated shim.

## Framework front door (Laravel-style)

Everything above is the low-level surface and keeps working. On top of it sits an
`App` container with `Provider`s, a fluent `Agent` builder, short facades, an
event bus, a middleware pipeline, per-concern config, an Artisan-style CLI, and a
thin `Model`/`DB` layer.

```python
# bootstrap.py  —  `agentkit serve` boots bootstrap:app
from agentkit import App
from nudge.providers import NudgeProvider

app = App(name="nudge", settings=Settings)
app.providers([NudgeProvider])          # package providers auto-load via entry points
```

```python
# providers/nudge.py
from agentkit import Agent, Provider

class NudgeProvider(Provider):
    def register(self, app):
        app.agent(
            Agent.make("nudge")
            .persona()                  # SOUL.md (read live every run)
            .instructions(ORCHESTRATOR)
            .memory()                   # remember/recall/forget tools
            .tool(handle_reminders)
            .output(str)
        )
        app.config("memory", MemorySection)

    def boot(self, app):
        async def audit(event):
            async with app.repositories() as repos:
                await repos.audit.append("turn.end", target=event.conversation_id)
        app.on("turn.end", audit)
```

```python
# facades resolve the current App
from agentkit import DB, Memory, Model, Schedule

await Memory.remember("My name is Ada")
await Schedule.cron("weekly", "0 8 * * 1", "digest")

class Reminder(Model, table=True):
    name: str
    cron: str

async with DB.transaction():
    await Reminder.create(name="digest", cron="0 8 * * 1")
await Reminder.where(cron="0 8 * * 1").first()
```

```bash
agentkit make:provider notes     # scaffold generators (overwrite-guarded)
agentkit make:tool add_note
agentkit serve                   # boot bootstrap:app and run its channels
agentkit tinker                  # REPL against the booted app
agentkit inspect                 # agents, tools, channels, commands, config
agentkit schedule:list
agentkit about
```

**IMPORTANT — `Agent` shadowing.** In *application* code, `from agentkit import
Agent` is the **builder**. Internal/low-level code keeps importing PydanticAI
directly:

```python
from pydantic_ai import Agent        # internal: the raw PydanticAI agent
from agentkit import Agent           # app-facing: the fluent builder
```

**Lifecycle.** `App.boot()` is idempotent and ordered: every `Provider.register()`
runs first (bindings/concerns, no side effects), then every `Provider.boot()`
(schedules, listeners), then services. Importing a provider must be
side-effect-free. Facades resolve the current app through a contextvar **and** a
thread-local, and `run_all` seeds the app into its worker threads, so facades work
inside channels.

### Laravel → agentkit concept map

| Laravel | agentkit |
| --- | --- |
| Service container | `App` (`bind`/`singleton`/`make`/`build`) + autowiring |
| Service provider | `Provider` (`register`/`boot`; `bindings`/`singletons`; `DeferrableProvider`) |
| Facade | `Memory`, `Schedule`, `DB`, `Events`, `Log`, `Cache`, `Storage`, `Queue`, `Feedback` |
| Global helpers | `app()`, `config()`, `env()`, `dispatch()`, `event()`, `storage()`, `cache()`, `queue()` |
| Artisan | `agentkit` CLI (`new`, `make:*`, `serve`, `tinker`, `inspect`, `schedule:run`, `queue:work`) |
| Events & listeners | `app.on("turn.end", ...)` + `Listener` |
| Middleware | `app.middleware(...)` + `Middleware` over the turn |
| `config/*.php` | `config/<name>.py` + `Section` (`defaults < file < env`) |
| Eloquent model | `Model` + `Repository` (`where`/`create`/`update`/`paginate` for free) |
| Notifications | `Notification` + `app.notify(...)` (log/conversation/telegram) |
| Jobs & queues | `Job` + `await app.dispatch(...)` (durable via DBOS) |
| Scheduler | `app.schedule("task").every_minute()` |
| Cache | `Cache` facade (`put`/`get`/`remember`) |
| Filesystem | `Storage` facade |
| Validation | `Rule` + `validate(...)` |
| Services | `Service` base (from `agentkit.foundation.service`) |
| `php artisan serve` | `agentkit serve` |

## Advanced primitives

### Streaming
```python
async for event in app.stream("hello", conversation_id="cli:1"):
    if event.kind == "text":
        print(event.text, end="")
    elif event.kind == "final":
        print("\n" + event.result.output)
```
`App.stream` / `ChatRunner.stream` yield `StreamEvent`s (`text`, `final`); history and
usage are recorded exactly as for `run`. Tool events keep firing via the lifecycle hooks.

### Model routing + cost
```python
from agentkit import ModelRouter, default_pricing

router = (
    ModelRouter()
    .route("openai:gpt-5-mini", when=lambda ctx: len(ctx.text) < 500)
    .route("openai:gpt-5")
    .otherwise("openai:gpt-4o-mini")
    .with_fallbacks("openai:gpt-4o")
)
app.model_resolver(router)                       # chosen per turn from the Turn context
default_pricing().set("openai:gpt-5-mini", input=0.00025, output=0.002)
```
Every turn records an estimated `cost_usd` alongside token counts.

### Context compaction
```python
from agentkit import Compactor

app.history_processor(Compactor(max_tokens=8000, keep_recent=0.45))
# or, shorthand:  app.compact(max_tokens=8000)
```
Tiered and rolling: **pinned** facts/constraints stay verbatim, the **recent** turns stay
verbatim, and older turns are folded into a structured summary (objective, facts,
constraints, decisions, tool results, open threads) that is merged incrementally — so
compaction is cheap and does not drift. Heuristic offline; pass `model=` for model-based
extraction. `summarize_older` and `truncating_processor` remain simple alternatives.

### Knowledge (RAG)
```python
from agentkit import Agent, KnowledgeBase

kb = KnowledgeBase()
kb.add_directory("docs", pattern="**/*.md")
kb.add("Free-form note text", source="note")
agent = Agent.make("notes").instructions("…").knowledge(kb).output(str).build()
```
Indexes chunks with embeddings and adds a `search_knowledge` tool (plus a source listing
in the instructions). Index from the CLI with `agentkit knowledge add|add-text|search|list`.

### Capability shortcuts
Builder pass-throughs to the PydanticAI capabilities of the same name:
`.web_search()` `.web_fetch()` `.x_search()` `.thinking(effort=...)` `.caching()`
`.tool_search()` `.image_generation()` `.instrumentation()` `.native_tool(...)` `.sandbox(...)`.

### Sandboxed workspace
```python
from agentkit import Agent, Sandbox

agent = Agent.make("coder").instructions("…").workspace(Sandbox("./work")).output(str).build()
```
Backed by `pydantic_ai.workspaces` (`LocalWorkspaceBackend` + `ReadOnlyWorkspace`) — agentkit
does not re-implement confinement or process execution. Adds `read_file`/`list_files`/
`write_file`/`run_command`. `Sandbox(path, read_only=True, env={...})` to restrict. This is a
*workspace*, not an OS sandbox: use a container/VM for untrusted code.

### Evaluations
```python
from agentkit.evals import Case, EvalSuite

report = await EvalSuite(
    [
        Case("adds", input="2+2?", expect="4"),
        Case("uses the tool", input="find x", calls="lookup"),
        Case("in persona", input="hi", not_contains=["As an AI language model"]),
    ],
    name="smoke",
).run(app)
report.raise_for_failures()
```
Assertions: `expect`, `contains`, `not_contains`, `regex`, `calls`, `not_calls` and a custom
`check`; load suites from YAML/JSON with `EvalSuite.from_file`; run with `agentkit eval suite.yaml`.
Executed and reported by Pydantic's `pydantic_evals`.

### Human-in-the-loop
```python
agent = Agent.make("desk").instructions("…").clarify().output(str).build()
app.agent(agent).clarify(lambda question, options: ask_the_user(question))
```
`ask_user` hands a question to your handler; with no handler it instructs the model to ask
in its reply. `App.resume(deferred_tool_results)` continues a turn that paused on deferred tool
calls (see [Approvals/scheduling](#production-features)). Register output checks with
`.output_validator(fn)`.

### Planning, graphs, teams
```python
from agentkit import StateGraph, END, Supervisor
from agentkit.planning import Planner

plan = await Planner(agent).execute("Launch the beta")     # plan-and-execute
graph = StateGraph(); graph.add_node("draft", draft); graph.add_edge("draft", END); ...
supervisor = Supervisor({"writer": writer, "researcher": researcher}).build()
```
`Planner` decomposes a goal then runs each step; `StateGraph` is a small async state machine
(conditional edges, cycle guard); `Supervisor`/`spawn_tool` route to or spawn sub-agents
(usage/model forwarded).

### Tooling
```python
agent = (Agent.make("t").instructions("…")
    .tool(lookup, cache_ttl=60, timeout=5, sequential=False, defer_loading=True)
    .toolset(my_toolset)
    .output(str).build())
```
Per-tool `retries`/`timeout`/`sequential`/`defer_loading`, a TTL result cache
(`cached_tool`), and generic toolsets (MCP, function toolsets).

### Safety
```python
from agentkit import ModerationPolicy
from agentkit.moderation import moderation_middleware, moderation_hooks

app.middleware(moderation_middleware(ModerationPolicy(banned=["…"], redact_pii=True)))
```
`scan_pii`/`redact_pii` (email, phone, SSN, card, IBAN), moderation middleware + output hooks,
and user feedback (`Feedback.add(rating=1, conversation_id=…)`, `Feedback.average()`).

### Ops
```python
from agentkit import Budget, PromptRegistry
app.budget(Budget(max_cost=5.0, max_tokens=1_000_000, window_seconds=86400))
prompts = PromptRegistry.from_settings().discover()       # prompts/<name>.md, versioned
agent = Agent.make("x").prompt(prompts, "greeting", name="Ada").output(str).build()
```
Budgets are checked before each turn (`BudgetExceeded`); the prompt registry is file-backed and
versioned; conversations branch with `app.fork(...)` / re-run with `app.replay(...)`.

### Multimodal + audio
```python
from agentkit import image, transcribe, synthesize
await app.run(content(text("What is this?"), image("cat.png")))
text = transcribe("note.m4a"); audio_bytes = synthesize("Call mom at 5.")
```
`image`/`audio`/`document` build content parts from files, bytes or URLs; generated media is
captured into `ChatResult.artifacts`; STT/TTS use the OpenAI audio API (client injectable).

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

Agents can also talk to each other directly. A registry of **handles** (local or
remote A2A) plus a **mailbox** and **handoff** gives you peer messaging; attach
the tools with the builder and the model can use them:

```python
from agentkit import Agent, AgentRegistry, Mailbox, AgentHandle

registry = AgentRegistry()
registry.register(AgentHandle.local(writer, capabilities=["writing"]))
mailbox = Mailbox(registry, events=app.events)

agent = (
    Agent.make("lead")
    .instructions("Coordinate the team. Use ask_agent/handoff_to when useful.")
    .agents(registry)
    .mailbox(mailbox)
    .full()
    .build()
)
# tools: send_to, ask_agent, broadcast, list_agents, handoff_to
```

See [Agent Communication](/guide/agent-communication) for registry routing,
`ask`/`broadcast`, `handoff_to` (full transcript or brief, with `MAX_HANDOFFS`),
fallbacks and the `agent.*` events.

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

## Skills (`SKILL.md`)

Skills are discoverable folders of instructions the agent loads **on demand**
(progressive disclosure): the model sees a cheap name+description index and
pulls the full how-to only when it is relevant.

```
skills/
  pdf-tools/
    SKILL.md              # front matter + instructions
    references/style.md   # bundled files, read via read_skill_file
    scripts/extract.py
```

```markdown
---
name: pdf-tools
description: Extract text and tables from PDF files.
allowed-tools: [read_skill_file]
---

# PDF tools
Call `read_skill_file("pdf-tools", "references/style.md")` for house style, then …
```

```python
from agentkit import Agent, SkillRegistry

registry = SkillRegistry.from_settings().discover()   # ./skills + <AGENT_HOME>/skills
agent = Agent.make("notes").instructions("…").skills(registry).output(str).build()
# or discover lazily from settings:  Agent.make("notes").skills()
```

`skills()` adds a compact index to the instructions plus three tools —
`list_skills`, `load_skill(name)` (full instructions) and
`read_skill_file(name, path)` (bundled files, path-traversal safe). Roots come
from `skills_dir` (or the project `./skills` and `<agent_home>/skills` when
unset); set `skills_enabled=false` to turn them off. Inspect from the CLI:

```bash
agentkit skills list
agentkit skills show pdf-tools
```

## The full stack, in one call

`Agent.full()` expands a builder to the whole agent stack (each layer toggleable,
idempotent, and skipped when its settings flag disables it):

```python
from agentkit import Agent, App, FullStackProvider

agent = Agent.make("assistant").instructions("Be helpful.").full().build()

app = App(name="assistant").fullstack()   # FullStackProvider
app.boot()                                # schedules + any configured channels
```

`FullStackProvider` declares the `memory`/`channels`/`interop`/`queue` config
sections, registers the daily durable `memory:consolidate` task, and wires a
gateway channel (Telegram/Slack/Email/Discord) for each token you provide —
nothing raises when a layer is unconfigured. `agentkit new` scaffolds this full
stack by default (`--minimal` for the older skeleton), and `agentkit inspect` /
`GET /api/info` show which layers are active. See
[The Full Stack](/guide/fullstack) and [Multiple Model Providers](/guide/multi-provider).

## Async by default

The data layer is async end to end. `build_runtime` creates an async engine (no
I/O); the schema is created lazily on the first scope:

```python
from agentkit import build_runtime, repositories

runtime = build_runtime(settings)
async with repositories(runtime) as repos:
    await repos.conversations.get_or_create("cli:default")
```

Repositories, `Model`/`Repository` terminals, `ChatRunner`, `KnowledgeBase`, the
`Memory`/`Feedback`/`Queue`/`Schedule` facades, the web UI and the CLI are all
coroutines. Two seams cannot be async — DBOS workflow/step bodies and build-time
bootstrapping — and they bridge with `agentkit._sync.run_sync`, which runs the work
on a private loop rather than the caller's. See [Async Data Layer](/guide/async).

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
- **Async by default.** The data layer is async (`sqlite+aiosqlite`): repositories,
  `Model`/`Repository` terminals, conversations, memory, knowledge, the web UI and
  the CLI are coroutines. SQLite is single-writer, so WAL + a busy timeout replace
  the old global lock; the only sync seams (DBOS steps, build-time bootstrap) drive
  the async layer on a private loop via `agentkit._sync.run_sync`.
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
