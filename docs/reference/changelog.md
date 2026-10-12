# Changelog

agentkit follows [Semantic Versioning](https://semver.org) and
[Keep a Changelog](https://keepachangelog.com).

## Unreleased

### Added

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
