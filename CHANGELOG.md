# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
