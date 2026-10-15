# Changelog

agentkit follows [Semantic Versioning](https://semver.org) and
[Keep a Changelog](https://keepachangelog.com).

## Unreleased

### Added

- **Contracts + drivers** (`agentkit.contracts`, `agentkit.support`) — a
  Laravel-style `contract → driver → registry → extend()` layer. Runtime-checkable
  Protocol contracts; a global `(kind, name)` registry with
  `@register_driver(kind, name)`; `Manager` + `App.manager`/`App.extend`/
  `App.drivers`; typed `StrEnum` kinds and driver names (`agentkit.support.kinds`)
  with every `<subsystem>_driver` setting validated at load. Converted: cache,
  prompts, embeddings, memory + recall, RAG (chunker/retriever/reranker), storage
  (+`edit_file`/`glob`/`grep`, `CompositeFileSystem`), queue, scheduler, durability,
  database dialect, observability, pricing, rate limits, auth, vault, guardrails,
  ingest, audio, learning, comms, channels + notification channels. `agentkit
  inspect` and `/api/info` report the active driver per kind.
- **New capabilities** in the same shape — an in-loop **task store** with
  `write_todos`/`read_todos`/`add_todo`/`update_todo`/`clear_todos`
  (`agentkit.tasks`); **subagents** with `isolated`/`shared`/`summarized` context
  strategies and a `task(subagent, prompt)` tool (`agentkit.agents.subagent`);
  **agent middleware** for model/tool hooks
  (`agentkit.foundation.agent_middleware`); **graph executors**
  (`sequential`/`parallel`/`checkpointed`, `agentkit.graph`); approval-gated
  **code execution** (`agentkit.executors`); **eval reporters** +
  `assert_trajectory` (`agentkit.evals`); **comms topologies**
  (`agentkit.comms`) with groupchat speaker strategies; and first-class
  `CommsContext` on `Deps`. `.full()` gains `todos`/`code` layers; the workspace
  layer gains `edit_file`/`glob`/`grep`.
- **Contracts & drivers docs** — `/guide/drivers`, `/guide/tasks`,
  `/guide/code-execution`, and a `DriverServiceProvider` in the `agentkit new`
  scaffold.
- **Opt-in auth & RBAC** (`agentkit.security`) — an `Actor` identity threaded
  through repos/`Deps`, a fail-closed `Authenticator` composing API keys (static
  + DB-hashed) and JWT/JWKS, web/A2A/MCP wiring, `ToolPolicy.require_roles`,
  `auth:key`/`auth:whoami` CLI, and the `api_keys` table. Off by default.
- **Product UX** — SSE streaming (`/api/chat/stream`), cancellation
  (`App.cancel`), an approval queue (`/api/approvals`), a lesson-review inbox, and
  web token entry.
- **Ops & scale** — opt-in Prometheus `/metrics`, `migrate`/`db:backup`/
  `db:restore`/`health` CLI, per-dependency readiness, an optional Postgres engine
  path, and Dockerfile/compose + runbook.
- **OpenAI-compatible API** — `/v1/models` + `/v1/chat/completions` (SSE + JSON)
  mapped to the agent (opt-in, authenticated, usage-recorded).
- **Outbound webhooks** (`agentkit.webhooks`) — signed, retried, logged event
  deliveries (`WEBHOOKS_ENABLED`, `webhook` CLI).
- **OpenAPI→tools** (`agentkit.tools_from_openapi`) and **presets**
  (`agentkit new --preset support|research|ops`).
- **Learning review & eval capture** — `Memory.status` with an approve/reject
  inbox (`LEARNING_REQUIRE_REVIEW`), plus `agentkit.evals.capture_turns` turning
  real turns into stored regression cases (`eval:capture`/`eval:gate`).
- **Data lifecycle** (`agentkit.data`) — owner export bundle + opt-in erasure
  that keeps audit tombstones (`data:export`/`data:forget`; `/api/data/*`).
- **Ingestion** (`agentkit.ingest`) — PDF/DOCX/HTML/URL text extraction for the
  knowledge base (`knowledge:add-file`/`add-url`).
- **Rate limiting** (`agentkit.ratelimit`) — opt-in database-backed fixed-window
  limiter enforcing on the web UI boundary (429 + `Retry-After`). Off by default.
- **Credential vault** (`agentkit.security.credentials`) — opt-in Fernet
  encryption of channel/provider secrets at rest, boot-time hydration (vault
  first, env fallback), `credentials:set|list|delete` CLI, and the `credentials`
  table. Off by default.
- **Framework front door** (`agentkit.foundation`) — an `App` container with
  service `Provider`s, entry-point discovery, a fluent `Agent` builder, short
  facades (`Memory`, `Schedule`, `DB`, `Events`, `Log`, `Feedback`), lifecycle
  events, a turn middleware pipeline, and an Artisan-style CLI (`serve`, `tinker`,
  `inspect`, `schedule:list`, `about`, and `make:*` generators).
- **Thin `Model` / `DB`** over SQLModel with ambient transactions.
- **Skills** (`SKILL.md` discovery), **knowledge/RAG**, **streaming**, **model
  routing** with `genai_prices` cost accounting.
- **Context compaction** (tiered, rolling, `tiktoken`-aware).
- **Human-in-the-loop** (approvals + clarification + resume).
- **Planning, state graphs, and multi-agent teams.**
- **Tooling** (per-tool options, toolsets, result caching).
- **Native agent tools** (`agentkit.toolkits`) — every capability as agent-callable
  tools (database CRUD, scheduling, queue, notifications, history, usage/audit,
  knowledge writes, skill authoring), deny-by-default allow-lists, approval-gated
  writes, owner-scoped and audited; attached via builder methods, `.native()`, or
  `Agent.full()`.
- **Self-learning** (`agentkit.learning`) — a closed reflect → learn → apply loop:
  idempotent reflection over conversation windows, procedural lessons + profile
  preferences, PII/secret redaction, an instructions digest, skill distillation,
  and the durable `learning:reflect` task (CLI `learning:reflect|lessons|forget`).
- **Safety** (moderation, PII redaction, feedback).
- **Ops** (prompt registry, budgets, conversation branching/replay).
- **Multimodal** input parts and speech (transcription/synthesis).
- **Evaluations** backed by `pydantic_evals`.

### Changed

- `AgentApp` is now a deprecated shim over `App`.
- Pricing is delegated to `genai_prices`; evaluations to `pydantic_evals`; the
  sandbox to `pydantic_ai.workspaces`.

## 0.1.0 — 2026-10-11

The initial release: config & resilience, agents (orchestrator, approvals,
`ChatRunner`), persistence (libSQL/SQLModel + repositories), durability (DBOS),
scheduler (cron + one-off), MCP, A2A, gateways (Telegram + CLI), observability
(Phoenix/OTLP), safety (injection scanning, redaction, egress, `ToolPolicy`,
hash-chained audit), and ops (error taxonomy, health routes, graceful shutdown).

---

The full, generated changelog lives in
[`CHANGELOG.md`](https://github.com/kakalition/agentkit/blob/main/CHANGELOG.md).
