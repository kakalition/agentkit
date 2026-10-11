# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
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
