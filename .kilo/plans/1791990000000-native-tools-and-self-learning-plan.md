# Native Agent Tools + Self-Learning — Plan

## Goal

Make **every agentkit capability first-class and agent-callable out of the box**
(database, scheduling, queue, notifications, history, usage/audit, knowledge writes,
skill authoring, self-learning), and add a real **self-learning mechanism** (a
closed reflect → learn → apply loop) — both opt-in-able in one call via
`Agent.make(...).full()` and `App(...).fullstack()`, safe by default, async-first,
and documented Laravel-style.

## Current state (audit)

Agent-callable today:

| Capability | Tools present |
| --- | --- |
| Memory | `remember`, `remember_person`, `recall`, `forget_memory`, `update_profile`, `get_profile` |
| Knowledge | `search_knowledge` (read only) |
| Skills | `list_skills`, `load_skill`, `read_skill_file` |
| Workspace | `read_file`, `list_files`, `write_file`, `run_command` |
| Peer agents | `send_to`, `ask_agent`, `broadcast`, `list_agents`, `handoff_to` |
| HITL | `ask_user` |
| Web/capabilities | PydanticAI `web_search`/`web_fetch`/`sandbox`/… |

**Missing (not agent-callable):** database/`Model`/`Repository` CRUD, scheduler,
queue, notifications, conversation history, usage/audit, knowledge writes, skill
authoring, evals. **Self-learning:** none.

Grounding facts: `Deps(repos, settings, model, extras, clock)`; `Repositories` has a
`repositories: ClassVar[dict[str, type]]` of domain repos; `ToolPolicy`/
`default_policy()` gate approvals; `scheduler.TASKS` is the named-callable registry
(`scheduler.task`, `invoke_task`, `schedule_cron/once`, `list_jobs`, `set_enabled`,
`remove_job`); `Queue`/`Job`/`serialize_job`; `Notifier`/`Notification`;
`Memory(kind∈{fact,preference,person,date,episodic,procedural})`, `memory_digest`,
`consolidate_memories`, `register_consolidate_task`; `SkillRegistry` (writeable
`roots`) + `Skill`/front-matter; `KnowledgeRepo.add/replace/clear/search`;
`FeedbackRepo`, `UsageRepo`, `AuditRepo`, `ConversationRepo`, `MessageRepo`;
`Dispatcher` events; `FullStackProvider`; `Agent.full()`; `_sync.run_sync` for sync
seams.

---

## Part A — Native tools: everything is agent-callable

### A1. Toolkit architecture

New package `src/agentkit/toolkits/` — one module per capability, each exposing
`<name>_tools(deps_source) -> list[callable]` plus an `attach_<name>(agent, …)`:

- `toolkits/__init__.py` — `TOOLKITS` registry + `attach_toolkits(agent, *, enabled, models, tasks, jobs) -> set[str]`.
- Tools read the live run context (`ctx.deps.repos`, `ctx.deps.settings`,
  `ctx.deps.extras["app"]`) so they always see the current session/owner.

Builder + app surface:

- `Agent.database(models=…)`, `.scheduler(tasks=…)`, `.queue(jobs=…)`,
  `.notifications()`, `.history()`, `.usage()`, `.knowledge_admin()`,
  `.skill_authoring()` — each appends the toolkit's tools (idempotent).
- `.full()` gains a `native=True` layer that attaches all toolkits whose settings
  flags are on (see A6). A single `.native(...)` alias attaches the enabled set.
- `App.models({...})`, `App.agent_tasks([...])`, `App.agent_jobs({...})` record the
  allow-lists the toolkits read (so the app, not the model, decides what's reachable).
- Introspection: `agentkit inspect` and `/api/info` list attached toolkits + the
  exposed models/tasks/jobs.

### A2. Database toolkit (`toolkits/database.py`)

Agent CRUD over an explicit, owner-scoped, allow-listed set of models.

- Input: `models: dict[str, type[Model] | type[Repository]]` (name → model/repo).
  Nothing is exposed unless named.
- Read tools (always on when the toolkit is on): `db_list_models`,
  `db_describe(model)` (columns + types for the schema), `db_find(model, filters={},
  limit=20)`, `db_get(model, id)`, `db_count(model, filters={})`.
- Write tools (approval-gated): `db_create(model, values)`, `db_update(model, id,
  values)`, `db_delete(model, id)`.
- Safety: owner scoping via the repository; `values` validated against the SQLModel
  schema (reject unknown fields); writes emit the `audit` entry and `db.*` events;
  paging caps; no raw SQL; no cross-owner reads.

### A3. Scheduler + queue toolkits

- `toolkits/scheduler.py`: `schedule_task(name, *, cron=None, at=None, task, args={})`
  (approval), `list_schedules`, `get_schedule`, `cancel_schedule`,
  `run_schedule_now` (approval). Tasks restricted to the app's `agent_tasks`
  allow-list; cron validated by `croniter`; async wrappers over `scheduler.*`.
- `toolkits/queue.py`: `enqueue_task(task, args={}, delay=0, queue=None)` (approval),
  `queue_status(queue=None)`, `list_failed_jobs`, `retry_job(id)`. Uses the existing
  `Queue`/`Job` machinery with a new `RunRegisteredTask` job that invokes
  `scheduler.invoke_task(name, args)` so one allow-list covers both.

### A4. Notifications, history, usage/audit toolkits

- `toolkits/notifications.py`: `notify(text, channels=["conversation"])` (approval),
  `notify_me(text)` (to the current conversation). Built on `Notifier` (sync seam via
  `run_sync`, already handled).
- `toolkits/history.py`: `list_conversations(limit)`, `search_history(query)`,
  `read_conversation(id, limit)` — owner-scoped reads.
- `toolkits/usage.py`: `usage_summary(window="all")`, `audit_trail(limit)`,
  `verify_audit()` — read-only.

### A5. Knowledge-write + skill-authoring toolkits

- `toolkits/knowledge_admin.py`: `index_document(text, source)`,
  `replace_document(source, text)` (approval), `forget_document(source)` (approval),
  `list_documents()`.
- `toolkits/skills_admin.py`: `save_skill(name, description, body, allowed_tools=[])`
  and `update_skill(name, body)` → write a valid `SKILL.md` into
  `SkillRegistry.roots[0]` (approval), then `registry.discover(reload=True)`.

### A6. Safety, policy, and config

- Extend `default_policy()` / add `agentkit.policy.NATIVE_TOOLS_POLICY` requiring
  approval for: `db_create`, `db_update`, `db_delete`, `schedule_task`,
  `run_schedule_now`, `enqueue_task`, `notify`, `replace_document`,
  `forget_document`, `save_skill`, `update_skill`.
- New settings (all default-safe, `.full()`/`fullstack()` respect them):
  `db_tools_enabled`, `scheduler_tools_enabled`, `queue_tools_enabled`,
  `notification_tools_enabled`, `history_tools_enabled`, `usage_tools_enabled`,
  `knowledge_admin_enabled`, `skill_authoring_enabled`.
- Deny-by-default: no model/task/job reachable unless the app allow-lists it; writes
  require approval; everything owner-scoped and audit-logged.

### A7. Tests (Part A)

`tests/toolkits/`: `test_database_tools.py` (allow-list, owner scoping, validation,
approval flags, no cross-owner), `test_scheduler_tools.py`, `test_queue_tools.py`,
`test_notification_tools.py`, `test_history_tools.py`, `test_usage_tools.py`,
`test_knowledge_admin.py`, `test_skills_admin.py`; plus an integration test that
`.full()` attaches the enabled toolkits and `inspect`/`/api/info` report them.

---

## Part B — Self-learning mechanism

New module `src/agentkit/learning.py` implementing a closed **reflect → learn →
apply** loop, native (agent-callable) and durable (scheduled).

### B1. Signals (event-driven, non-blocking)

A `LearningSignals` collector subscribes to the `Dispatcher` and `FeedbackRepo`:
`turn.end`, `agent.error`, tool failures/retries, budget exceedances, deferrals,
compactions, and explicit user feedback/ratings; it also reads recent turns
(`ConversationRepo`/`MessageRepo`) and the `Compactor` summary. Signals are cheap,
bounded (ring buffer), and redacted (reuse `guardrails.redact_pii`).

### B2. Reflection engine

`async def reflect(repos, *, model=None, conversation_id=None, window=20, dry_run=False)`
→ extracts **lessons** (procedural: "when X, do Y"), **preferences**, **facts**, and
**skill candidates** from the signals with a model (mirrors `Compactor._model_extract`;
JSON schema enforced; offline heuristic fallback). Idempotent per conversation+window
via a `learning_runs` table (evidence + counts), so re-running is cheap.

- Tool `reflect(...)` — the agent can learn immediately after a task.
- Durable task `learning:reflect` (`scheduler.task`) registered by
  `FullStackProvider` and scheduled (default daily, `learning_reflect_cron`).
- CLI `agentkit learning:reflect [--conversation id] [--dry-run]`.

### B3. Storage & application

- Lessons stored as `Memory(kind="procedural")` (procedural already exists) with
  `source_conversation_id`, `importance` from evidence, and dedupe via
  `near_duplicates`/`merge`. Preferences merge into `OwnerProfile`; facts into memory.
- **Application:** a new `lessons_digest(repos)` block (like `memory_digest` but
  procedural/first-person guidance, capped, importance-ranked) injected into
  instructions by `.learning()`/`.full()`, so learned behavior changes future turns.
- **Skill distillation:** when the same lesson recurs ≥ `learning_skill_threshold`
  times (embedding similarity), synthesize a `SKILL.md` into the skills dir
  (reusing A5's `save_skill`); approval-gated or threshold-gated via
  `learning_auto_skills`.
- Events: `learning.reflected`, `learning.lesson`, `learning.skill`.

### B4. Consolidation, decay, guardrails

- `memory:consolidate` continues to dedupe/summarize/prune; learning feeds it and
  adds lesson-specific decay (unused low-importance lessons fade).
- Guardrails: `learning_enabled` flag, max lessons/window, reflection rate-limit,
  PII redaction before storage, never learn credentials/secrets, importance decay,
  and `--dry-run` everywhere. Learning is transparent (CLI + `/api/info` state).

### B5. Tools, CLI, wiring

- Tools attached by `.learning()` / `.full()`: `learn(insight, kind="lesson")`,
  `reflect()`, `list_lessons()`, `forget_lesson(id)`.
- CLI: `learning:reflect`, `learning:lessons`, `learning:forget`.
- `FullStackProvider.boot` registers `learning:reflect` (schedule) when
  `learning_enabled`; settings: `learning_enabled` (default true), 
  `learning_reflect_cron` (`0 4 * * *`), `learning_skill_threshold`, 
  `learning_auto_skills` (false), `learning_max_lessons`.

### B6. Tests (Part B)

`tests/test_learning.py`: reflect extracts lessons/preferences/facts (stub model),
idempotency via `learning_runs`, dedupe/decay, PII redaction, `learning_enabled`
off disables tools+task, `learn`/`list_lessons`/`forget_lesson` tools, skill
distillation threshold, `learning:reflect` durable-task registration + schedule,
CLI commands, and `lessons_digest` appearing in built instructions.

---

## Part C — Wiring

- `Agent.full()` gains `native=True` and `learning=True` layers (settings-aware),
  both idempotent; `.full()` never double-registers (existing layer guard).
- `FullStackProvider`: schedules `learning:reflect` alongside `memory:consolidate`;
  fails gracefully when unconfigured.
- Scaffold: full project shows `.database({...}).scheduler([...]).learning()`
  (commented allow-lists) and a `config/learning.py` section; keep the generated
  project booting (subprocess smoke test).
- `App.models/agent_tasks/agent_jobs` recorded and surfaced by `inspect`/`/api/info`.

## Part D — Docs (Laravel style)

- New `docs/guide/native-tools.md` (title → `## Introduction` → sections + `::: tip`/
  `::: warning` callouts) covering every toolkit, safety, and the allow-lists.
- New `docs/guide/self-learning.md` (the reflect→learn→apply loop, guardrails,
  CLI, scheduling).
- Update `docs/guide/async.md`-adjacent guides: `agents.md` (builder methods),
  `fullstack.md` (new layers/flags), `memory.md` (lessons), `skills.md`
  (authoring/distillation), `scheduling.md`, `jobs.md`, `facades.md`;
  `docs/.vitepress/config.mts` sidebar entries; README highlights + a short section;
  CHANGELOG `Added` entries.

## Workstream order

1. A1 architecture + settings + policy (no behavior change) → 2. A2–A5 toolkits →
3. A6 safety/config → 4. A7 tests → 5. B1–B5 learning → 6. B6 tests →
7. C wiring/scaffold → 8. D docs → 9. full validation.

## Risks & mitigations

- **Model misuse of write tools** → allow-lists + approvals + audit + owner scoping.
- **Self-learning drift / prompt bloat** → caps, decay, dedupe, importance ranking,
  `learning_enabled` flag, dry-run.
- **PII leakage into lessons** → redact before storage; never store secrets.
- **Naming collisions** (e.g. `queue`/`schedule` tools vs. existing) → prefix tools
  (`db_*`, `schedule_*`, `enqueue_*`, `notify*`) and check `_function_toolset` keys.
- **Sync seams** (`Notifier`, queuing) → `_sync.run_sync`, never on the loop.
- **Test/coverage** → keep ruff/mypy/pytest green and coverage ≥70%.

## Acceptance criteria

- With `Agent.make("x").full()` and `App(...).fullstack()`, an agent can natively
  read/write allow-listed DB rows, schedule/cancel tasks, enqueue jobs, notify,
  read history/usage/audit, write knowledge/skills, and **learn** — all owner-scoped,
  approval-gated for writes, and audited.
- Reflection runs durably (`learning:reflect`) and on demand (`reflect` tool/CLI);
  lessons change future behavior via the instructions digest and can distill skills.
- `agentkit inspect` / `/api/info` report toolkits, exposed models/tasks/jobs, and
  learning state; docs/README/CHANGELOG updated; ruff, mypy, pytest, coverage green.
