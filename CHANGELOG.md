# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased] — full-stack agent

### Added
- **`Agent.full()`** — expand a builder to the whole agent stack in one call
  (persona + typed memory + skills + HITL approvals + safety policy + optional
  knowledge/workspace/peer tools). Every layer is toggleable and idempotent, and
  respects the `memory_enabled`/`skills_enabled`/`approvals_enabled`/
  `subagents_enabled` settings flags (a disabled layer is skipped silently).
- **`FullStackProvider`** (`App(...).fullstack()`) — boot the full stack from
  settings/config: per-concern config sections (`memory`, `channels`, `interop`,
  `queue`), the daily durable `memory:consolidate` schedule, and gateway channels
  registered only when their token/env is present. Unconfigured layers stay idle
  and never raise.
- **Multi-provider model registry** (`agentkit.model_providers`): `MODEL_NAME` is
  `provider:model`; `resolve_model(name, settings)` dispatches to openai,
  openai-compatible, anthropic, google, groq, mistral and ollama (plus
  `register_model_provider(prefix, factory)` for custom providers). `build_model`
  is now a thin wrapper. Missing keys raise a clear `ConfigurationError` naming
  the env var; an unknown prefix names the supported set.
- **Typed memory + owner profile**: `Memory` gains `importance`, `last_used_at`,
  `access_count`, `source_conversation_id` and `expires_at`; a new `OwnerProfile`
  table + `profile` repo; `MemoryRepo.search` is now a hybrid of semantic
  similarity, recency and importance (weights in settings), and adds
  `record_use`/`expired`/`prune_expired`/`near_duplicates`/`merge`. New tools
  `remember_person`/`update_profile`/`get_profile`; `memory_digest` groups facts
  by kind and includes the profile. **`memory:consolidate`** (durable task +
  `agentkit memory:consolidate`, scheduled daily) dedupes, summarizes and prunes.
  CLI: `memory:list`/`memory:forget`/`memory:profile`.
- **Shared `Gateway` base + channels**: `Gateway` owns the allow-list,
  external-id→conversation mapping, `run_turn`/`stream_turn`, approval futures and
  a `Service` factory. `TelegramGateway` refactors Telegram onto it (helpers
  `is_allowed`/`send_markdown`/`run_turn`/`ApprovalBroker` unchanged), plus new
  `SlackGateway` (socket mode), `EmailGateway` (stdlib IMAP/SMTP) and
  `DiscordGateway` (reaction approvals). Settings for each; notifier senders.
- **Agent-to-agent communication** (`agentkit.agents`): `AgentHandle` (uniform
  local/remote-A2A wrapper), `AgentRegistry` (capability resolution + roster),
  `Mailbox` (in-process/durable `send`/`ask`/`broadcast` with per-agent inboxes
  and events), `handoff` (full-transcript or brief, with a `max_handoffs` guard)
  and peer tools `send_to`/`ask_agent`/`broadcast`/`list_agents`/`handoff_to`.
  Builder sugar: `.subagent()`, `.agents()`, `.mailbox()`, `.handoff_to()`.
- **Unified orchestrator**: `Orchestrator` and `Supervisor` are one
  registry-driven implementation; delegation forwards `deps`/`usage`/`model`,
  supports capability routing + ordered fallbacks, and emits
  `agent.started`/`finished`/`message`/`handoff`/`error` events.
- **Concurrency**: `Compactor` now keeps rolling state **per conversation**
  (`compact(..., conversation_id=…)`), fixing cross-conversation memory leakage.
- **Introspection**: `/api/info` and `agentkit inspect` report the enabled stack
  (providers, memory, skills, approvals, sub-agents, channels, interop, queue);
  more credential fields are masked.

### Changed
- **Async data layer (breaking).** The whole data layer is async by default:
  - the engine is `sqlite+aiosqlite` (the local `sqlite+libsql` URL is mapped),
    with WAL + a busy timeout and `NullPool`; `init_db`/`sync_missing_columns` are
    awaited (`connection.run_sync`) so DDL never blocks the loop;
  - `runtime.repositories()` is an async context manager, and `runtime` gained
    `ensure_initialized` (once, guarded by an `asyncio.Lock`) and
    `run_repositories_sync` for the sync seams;
  - **every** repository method, the `Model`/`Query` and `Repository`/
    `RepositoryQuery` terminals, `DB.session()`/`DB.transaction()`, `ChatRunner`,
    `load_history`/`save_new_messages`, `KnowledgeBase`, `consolidate_memories`,
    the `Memory`/`Feedback`/`Queue`/`Schedule` facades, the web UI endpoints, the
    CLI commands, and the A2A task store are now coroutines (`await …`);
  - embedding/query work runs via `asyncio.to_thread`; the `DB_LOCK` global is
    gone (WAL + a bounded busy timeout replace it);
  - the two seams that cannot be async — DBOS workflow/step bodies and build-time
    bootstrapping — bridge through `agentkit._sync.run_sync` (a private event
    loop, never nested inside a running loop).
  The scaffold, docs and tests are updated to async; `tests/conftest.py` yields an
  async `repos` fixture.

### Refactored
- Split the largest modules to keep them small and focused: `db/repositories`
  (965 → a package with a module per concern), `foundation/scaffold`
  (templates split into `minimal`/`full`), and `cli` (a package of command
  modules behind a shared `_app`). Public import paths are unchanged.

### Library swaps
- **Behaviour-preserving** swaps: validation compiles to Pydantic
  `TypeAdapter`s (EmailStr/StringConstraints) instead of the hand-rolled regex
  engine; tool caching uses `cachetools.TTLCache` under an `asyncio.Lock`;
  `SKILL.md`/prompt front matter parses with `yaml.safe_load` (malformed front
  matter now raises); `chunk_text` uses `semantic-text-splitter`;
  vectors/search use numpy (base64 float32 format preserved, `sqlite-vec`
  detected when available); `StateGraph` is compiled to `pydantic-graph`; web UI
  SSE uses `sse-starlette`; pricing already used `genai-prices`.
- **Scaffold**: `agentkit new` defaults to the full-stack project
  (`FullStackProvider` + `Agent.full()` + `app/Channels/` + `config/memory.py`);
  `agentkit new --minimal` writes the older skeleton. `scaffold_project(...,
  full=False)` for the minimal set.

## [Unreleased]

### Added
- **Framework front door** (`agentkit.foundation`): an `App` container with
  `Provider` (`register`/`boot`) service providers, entry-point discovery
  (`agentkit.providers`), typed concerns (`agent`/`tool`/`channel`/`commands`/
  `schedules`/`migrations`/`config`/`on`/`middleware`/`bind`), plus `run`/`serve`/
  `answer`. The fluent `Agent.make(...).persona().instructions().tool()/
  .specialist().memory().approvals().policy().output().build()` builder assembles
  a PydanticAI agent. `agentkit.Agent` is the app-facing builder; internal modules
  keep importing `pydantic_ai.Agent`.
- **Facades**: `Memory`, `Schedule`, `DB`, `Events`, `Log` resolve the current
  `App` through a contextvar **and** a thread-local (`run_all` seeds worker
  threads), with `facade.using(app)` scoping.
- **Events + middleware**: a `Dispatcher` (`app.on("turn.end", ...)`) with
  lifecycle events (`boot`, `turn.start`/`turn.end`, `channel.message`,
  `tool.start`/`tool.end`, `approval.asked`, `guardrails.injection`) and a turn
  `Pipeline`; capability middleware for lifecycle, `ToolPolicy` and guardrails.
- **Per-concern config**: `Section` with `defaults < config/<name>.py < env`.
- **Artisan-style CLI**: `serve`/`up`, `tinker`, `inspect`, `schedule:list`,
  `about`, and `make:agent|provider|tool|channel|command|model` generators
  (overwrite-guarded); boot target from `AGENTKIT_BOOTSTRAP` (default
  `bootstrap:app`). `Command` base for provider-contributed commands.
- **Project scaffold**: `agentkit new <name>` writes a bare, runnable skeleton
  (App + provider + assistant agent + tool + skill + prompt + config section +
  eval suite + test), the Laravel-style "new project" experience.
  `scaffold_project(...)` is also available programmatically.
- **Thin `Model` / `DB`**: `Model.where/create/get/update/delete/count/paginate`
  and `DB.session()/transaction()` over SQLModel, with ambient transactions.
- **Laravel-style superclasses & primitives**: a generic `Repository` base
  (`RepositoryQuery` + CRUD for free) with a declarative `Repositories`
  `repositories` map; a fluent `Schedule` builder
  (`app.schedule("t").every_minute()`); `Notification` + `Notifier` with
  `log`/`conversation`/`telegram` channels and `app.notify(...)`; `Job` +
  `app.dispatch(...)`; `Cache` and `Storage` facades (`CacheStore`, `Filesystem`);
  `Rule`/`validate`; and `Listener`/`Middleware` base classes. `agentkit new`
  now generates a Laravel-style flat `app/` package (models, repositories,
  providers, tools) instead of a nested project package.
- **Laravel parity, round two**: a durable, database-backed **queue**
  (`QUEUE_ENABLED`, `app.dispatch` queues when enabled, `agentkit queue:work` /
  `queue:failed` / `queue:retry` / `queue:flush`, retries + failures); provider
  `bindings`/`singletons` maps and **deferred providers** (`DeferrableProvider`);
  container **autowiring** (`make`/`build`/`resolve`); **global helpers**
  (`app`, `config`, `env`, `dispatch`, `event`, `notify`, `cache`, `storage`,
  `queue`, `logger`, `report`, `resolve`); Eloquent-style `Model.first_or_create`
  / `update_or_create` / `find_or_fail` (with automatic `owner_id`); fluent
  schedule extras (`timezone`, `description`, `without_overlapping`,
  `on_one_server`, `run_in_background`); `agentkit schedule:run`; and a full,
  explorable Laravel-style project template (`app/Providers`, `Console/Kernel`,
  `Jobs`, `Events`, `Listeners`, `Notifications`, `Policies`, `Rules`, `Services`,
  `Repositories`, `Models`, `Middleware`, `Tools`, `Agents`).
- **Skills** (`agentkit.skills`): discoverable `SKILL.md` folders with YAML front
  matter (`Skill`, `SkillRegistry`, `load_skill_file`, `parse_front_matter`).
  `Agent.make(...).skills()` adds a compact index to the instructions and the
  `list_skills`/`load_skill`/`read_skill_file` tools (progressive disclosure;
  path-traversal safe). Roots from `skills_dir` (or `./skills` +
  `<agent_home>/skills`); `skills_enabled` toggles them. CLI: `agentkit skills
  list` / `skills show`.
- **Streaming**: `ChatRunner.stream` / `App.stream` yield `StreamEvent`s
  (`text`, `final`); history and usage are recorded as for `run`.
- **Model routing + cost**: `ModelRouter` (`route`/`otherwise`/`with_fallbacks`)
  via `App.model_resolver`, and `Pricing`/`default_pricing` estimating per-turn
  `cost_usd` recorded on usage.
- **Context compaction**: `Compactor` — tiered (pinned facts/constraints, verbatim
  recent, folded older) with a structured rolling summary; `App.compact(...)`;
  `summarize_older`/`truncating_processor` kept as simple alternatives.
- **Knowledge (RAG)**: `KnowledgeBase` indexes chunked sources with embeddings and
  exposes a `search_knowledge` tool via `Agent.make(...).knowledge(...)`; CLI
  `agentkit knowledge add|add-text|search|list`.
- **Capability shortcuts**: builder pass-throughs `.web_search()`, `.web_fetch()`,
  `.x_search()`, `.thinking()`, `.caching()`, `.tool_search()`,
  `.image_generation()`, `.instrumentation()`, `.native_tool()`.
- **Sandboxed workspace**: `Sandbox` (backed by `pydantic_ai.workspaces`) and
  `Agent.make(...).workspace(...)` adding `read_file`/`list_files`/`write_file`/
  `run_command`; skill `allowed-tools` can be enforced with `.skills(enforce=True)`.
- **Evaluations** (`agentkit.evals`): `Case`/`EvalSuite`/`Report` with output, tool
  and custom assertions; `EvalSuite.from_file` (YAML/JSON); CLI `agentkit eval`.
  Execution/reporting delegated to `pydantic_evals`.
- **Cost via `genai_prices`**: `agentkit.pricing` wraps Pydantic's `genai_prices`
  (no bundled price table); per-turn cost prefers `RunUsage.cost`, else
  `estimate_cost(...)`. `Pricing` supports overrides.
- **Human-in-the-loop**: `Clarification` + `ask_user` tool (`Agent.make(...).clarify()`)
  and `App.clarify(handler)`; `App.resume(deferred_tool_results)`; `.output_validator(fn)`.
- **Planning / graphs / teams**: `Planner` (plan-and-execute), `StateGraph` (async
  state machine with conditional edges), `Supervisor` and `spawn_tool`/`team_tools`.
- **Tooling**: per-tool `retries`/`timeout`/`sequential`/`defer_loading`, `cached_tool`
  (TTL result cache) and `.toolset(...)`.
- **Safety**: PII `scan_pii`/`redact_pii`, `ModerationPolicy` +
  `moderation_middleware`/`moderation_hooks`, and `Feedback` (repo + facade).
- **Ops**: `PromptRegistry` (file-backed, versioned prompts + `.prompt(...)`),
  `Budget`/`check_budget` with `App.budget(...)`, and conversation branching
  (`ConversationRepo.fork`, `App.fork`, `App.replay`).
- **Multimodal + audio**: `image`/`audio`/`document`/`content` content-part helpers,
  generated-media artifacts, and `transcribe`/`synthesize` (OpenAI audio).
- **Compaction** now estimates tokens with `tiktoken` when available.
- **Workspace layout**: agents now live under `workspace_root` (default
  `~/.agentkit`), with `agent_home` defaulting to `workspace_root/<agent_name>`
  (`AGENTKIT_HOME` / `AGENT_HOME` still override). `agentkit.workspace` detects
  legacy `~/.local/share/...` data and migrates it (`detect_legacy`, `migrate`).
- **Operator web UI** (`agentkit.webui`): an in-core FastAPI app served by the
  agent process that inspects conversations/chat, usage, audit, A2A tasks and
  durable workflows, and manages schedules, workflows, SOUL and config — for the
  hosting agent only. `run_all(...)` auto-appends it, so every agent gets it.
- **Web SPA** (`web/`): Vite + React + TypeScript + Tailwind + shadcn/ui
  console (Overview, Chat, Conversations, Scheduler, Workflows, Usage, Audit,
  A2A, Persona, Config, Artifacts), built into `agentkit/webui/static`.
- **CLI**: `agentkit` console script with `webui`/`api` and
  `workspace list|migrate` commands.
- Repo helpers: `ConversationRepo.list/get`, `UsageRepo.list`,
  `ScheduledJobRepo.set_enabled`, `scheduler.ensure_configured`/`set_enabled`.

### Changed
- `AgentSettings.ensure_dirs()` also creates `logs/`.
- `AgentApp` is now a deprecated shim over `App` (same `build`/`run`/`deps`/
  `repositories` surface); `ChatRunner.send` now emits `turn.start`/`turn.end`/
  `channel.message` and `approval_handler` emits `approval.asked`.

## [0.1.0] - 2026-10-11

### Added
- **Config & resilience**: `AgentSettings`, `build_model` (timeout + SDK
  retries), `model_settings`, `usage_limits`.
- **Agents**: `Orchestrator` (specialist delegation), `Deps`, HITL `approvals`
  (deferred tools), `ChatRunner` with durable history.
- **Persistence**: libSQL/SQLModel runtime, `Repositories` (conversations,
  messages, A2A tasks, scheduled jobs, usage, audit), engine with WAL + a
  single-writer lock, Alembic helper.
- **Durability**: DBOS workflows/queues, `durability.init(queues=…)`,
  `failed_workflows` dead-letter view.
- **Scheduler**: durable cron **and one-off** jobs (`scheduler.task`,
  `schedule_cron`, `schedule_once`, `list_jobs`, `remove_job`).
- **MCP**: prefixed `MCPRegistry` client + `serve_mcp`.
- **A2A**: task-based `TaskAgentExecutor` + `build_a2a_app` + durable
  `SQLAlchemyTaskStore` + outbound `A2AClient`.
- **Gateways**: Telegram markdown rendering + `ApprovalBroker`, CLI helpers.
- **Observability**: OpenTelemetry export (console / OTLP) with **no hosted
  account**; structured logging with correlation ids and redaction.
- **Safety**: prompt-injection scanning, untrusted-data wrapping, secret/amount
  redaction, egress (SSRF) checks, `ToolPolicy` RBAC/approval policy,
  hash-chained audit log.
- **Ops**: error taxonomy, health/readiness routes, graceful shutdown,
  `AgentApp` facade.

[Unreleased]: https://github.com/kakalition/agentkit/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/kakalition/agentkit/releases/tag/v0.1.0
