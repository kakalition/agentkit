# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased] — full-stack agent

### Added
- **Contracts + drivers substrate** (`agentkit.contracts`, `agentkit.support`):
  the Laravel-style `contract → driver → registry → extend()` shape applied across
  the framework. Contracts are runtime-checkable Protocols; `agentkit.support.Manager`
  resolves a settings-selected driver per subsystem and caches it as a singleton;
  `agentkit.support.drivers` is a global `(kind, name)` registry with a
  `@register_driver(kind, name)` decorator; `App.manager(kind)`,
  `App.extend(kind, name, factory)` and `App.drivers()` expose it. Kinds and
  built-in driver names are typed `StrEnum`s (`agentkit.support.kinds`:
  `DriverKind`, `CacheDriver`, `EmbeddingsDriver`, …) rather than bare strings,
  and every `<subsystem>_driver` setting is typed with its enum, so an invalid
  value is rejected at settings load. The container
  gains tagged (`tag`/`tagged`) and contextual (`when().needs().give()`) bindings.
  Conversion for every subsystem (existing class = default driver): cache, prompts,
  embeddings, memory + recall strategy, RAG (chunker/retriever/reranker), storage
  (with `edit_file`/`glob`/`grep` + `CompositeFileSystem`), queue, scheduler,
  durability, database dialect, observability, pricing, rate limiting, auth, vault,
  guardrails, ingest, audio, learning (extractor/strategy/sink), comms topologies,
  tasks + planning, subagent context strategies, agent middleware, graph executors,
  code executors, eval reporters, chat channels + notification channels, and the
  first-class `CommsContext` on `Deps`. `inspect`/`/api/info` report the active
  driver per kind; `/guide/drivers` documents them; conformance suites live under
  `tests/contracts`.
- **New capabilities** in the same contract+driver shape: an in-loop **todo store**
  with `write_todos`/`read_todos`/`add_todo`/`update_todo`/`clear_todos`
  (`agentkit.tasks`), **subagents** with `isolated`/`shared`/`summarized` context
  strategies and a `task(subagent, prompt)` tool (`agentkit.agents.subagent`),
  **agent middleware** for model/tool hooks (`agentkit.foundation.agent_middleware`),
  **graph executors** (`sequential`/`parallel`/`checkpointed`, `agentkit.graph`),
  **code execution** with an approval-gated `run_code` tool (`agentkit.executors`),
  **eval reporters** + `assert_trajectory` (`agentkit.evals`), and **comms
  topologies** (`agentkit.comms`) with `round_robin`/`moderator`/`all` groupchat
  speaker strategies. `.full()` gains `todos` (on) and `code` (off) layers. The
  workspace layer gains `edit_file`/`glob`/`grep` agent tools. The **scaffold**
  (`agentkit new`) ships a `app/Providers/DriverServiceProvider.py` showing
  `app.extend(DriverKind.X, …)`, a `# -- Drivers --` block in `.env.example`
  (typed `<X>_DRIVER` settings), and a "Swapping a driver" README section.

### Changed
- **Self-learning is now review-gated by default** (`learning_require_review=true`):
  learned lessons are stored `proposed` and do not affect turns until approved (or an
  eval gate passes). Auto-apply is an explicit opt-in; `learning_strategy=none` keeps
  a deterministic agent. `reflect()` now reads settings by default.

### Added
- **Opt-in authentication & RBAC** (`agentkit.security`): a framework-neutral
  `Actor` (owner + subject + roles + method) that becomes the tenant key for every
  repository and `Deps`. Auth is off by default and byte-for-byte compatible with
  the local single-operator behavior; when enabled it is fail-closed. A single
  `Authenticator` composes static/env API keys, DB-backed hashed keys, and
  JWT/OIDC (JWKS with cached keys + rotation refetch). Wired into the web UI
  middleware (`/api/*` gated, `/api/whoami`, `?access_token=` for SSE), the A2A
  Starlette app (JSON-RPC gated, agent card public), and FastMCP HTTP transports.
  `ToolPolicy.require_roles` + `policy_hooks` enforce per-tool roles (fail-closed);
  audit writes carry the actor label. New: `agentkit auth:key create|list|revoke`,
  `agentkit auth:whoami`, the `api_keys` table/`APIKeyRepo`, `AUTH_*` settings, and
  `/guide/authentication`. `App.repositories(owner_id=...)`, `App.deps(actor=...)`,
  `App.run/stream/resume(actor=...)` and `repositories(runtime, owner_id=...)`
  thread the actor explicitly.
- **Product UX**: `App.stream` over SSE (`POST /api/chat/stream`) and cancellation
  (`App.cancel`/`App.running`, `POST /api/chat/cancel`); an in-process
  `ApprovalQueue` (`APPROVAL_UI_ENABLED`, `/api/approvals`) so a UI can decide
  deferred approvals; a lesson-review inbox in the web console (`/lessons`,
  `/api/lessons`); and token entry / actor display. Streaming/cancel/approval docs.
- **Ops & scale** (`agentkit.metrics`, `agentkit.cli`): Prometheus metrics
  (turns/latency, tool errors, queue depth, scheduler runs, cost) exposed at
  `METRICS_PATH` when `METRICS_ENABLED`; turn/queue/scheduler instrumentation.
  `agentkit migrate` (non-destructive `init_db`), `db:backup`/`db:restore`
  (SQLite `VACUUM INTO`), and `health`. Per-dependency readiness
  (`readiness_checks`: db + optional queue/vault) behind `/api/health` and
  `/readyz`. An optional Postgres engine path (`DATABASE_URL=postgresql://…`,
  `asyncpg`). Dockerfile + docker-compose (app + worker, one scheduler leader)
  and a deployment/runbook doc.
- **OpenAI-compatible API**: `GET /v1/models` and `POST /v1/chat/completions`
  (streaming SSE + JSON) mapped to `App.answer`, gated by `OPENAI_API_ENABLED`,
  authenticated via the Phase 1 `Authenticator`, with usage recorded. Web UI gains
  `webui/openai_api.py`; docs `/guide/openai-api`.
- **Outbound webhooks** (`agentkit.webhooks`): opt-in `Webhook`/`WebhookDelivery`
  tables and a `WebhookDispatcher` that subscribes to the event bus, POSTs
  HMAC-SHA256-signed JSON, retries with bounded backoff, and logs every attempt.
  `FullStackProvider` wires it when `WEBHOOKS_ENABLED`; CLI `webhook add|list|delete`.
- **OpenAPI→tools loader** (`agentkit.tools_from_openapi`): compile an OpenAPI
  document into agent tools (`tools_from_openapi`, `register_openapi_tools`).
- **Presets/blueprints**: `agentkit new --preset support|research|ops` overlays the
  full-stack scaffold with a composed blueprint (instructions + knowledge + eval
  suite).
- **Learning review & eval-driven learning**: `Memory.status`
  (`active`/`proposed`/`rejected`, existing rows default `active`) plus
  `LEARNING_REQUIRE_REVIEW` to hold lessons as `proposed` until approved. Only
  `active` rows appear in listings/search/digest/distillation; the review inbox
  is available in the CLI (`learning:review approve|reject`, `learning:lessons
  --status`) and the API (`/api/lessons`, approve/reject). `agentkit.evals.
  capture_turns` / `load_captured` distil real turns into stored regression cases
  (`evals_capture` table) with `eval:capture`/`eval:gate`; `LEARNING_EVAL_GATE`
  reports the post-reflect gate intent.
- **Data lifecycle** (`agentkit.data`): `export_owner` produces a JSON bundle and
  `forget_owner` erases an owner's data (dry-run by default), keeping audit
  entries and appending a `data.forget` tombstone so the hash chain stays
  verifiable. CLI `data:export`/`data:forget --yes`; API `GET /api/data/export`
  and `POST /api/data/forget?confirm=true` (gated by `DATA_EXPORT_ENABLED` /
  `DATA_FORGET_ENABLED`).
- **Ingestion** (`agentkit.ingest`): `extract_text` (txt/md/csv/json, HTML via
  `beautifulsoup4`, PDF via `pypdf`, DOCX via `python-docx`) and `fetch_url`
  (httpx, SSRF/scheme/size guarded). `KnowledgeBase.add_file` now parses document
  formats and gains `add_url`; CLI `knowledge:add-file` / `knowledge:add-url`.
  Guards `INGEST_MAX_BYTES` / `INGEST_ALLOWED_SCHEMES`.
- **Rate limiting** (`agentkit.ratelimit`): an opt-in, database-backed fixed-window
  limiter (`rate_windows` table, keyed `(owner_id, key, window_start)`, works on
  SQLite + Postgres) with an in-process cache. Enforced at the web UI's HTTP
  boundary (429 + `Retry-After`, keyed on the resolved actor); `RateLimiter` is
  reusable for per-tool caps. Settings `RATE_LIMIT_ENABLED`,
  `RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_BURST`, `RATE_LIMIT_TOOL_PER_MINUTE`; the
  stack view reports the state.
- **Credential vault** (`agentkit.security.credentials`): opt-in Fernet
  encryption of channel/provider secrets at rest in a new `credentials` table
  (`CredentialRepo`). `Credentials` exposes `set/get/names/delete` and encrypts
  everything; `hydrate_credentials` loads vault secrets into settings at boot
  (vault first, environment fallback) so channels pick them up transparently.
  `Deps.credentials` / `App.credentials` expose the vault to tools. Refuses to
  operate without `AGENTKIT_CREDENTIALS_KEY`; `credentials:set|list|delete` CLI
  never echoes values; the key is masked in `/api/config` and only the enabled
  flag is reported in the stack view.
- **`Agent.full()`** — expand a builder to the whole agent stack in one call
  (persona + typed memory + skills + HITL approvals + safety policy + optional
  knowledge/workspace/peer tools). Every layer is toggleable and idempotent, and
  respects the `memory_enabled`/`skills_enabled`/`approvals_enabled`/
  `subagents_enabled` settings flags (a disabled layer is skipped silently).
- **`FullStackProvider`** (`App(...).fullstack()`) — boot the full stack from
  settings/config: per-concern config sections (`memory`, `learning`, `channels`,
  `interop`, `queue`), the daily durable `memory:consolidate` and
  `learning:reflect` schedules, and gateway channels registered only when their
  token/env is present. Unconfigured layers stay idle and never raise.
- **Native agent tools** (`agentkit.toolkits`): every capability as first-class,
  agent-callable tools — `database` (`db_*` CRUD), `scheduler` (`schedule_*`),
  `queue` (`enqueue_*`, `RunRegisteredTask`), `notifications` (`notify*`),
  `history`, `usage`, `knowledge_admin` (`index/replace/forget_document`), and
  `skills_admin` (`save_skill`/`update_skill`). Attached per capability or via
  `Agent.native()`/`Agent.full()`; safe by default (deny-by-default allow-lists,
  owner scoping, audited writes) with every mutating tool registered
  `requires_approval=True`. Builder methods and `App.models`/`agent_tasks`/
  `agent_jobs` record the allow-lists; `agentkit inspect` / `/api/info` report the
  enabled toolkits and exposed models/tasks/jobs. Per-toolkit settings flags
  (`db_tools_enabled`, `scheduler_tools_enabled`, `queue_tools_enabled`,
  `notification_tools_enabled`, `history_tools_enabled`, `usage_tools_enabled`,
  `knowledge_admin_enabled`, `skill_authoring_enabled`) plus
  `agentkit.policy.NATIVE_TOOLS_POLICY`.
- **Self-learning** (`agentkit.learning`): a closed **reflect → learn → apply**
  loop. `reflect(repos, ...)` distils lessons/preferences/facts from a conversation
  window (model JSON extraction with an offline heuristic fallback), is idempotent
  per conversation + window via a `learning_runs` table, and redacts PII/secrets
  before storage. Lessons are `procedural` memories (deduped via
  `near_duplicates`/`merge`), preferences merge into the owner profile, and
  `lessons_digest` is injected into the instructions by `.learning()`/`.full()`.
  Tools `learn`/`reflect`/`list_lessons`/`forget_lesson`; recurring lessons distil
  into a `SKILL.md` (`learning_skill_threshold`/`learning_auto_skills`);
  `learning:reflect` is a durable scheduler task registered + scheduled by
  `FullStackProvider`; CLI `learning:reflect|lessons|forget`; settings
  `learning_enabled`/`learning_reflect_cron`/`learning_window`/
  `learning_skill_threshold`/`learning_auto_skills`/`learning_max_lessons`.
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
