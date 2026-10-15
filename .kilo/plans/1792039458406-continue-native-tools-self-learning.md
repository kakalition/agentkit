# Continue — Native Agent Tools + Self-Learning (remaining work)

Source of truth: `CONTINUATION.md` (repo root) and `.kilo/plans/1791990000000-native-tools-and-self-learning-plan.md`.
Scope of this plan: finish the work listed under **NOT DONE** in `CONTINUATION.md`. Parts A (toolkits), B (learning module), and most of C (wiring) are already implemented and committed (`5f17548`).

## Verified current state

- Toolkits exist: `src/agentkit/toolkits/{_common,database,scheduler,queue,notifications,history,usage,knowledge_admin,skills_admin,__init__}.py`.
- Learning module exists: `src/agentkit/learning.py`; storage `LearningRun`/`LearningRunRepo`; `FullStackProvider._register_learning` schedules `learning:reflect`; `stack_view` reports `native_tools` + `learning`; `agentkit learning:*` CLI commands exist and are registered.
- Builder surface exists: `Agent.{database,scheduler,queue,notifications,history,usage,knowledge_admin,skill_authoring,native,learning}` and `App.{models,agent_tasks,agent_jobs}`.
- Existing toolkit tests (passing): `tests/toolkits/test_{database,scheduler,queue,notification,history,usage}_tools.py`.
- `repos.knowledge` is the DB `KnowledgeRepo` (`add(source, contents)`, `replace(source, contents)`, `clear(source)`, `sources()`, `count(source)`) — matches `knowledge_admin.py`.
- Settings are mutable (not frozen); `AgentSettings` has `skills_dir`, all native-toolkit flags and learning flags (all default `True` except `learning_auto_skills=False`).

Remaining gaps are exactly: 4 missing test files, scaffold updates, docs, and final validation. No production logic is known to be missing, but the new tests may surface bugs (fix those as part of the run).

## Task 1 — Toolkit tests

Reuse the established pattern (`tests/toolkits/test_database_tools.py`): build a real agent via `Agent.make(...).<toolkit>(...).output(str).build()`, fetch tools with `agent._function_toolset.tools[name].function`, call with `SimpleNamespace(deps=deps)`; assert `...requires_approval` for gating. Fixtures `repos`/`deps` come from `tests/conftest.py`.

1. `tests/toolkits/test_knowledge_admin.py` (`attach_knowledge_admin` / `Agent.make(...).knowledge_admin()`):
   - approval: `replace_document`/`forget_document` `True`; `index_document`/`list_documents` `False`.
   - `index_document(ctx, "text", "src")` → `list_documents` JSON contains `src` with chunk count; `replace_document` changes chunk count; `forget_document` removes it; `list_documents` then reports none.
2. `tests/toolkits/test_skills_admin.py` (`attach_skill_authoring` / `.skill_authoring()`):
   - Point `deps.settings.skills_dir` at `str(tmp_path / "skills")`.
   - approval: `save_skill`/`update_skill` both `True`.
   - `save_skill(ctx, "My New Skill", "desc", "body here")` writes `skills/my-new-skill/SKILL.md`; assert the file exists and `SkillRegistry.from_settings(deps.settings).discover(reload=True).get("my-new-skill")` round-trips `description`/`body`.
   - `update_skill(ctx, "my new skill", "new body")` → reloaded skill body == `"new body"`; unknown name returns `"(no such skill)"`.
3. `tests/toolkits/test_integration.py`:
   - `Agent.make("full").instructions("x").full(models={"feedback": Feedback}, tasks=["noop"], jobs={}).output(str).build()` (all flags default on) — assert the built agent registers the expected tool names for every toolkit (`db_find`, `schedule_task`, `enqueue_task`, `notify`, `list_conversations`, `usage_summary`, `index_document`, `save_skill`) with no collisions, plus `learning` tools (`learn`, `reflect`, `list_lessons`, `forget_lesson`).
   - With one flag off (e.g. `settings` built with `db_tools_enabled=False`), assert `db_find` is absent. Confirm how `.full()` obtains settings for gating (it uses the enabled-toolkit layer; verify by reading `_attach_native` in `foundation/agent.py` and adapt the test to the actual mechanism — likely a settings object passed through `full(...)`/app).
   - `stack_view(settings, app)` (from `agentkit.webui.introspect`) reports `native_tools.enabled` containing the enabled toolkit names and the allow-listed `models`/`tasks`/`jobs` from the `App`.
   - Add a matching `assert` in `tests/test_foundation_scaffold.py` only if needed.

## Task 2 — Learning tests (`tests/test_learning.py`)

Cover `src/agentkit/learning.py`:

- **Extraction**: seed `repos.conversations` + `repos.messages` with a few turns; `await reflect(repos)` uses the offline `_heuristic_extract` and returns `lessons`/`preferences`/`facts` counts > 0 for sentences matching `_LESSON_RE`/`_PREF_RE`/`_FACT_RE`; stored rows are `kind="procedural"` in `repos.memories`.
- **Model path**: pass a `pydantic_ai.models.function.FunctionModel` (or `TestModel`) stub that returns a JSON object; assert `_model_extract` shape is honored via `reflect(repos, model=stub)`; also assert malformed JSON falls back to heuristics (the `except Exception` branch).
- **Idempotency**: a second `reflect(repos)` with the same conversation/window returns `skipped=True` (driven by `repos.learning_runs.seen`); a different window is not skipped.
- **Dedupe**: add two near-identical lessons → `reflect` reports `merged >= 1` and only one procedural memory remains (uses `memories.near_duplicates`/`merge`).
- **Redaction**: a lesson containing an email/secret-style token is stored with PII/secret redacted (`guardrails.redact_pii`/`redact`).
- **Skill distillation**: with `learning_skill_threshold=2` and 2 identical lessons, `reflect(...).skill_candidates` is non-empty; with `auto_skills=True` (or `learning_auto_skills=True`) a `SKILL.md` is written into `settings.skills_dir`. Note `_distill` runs **before** `_dedupe_lessons` (must stay that way).
- **Tools** (`.learning()` / `.full()`): `learn`/`reflect`/`list_lessons`/`forget_lesson` present; call `learn` → memory added with redaction; `list_lessons` shows it; `forget_lesson` removes it (`forgotten` / `no such lesson`).
- **Gating**: `learning_enabled=False` → `.full()` does not attach learning tools; `FullStackProvider` does not schedule `learning:reflect` (extend the two new tests in `tests/test_fullstack.py` only if they do not already assert this).
- **Durable task**: `register_reflect_task()` is idempotent and `learning:reflect` ∈ `scheduler.TASKS`.
- **Instructions digest**: `lessons_digest(repos)` returns `None` when empty and includes `#<id> <content>` once lessons exist; assert the built agent's instruction includes the digest text when lessons exist (call `_learning_instructions` through the tool/agent instructions path).
- **CLI**: `learning:reflect --dry-run`, `learning:lessons`, `learning:forget <id>` via `typer.testing.CliRunner`; monkeypatch `agentkit.runtime.build_runtime`/`repositories` (or `AGENT_HOME`) so the CLI hits `tmp_path`. Follow the isolation pattern in `tests/test_foundation_scaffold.py`/`tests/test_cli*.py` if present.

## Task 3 — Scaffold (`src/agentkit/foundation/scaffold/full.py`)

Keep `tests/test_foundation_scaffold.py::test_scaffolded_project_boots_and_tests_pass` green.

- Add `"config/learning.py"` to `_full_overlay()`:
  ```python
  # Overrides for the "learning" config section (defaults < this file < environment).
  config = {"enabled": True, "reflect_cron": "0 4 * * *"}
  ```
- In the overlay `app/Agents/assistant.py`, insert between `.tool(...)` calls and `.full()`:
  ```python
  # Native toolkits are opt-in per capability; allow-lists stay empty by default.
  # .database({"note": Note})            # expose allow-listed models to the agent
  # .scheduler(["sync_notes"])           # expose allow-listed tasks
  # .queue()                             # enqueue allow-listed jobs/tasks
  .learning()                            # reflect -> learn -> apply
  ```
  `.learning()` is safe with defaults and keeps the smoke test passing.
- Update `_FULL_STACK_README` layer table (add: Native toolkits / `db_tools_enabled`…; Self-learning / `LEARNING_ENABLED`) and `_FULL_STACK_ENV` (commented `AGENTKIT_LEARNING_ENABLED`, `AGENTKIT_LEARNING_REFLECT_CRON`, per-toolkit flags).
- No `EXPECTED` change needed: `config/memory.py`/`config/channels.py` are not listed either; confirm `config/learning.py` boots (it is optional overrides).

## Task 4 — Docs (Laravel style: `# Title` → `## Introduction` → sections, `::: tip`/`::: warning`)

- New `docs/guide/native-tools.md`: every toolkit (tools, args, approval status), safety model (deny-by-default allow-lists, owner scoping, audit, approvals), the builder methods, and `App.models/agent_tasks/agent_jobs`.
- New `docs/guide/self-learning.md`: the reflect → learn → apply loop, signals, storage (procedural memories/profile), guardrails (redaction, caps, decay, `learning_enabled`), skills distillation, CLI, durable scheduling.
- Update existing guides: `agents.md` (builder methods + `.full()` layers), `fullstack.md` (new flags/layers + `LearningSection`), `memory.md` (lessons/procedural), `skills.md` (authoring + distillation), `scheduling.md` and `jobs.md` (`learning:reflect`, queue toolkit, `RunRegisteredTask`), `facades.md` (new exports).
- `docs/.vitepress/config.mts`: add `{ text: "Native Tools", link: "/guide/native-tools" }` and `{ text: "Self-Learning", link: "/guide/self-learning" }` under **The Basics** (after "The Agent Builder"/"Tools").
- Root `README.md` highlights + a short section; `CHANGELOG.md` `## [Unreleased]` → `### Added` entries (mirror into `docs/reference/changelog.md` if it mirrors the root).
- Optional: `npm run build` in `docs/` (node_modules present) to catch broken links/sidebar entries.

## Task 5 — Final validation (must all pass)

- `uv run ruff check src tests`
- `uv run mypy src/agentkit`
- `uv run pytest` (full suite; coverage gate ≥70%; was ~79.5%) — this also re-runs the earlier toolkit tests and the scaffold subprocess smoke test.
- `uv run pytest tests/toolkits tests/test_learning.py -q` first for a fast inner loop.

## Do-not-commit / constraints

- Do not commit `.kilo/` or `kilo.jsonc`/`kilo.json` (untracked tooling). No committing at all unless the user asks.
- No new comments beyond what templates require; match existing style.

## Gotchas (carry over from CONTINUATION.md)

- Approval is registration-based: `@agent.tool(requires_approval=True)` + `approval_capability`; `ToolPolicy.require_approval` alone does nothing at runtime.
- `db/repositories/learning.py` must stay a plain repo class (importing `agentkit.foundation.repository` there is circular).
- In `reflect`, `_distill` must run **before** `_dedupe_lessons`.
- `attach_learning`'s tool is named `reflect`; the module function is reached via `_reflect_for_ctx` (do not shadow).
- `attach_queue` needs the task allow-list (passed by `attach_toolkits`).
- `App.models` is overloaded: a `Mapping` = DB allow-list; a callable = `model_resolver`.
- `notify` (conversation channel) writes through the current repos session, not the sync `Notifier`.
- Use `run_sync` for sync seams; never `asyncio.run` from async code.
