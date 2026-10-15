# CONTINUATION — Native Agent Tools + Self-Learning

Source-of-truth plan: `.kilo/plans/1791990000000-native-tools-and-self-learning-plan.md`
(this file embeds the raw plan at the bottom).

Branch: `main` (uncommitted work in the working tree). Do **not** commit `.kilo/` or `kilo.json` (untracked tooling).

---

## Status at pause (2026-10-15)

Baseline at start: full `pytest` green. After the changes below:
- `uv run pytest -q` → green (existing suite + `tests/toolkits/test_database_tools.py`, `test_scheduler_tools.py`, `test_queue_tools.py`, `test_notification_tools.py`, `test_history_tools.py`, `test_usage_tools.py`).
- `uv run ruff check src tests` → clean (just re-sorted imports).
- `uv run mypy src/agentkit` → clean (139 files).
- NOT yet re-run: full `pytest` after the last new test files (they pass individually), coverage gate.

Workstream order from the plan: 1 arch+settings+policy → 2 toolkits → 3 safety/config → 4 tests → 5 learning → 6 learning tests → 7 wiring/scaffold → 8 docs → 9 validation.

---

## DONE

### A6 — Settings + policy
- `src/agentkit/config.py`: added native-toolkit flags `db_tools_enabled`, `scheduler_tools_enabled`, `queue_tools_enabled`, `notification_tools_enabled`, `history_tools_enabled`, `usage_tools_enabled`, `knowledge_admin_enabled`, `skill_authoring_enabled` (all default **True**; safety comes from empty allow-lists + approval-gated writes). Added learning flags `learning_enabled=True`, `learning_reflect_cron="0 4 * * *"`, `learning_window=20`, `learning_skill_threshold=3`, `learning_auto_skills=False`, `learning_max_lessons=50`.
- `src/agentkit/policy.py`: added `NATIVE_APPROVAL_TOOLS` (`db_create`, `db_update`, `db_delete`, `schedule_task`, `run_schedule_now`, `enqueue_task`, `notify`, `replace_document`, `forget_document`, `save_skill`, `update_skill`), `native_policy()`, `NATIVE_TOOLS_POLICY`; `default_policy()` now unions `DEFAULT_APPROVAL_TOOLS | NATIVE_APPROVAL_TOOLS`.
- IMPORTANT: `ToolPolicy.require_approval` is **informational only** — `policy_hooks` enforces `deny` only. Real approval needs the tool registered with `requires_approval=True` (PydanticAI defers it) plus `approval_capability` from `Agent.approvals()`. Writes are registered with `requires_approval=True` accordingly.

### A1 — Toolkit architecture (`src/agentkit/toolkits/`)
- `_common.py`: `app_of(ctx)` (reads `ctx.deps.extras["app"]`), `repos_of`, `settings_of`, `resolve_allow_list`, `resolve_list`, `emit_event(event, **payload)` (param is `event`, not `name`, to avoid kwarg collisions).
- `__init__.py`: `TOOLKITS` (name → settings flag), `enabled_toolkits(settings)`, `attach_toolkit(agent, name, **opts)`, `attach_toolkits(agent, *, enabled, settings, models, tasks, jobs) -> set[str]`. Exports `RunRegisteredTask`.
- `database.py` (`attach_database(agent, models)`): `db_list_models`, `db_describe`, `db_find`, `db_get`, `db_count` (reads) + `db_create`/`db_update`/`db_delete` (approval). Accepts `Model` **or** `Repository` subclasses; owner-scoped via `Repository`; validates fields against `model_fields`, rejects `owner_id`/unknown fields; audit + `db.*` events; limit cap 100.
- `scheduler.py` (`attach_scheduler(agent, tasks)`): `schedule_task` (approval; cron validated with `croniter`; task restricted to allow-list), `list_schedules`, `get_schedule`, `cancel_schedule` (disable/delete), `run_schedule_now` (approval). CRUD on `ctx.deps.repos.schedules`; runs via `scheduler.invoke_task`.
- `queue.py` (`attach_queue(agent, jobs, tasks)`): `RunRegisteredTask(Job)` (module scope, import-path serializable, `handle` awaits `scheduler.invoke_task`); `enqueue_task` (approval), `enqueue_job` (approval), `queue_status`, `list_failed_jobs`, `retry_job`. Uses `app.dispatch(...)` so `queue_enabled` semantics hold (inline when off).
- `notifications.py` (`attach_notifications`): `notify` (approval), `notify_me`. `conversation` channel writes through the **current** repos session (avoids cross-thread SQLite write when calling the sync `Notifier` mid-loop); `log` logs; other channels go through `app.notifier.channel(...)` senders.
- `history.py` (`attach_history`): `list_conversations`, `search_history` (bounded scan), `read_conversation` (owner-scoped via conversation owner check + `transcript`).
- `usage.py` (`attach_usage`): `usage_summary(window)`, `audit_trail(limit)`, `verify_audit`.
- `knowledge_admin.py` (`attach_knowledge_admin`): `index_document`, `replace_document` (approval), `forget_document` (approval), `list_documents`.
- `skills_admin.py` (`attach_skill_authoring`): `save_skill` (approval), `update_skill` (approval); writes to first `SkillRegistry` root via shared helper, re-discovers, verifies parse.

### Shared skill-writing helpers
- `src/agentkit/skills.py`: added `slugify_skill(name)`, `render_skill_file(...)` (yaml.safe_dump front matter), `write_skill_file(root, name, ...)`; exported.

### A1 builder surface (`src/agentkit/foundation/agent.py`)
- New methods: `.database(models)`, `.scheduler(tasks)`, `.queue(jobs)`, `.notifications()`, `.history()`, `.usage()`, `.knowledge_admin()`, `.skill_authoring()`, `.native(enabled=None, *, models, tasks, jobs)`, `.learning(enabled=True)`.
- State: `_native_requested`, `_native_all`, `_agent_models`, `_agent_tasks`, `_agent_jobs`, `_learning_requested`.
- `.full(...)` gained `native=True, learning=True, models, tasks, jobs` params; adds `"native"` (settings-gated via `enabled_toolkits`) and `"learning"` (only if `enabled("learning_enabled")`) layers through the existing `_full_layers` guard.
- `build()` now calls `_attach_native(built, settings)` and `_attach_learning(built, settings)` after `_attach_workspace`.
- Verified: `.full()` registers 43 tools, no name collisions.

### App surface (`src/agentkit/foundation/application.py`)
- `App.models(x)` is **overloaded**: a `Mapping` records the DB model allow-list (`_agent_models`); a callable is still an alias for `model_resolver`. Added `App.agent_tasks(tasks)` and `App.agent_jobs(jobs)`.
- `App.deps(...)` now seeds `deps.extras["app"] = self` so toolkits see app-level allow-lists.
- New state: `_agent_models`, `_agent_tasks`, `_agent_jobs`.

### Part B — Self-learning (`src/agentkit/learning.py`)
- `LESSON_TASK = "learning:reflect"`, `LESSON_KIND = "procedural"`, `LESSON_GUIDE`.
- `LearningSignals` (bounded, redacted ring buffer; `subscribe(dispatcher)`).
- `reflect(repos, *, model=None, conversation_id=None, window=None, dry_run=False, settings=None, auto_skills=None, skill_threshold=None) -> dict`: idempotent per conversation+window via `learning_runs.signature`; extracts lessons/preferences/facts (model JSON extraction mirroring `Compactor._model_extract`, offline heuristic fallback); redacts PII (`redact_pii`) + secrets (`redact`) before storage; lessons → `kind="procedural"` memories, preferences → memory + merged into `OwnerProfile.preferences`, facts → memory; `_distill` (recurring lessons → skill candidates, optional SKILL.md when `learning_auto_skills`); emits `learning.lesson` / `learning.reflected`.
- `lessons_digest(repos, *, limit=None)`: importance-ranked procedural digest.
- `attach_learning(agent, settings=None)`: tools `learn`, `reflect`, `list_lessons`, `forget_lesson` + dynamic `@agent.instructions` injecting `lessons_digest`. Helper `_reflect_for_ctx` avoids the tool-named-`reflect` shadowing bug.
- `register_reflect_task()` registers the durable `learning:reflect` task.

### Learning storage
- `src/agentkit/db/models.py`: `LearningRun` table (`learning_runs`).
- `src/agentkit/db/repositories/learning.py`: `LearningRunRepo` (plain class — MUST NOT import `agentkit.foundation.*` at module level, circular). Methods `latest`, `seen`, `record`.
- `container.py` attaches `self.learning_runs`; `repositories/__init__.py` exports `LearningRunRepo`.

### C — Wiring (partial)
- `src/agentkit/foundation/fullstack.py`: `LearningSection` (`AGENTKIT_LEARNING_`, `enabled=True`, `reflect_cron="0 4 * * *"`); `boot` calls `_register_learning` (registers + schedules `learning:reflect` when `learning_enabled`, never fatal).
- `src/agentkit/webui/introspect.py`: `stack_view(settings, app=None)` now reports `native_tools` (enabled toolkits, flags, allow-listed models/tasks/jobs) and `learning` state.
- `src/agentkit/webui/config_api.py`: `/api/info` passes `app=get_current_app()`.
- `src/agentkit/cli/commands/inspect.py`: passes `app=booted`, prints native toolkits/allow-lists/learning.
- `src/agentkit/cli/commands/learning.py`: `learning:reflect` (`--conversation`, `--window`, `--dry-run`), `learning:lessons` (`--limit`), `learning:forget <id>`; registered in `cli/commands/__init__.py`.
- `src/agentkit/__init__.py`: exports `attach_learning`, `lessons_digest`, `reflect`, `register_reflect_task`, `LearningSignals`, `LESSON_TASK`, `attach_toolkits`, `enabled_toolkits`, `TOOLKITS`, `render_skill_file`, `slugify_skill`, `write_skill_file`, `NATIVE_TOOLS_POLICY`, `NATIVE_APPROVAL_TOOLS`, `native_policy`.

### Tests written (passing)
- `tests/toolkits/__init__.py` (empty), `test_database_tools.py`, `test_scheduler_tools.py`, `test_queue_tools.py`, `test_notification_tools.py`, `test_history_tools.py`, `test_usage_tools.py`.
- `tests/test_fullstack.py`: updated `test_boot_registers_settings_list_flags` (now also disables learning) + added `test_learning_reflect_scheduled_and_registered`, `test_learning_disabled_skips_reflect`.
- Test pattern used: call tools directly via `agent._function_toolset.tools[name].function` with a `SimpleNamespace(deps=deps)` context; assert `...requires_approval is True/False` for gating.

---

## NOT DONE (next steps)

### Tests still to write
1. `tests/toolkits/test_knowledge_admin.py` — `index_document`, `list_documents`, `replace_document`, `forget_document` (approval flags).
2. `tests/toolkits/test_skills_admin.py` — point `deps.settings.skills_dir` at `tmp_path/"skills"`, call `save_skill`/`update_skill`, assert a valid `SKILL.md` is discovered and round-trips.
3. `tests/toolkits/test_integration.py` — `.full()` attaches settings-enabled toolkits; `stack_view(settings, app)` reports toolkits + allow-lists.
4. `tests/test_learning.py` — reflect extracts lessons/preferences/facts (heuristic + `FunctionModel` stub for `_model_extract`), idempotency via `learning_runs`, dedupe, PII redaction, `learning_enabled` off disables tools, `learn`/`list_lessons`/`forget_lesson` tools, skill distillation threshold (`_distill` runs before dedupe so identical lessons group), `learning:reflect` task registration + scheduling, CLI commands, `lessons_digest` in built instructions.

### C — Scaffold (must keep `tests/test_foundation_scaffold.py` subprocess boot green)
- `src/agentkit/foundation/scaffold/full.py`: add `config/learning.py` section; show `.database({...}).scheduler([...]).learning()` (commented allow-lists) in `app/Agents/assistant.py`; update README/env tables for native toolkits + learning.
- Add any new files to `EXPECTED` in `tests/test_foundation_scaffold.py` if new scaffolding files are added.

### D — Docs (Laravel style: `# Title` → `## Introduction` → sections + `::: tip`/`::: warning`)
- New `docs/guide/native-tools.md` (every toolkit, safety, allow-lists).
- New `docs/guide/self-learning.md` (reflect→learn→apply, guardrails, CLI, scheduling).
- Update: `agents.md`, `fullstack.md`, `memory.md`, `skills.md`, `scheduling.md`, `jobs.md`, `facades.md`.
- `docs/.vitepress/config.mts` sidebar entries; `README.md` highlights; `CHANGELOG.md` `## [Unreleased]` Added entries.
- Optional verify: `npm run build` in `docs/` (node_modules present).

### Final validation
- `uv run ruff check src tests`
- `uv run mypy src/agentkit`
- `uv run pytest` (coverage gate ≥70%; was ~79.5%)

---

## Gotchas / decisions to remember
- Approval is registration-based (`requires_approval=True`) + `approval_capability`; policy `require_approval` alone does nothing at runtime.
- `db/repositories/learning.py` is a plain repo class (importing `agentkit.foundation.repository` there caused a circular import).
- `attach_learning`'s tool named `reflect` would shadow the module function → use `_reflect_for_ctx`.
- In `reflect`, `_distill` must run **before** `_dedupe_lessons` (merging identical lessons destroys the recurrence signal).
- `attach_queue` needs the task allow-list too (`attach_toolkits` passes `tasks` to it) — `enqueue_task` checks it.
- `App.models` is overloaded (Mapping = allow-list, callable = resolver).
- `notify` (conversation channel) writes via current repos, not the sync `Notifier`, to avoid a worker-thread SQLite write while the turn's session is open.
- `run_sync` offloads to a thread when a loop is running; don't call `asyncio.run` from async code.

---

# RAW PLAN (verbatim)

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
