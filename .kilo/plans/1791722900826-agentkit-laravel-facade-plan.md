# agentkit Laravel-style interface — Implementation Plan

## Goal

Give agentkit a framework "front door" as expressive, intuitive and extensible as
Laravel, layered over the existing building blocks (which must keep working):

- an **`App` container + `Provider`** model with `register()` / `boot()`,
- a **fluent `Agent` builder`,
- short **class-method facades** (`Memory`, `Schedule`, `DB`, `Events`, `Log`),
- an **Artisan-style CLI** with `make:*` generators,
- a **lifecycle event bus + middleware pipeline**,
- **per-concern config** sections over `AgentSettings`,
- a **thin Eloquent-like `Model` / `DB`** layer over SQLModel.

## Confirmed decisions

1. **Phased facelift**, additive on top of existing internals (framework facelift, not a rewrite).
2. **Service Providers + container** are the boot model (`register`/`boot`).
3. **Discovery:** app providers are explicit in a conventional `bootstrap` module; installed
   packages contribute providers via `[project.entry-points."agentkit.providers"]`, auto-loaded.
4. **Agent DSL:** fluent builder (`Agent.make("notes").persona().instructions(...).tool(...).memory()`),
   `@agent.tool` decorators still supported.
5. **Naming:** short names from `agentkit` with class-method facades (`Agent.make`, `Memory.remember`,
   `Schedule.cron`). App code imports agentkit's `Agent`.
6. **`App` hosts one primary agent** (matches the one-dir-per-agent model); specialists live under `Orchestrator`.
7. **Provider surface:** typed concerns (`agent`, `tool`, `channel`, `commands`, `schedules`,
   `migrations`, `on`, `middleware`, `config`) plus a `bind(name, factory)` escape hatch.
8. **Persistence:** thin expressive `Model` / `DB` layer over SQLModel/`Repositories`; no schema or
   Alembic rewrite.
9. In scope this round: Artisan CLI + generators, events + middleware, per-concern config, migrate
   clients (nudge first, then calliope/artemis).

## Non-goals

- Multi-agent-per-`App`, auth, multi-user, remote hosting.
- Full Eloquent (relationships, eager loading, soft deletes, factories/seeders).
- Replacing SQLModel/Alembic, the libSQL runtime, or the `~/.agentkit/<agent>` workspace layout.
- Removing or changing existing exports (see Back-compat).

## Target API (what "done" looks like)

```python
# bootstrap.py  (conventional module; `agentkit serve` boots `bootstrap:app`)
from agentkit import App
from nudge.config import Settings
from nudge.providers import NudgeProvider, TelegramProvider

app = App(name="nudge", settings=Settings)
app.providers([NudgeProvider, TelegramProvider])   # package providers auto-added via entry points
```

```python
# nudge/providers/nudge.py
from agentkit import Agent, Provider

class NudgeProvider(Provider):
    def register(self, app):
        self.agent = (
            Agent.make("nudge")
            .persona()                       # SOUL.md (replaces compose_instructions(load_soul(...)))
            .instructions(ORCHESTRATOR)
            .memory()                        # replaces attach_memory(agent)
            .tool(handle_reminders)
            .output(str)
        )
        app.agent(self.agent)
        app.commands([AddReminder, ListReminders, FireReminder])
        app.schedules([*reminder_schedules])
        app.config("memory", MemoryConfig)

    def boot(self, app):
        app.on("turn.end", lambda ctx: app.repos.audit.append("turn", target=ctx.conversation_id))
```

```python
# channels + serving  (replaces the four ChatRunner wirings in nudge/cli.py)
app.channel("cli")
app.channel("telegram", telegram_bot)
app.channel("a2a", skills=[{"id": "reminders", "name": "Reminders"}])
app.channel("mcp", tools=[add_reminder, list_reminders])
app.channel("webui")
app.serve()                  # == run_all(...) over registered channels + webui
await app.run("hi")          # one-turn runner
app.answer                   # (conversation_id, text) -> ChatResult for webui/a2a/mcp
```

```python
# facades + model layer
from agentkit import Memory, Schedule, DB, Model

await Memory.remember("My name is Ada")
Schedule.cron("weekly", "0 8 * * 1", "digest")

class Reminder(Model, table=True):
    name: str
    cron: str

Reminder.where(cron="0 8 * * 1").first()
with DB.transaction():
    Reminder.create(name="x", cron="0 8 * * 1")
```

```bash
agentkit make:provider nudge     # scaffolding generators
agentkit make:tool add_reminder
agentkit serve                   # boot bootstrap:app and run channels
agentkit tinker                  # REPL chat against the booted App
agentkit inspect                 # agents, channels, tools, schedules
agentkit schedule:list
```

## Object model

```
App (container + lifecycle, one primary agent)
├─ settings: AgentSettings (env)  ── config("section", Schema) layered on top
├─ providers: [Provider]           explicit list + entry-point auto-discovery
├─ container: bindings/singletons  (bind/singleton/make)
├─ agent: AgentBuilder             primary agent
├─ channels: {name -> factory}     cli|telegram|a2a|mcp|webui
├─ commands / schedules / migrations registries
├─ events: Dispatcher              lifecycle hooks
└─ middleware: Pipeline            wraps the turn

boot():
  1. instantiate providers
  2. provider.register(app) in order   (bindings, concerns; no side effects)
  3. provider.boot(app) in order       (side effects: schedule tasks, listeners)
  4. set current App for facades (contextvar + thread-local)
```

- `App.boot()` is idempotent; `App.serve()` boots then `run_all`s channel services + webui.
- `App.answer`/`app.run` centralise `build_runtime → build_deps → ChatRunner` so clients stop
  repeating it (kills the four copies in `nudge/src/nudge/cli.py`).
- Facades resolve the **current App**: a `contextvar` set by `App.boot()`/`App.serve()`, plus a
  thread-local seeded by `run_all` worker threads (services run on daemon threads — see Risks).
- `AgentApp` stays as a deprecated alias/shim over `App` (same behaviour).

## Phased task list

### Phase 0 — foundation (no behaviour change)
1. Add `src/agentkit/foundation/` with `container.py` (`Container` with `bind`/`singleton`/`make`),
   `provider.py` (`Provider` base with `register`/`boot`, no-op defaults), `application.py` (`App`),
   `events.py` (`Dispatcher`), `pipeline.py` (`Pipeline`), `facade.py` (`Facade` base + current-app
   contextvar/thread-local).
2. Re-export from `agentkit/__init__.py` additively (`App`, `Provider`, `Facade`, `Event`); do not
   touch existing exports.

### Phase 1 — App + Providers + fluent Agent + facades
3. `Agent` builder (`foundation/agent.py`) that assembles a PydanticAI `Agent`: `.persona()`,
   `.instructions()`, `.tool()/.tools()`, `.specialist()/.orchestrate()`, `.memory()`,
   `.approvals()`, `.policy()`, `.output()`, `.model()`, `.build()`. Assert equivalence with the
   current construction in tests.
4. `App` typed concerns: `agent()`, `tool()`, `channel()`, `commands()`, `schedules()`,
   `migrations()`, `config()`, `on()`, `middleware()`, `bind()`, plus `run()`, `serve()`, `answer`.
5. Facades: `Memory`, `Schedule`, `DB`, `Events`, `Log`, `Agent` (if used as a facade). `Log` wraps
   `agentkit.logging`.
6. Provider auto-discovery via `importlib.metadata.entry_points(group="agentkit.providers")`;
   `App(discover=False)` to disable.
7. Deprecate `AgentApp` → alias `App`; keep `AgentApp.build/run` working.

### Phase 2 — events, middleware, config
8. Emit lifecycle events at the real seams: `boot`, `turn.start`, `turn.end`, `tool.start`,
   `tool.end`, `approval.asked`, `channel.message` (hook `ChatRunner.send` and
   `ApprovalBroker`/`approval_handler`).
9. Middleware pipeline wrapping the turn; port `guardrails`/`approvals`/`policy` to built-in
   middleware registered by default (keep the standalone functions).
10. Config: `Section` base; `App.config(name, schema)` reads `config/<name>.py` (project) with
    env overrides still winning. Layered precedence: defaults < config file < env.

### Phase 3 — Artisan-style CLI + generators
11. `Command` base class + provider command registry; merge into the existing Typer `app` in
    `agentkit/cli.py` without removing current commands.
12. Generators: `make:agent`, `make:provider`, `make:tool`, `make:channel`, `make:command`,
    `make:model` (templates + overwrite guard).
13. Runtime commands: `serve`/`up`, `tinker`, `inspect`, `schedule:list`, `about`; boot target
    resolved from `AGENTKIT_BOOTSTRAP` (default `bootstrap:app`).

### Phase 4 — thin Model / DB
14. `Model` base over SQLModel with `query()`, `where()`, `first()/get()`, `create()`, `update()`,
    `delete()`, `paginate()`, `count()`; `DB` facade for session/transaction/`repos`.
15. Bridge: `app.db` and `Model` resolve the active `Repositories`; existing repo classes remain.

### Phase 5 — migrate clients + docs
16. Rewrite **nudge** on the new API as the reference app; assert parity against the current nudge
    test suite (same tools, chat output, schedules, telegram behaviour).
17. Migrate **calliope**, then **artemis** (artemis's custom `Repositories` gains `memories`).
18. Rewrite README sections + add a "Laravel-to-agentkit" concept map; document deprecations.

## Back-compat & migration

- All existing exports and modules keep working; new surface is a superset.
- `AgentApp` becomes a shim over `App`; `build_runtime`/`build_deps`/`ChatRunner` are reused
  internally and remain public.
- `agentkit.Agent` shadows `pydantic_ai.Agent` in **app** code only; internal modules keep importing
  PydanticAI directly. Documented prominently.
- Clients migrate one at a time; no coordinated big-bang.

## Risks & mitigations

- **Facades vs threads:** `run_all` runs services on daemon threads; a contextvar alone won't reach
  them. Seed the thread-local current-app at thread start in `run_all`, and allow explicit
  `facade.using(app)` scoping. Add a threaded facade test.
- **Import cycles:** `facades ↔ application ↔ providers`. Keep foundation modules dependency-light;
  resolve facades lazily via the current App, never import `application` at module top in facades
  that providers import.
- **Boot ordering:** schedules/tasks must register before `init_scheduler` (see nudge comment).
  Define explicit ordering: all `register()` → all `boot()` → services.
- **Entry-point side effects:** importing a provider must be side-effect-free; only `register`/`boot`
  may act. Wrap discovery failures to log-and-continue.
- **Name shadowing** of `pydantic_ai.Agent`: documented; lint example in README shows the correct
  import in app vs internal code.
- **Scope creep** toward full Eloquent: explicitly capped at the thin layer.

## Validation

- Unit tests: container (`bind`/`singleton`/`make`), provider lifecycle order, entry-point discovery,
  event dispatch order + payloads, middleware short-circuit/ordering, config precedence
  (default < file < env), facade resolution incl. threads, generator output imports and boots,
  `Model` query results equal to the equivalent raw-repo calls.
- Equivalence test: `Agent.make(...)` produces the same PydanticAI tool/instruction set as the
  current hand-built agents (nudge/calliope fixtures).
- Parity test: nudge rewritten on the new API passes the existing nudge test suite unchanged.
- Keep gates green: `uv run pytest --cov=agentkit`, `ruff check`, `mypy src/agentkit`, bandit;
  README quickstart examples are executable.

## Open questions (decide during implementation, defaults noted)

- Exact facade set (`Log`, `Agent` as facade) — default: `Memory`, `Schedule`, `DB`, `Events`, `Log`.
- Event name style (`turn.end` vs `turn:end`) — default: dotted.
- Config file format (Python `config/*.py` vs `agentkit.toml`) — default: Python modules + env.
- Whether `serve` also runs the DBOS worker by default — default: yes, mirroring `nudge up`.

## Handoff

Implementation requires source edits; switch to an implementation-capable agent to execute this
plan.
