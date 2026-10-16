# Studio MVP & Remaining Gap-Fill

Source of truth: `CONTINUATION.md` "NOT DONE" (items 1–10). Workstreams WS0–WS5
landed in commit `160bac2`; the tree is clean except untracked `docs/.vitepress/`
(build artifacts). This plan finishes **all** remaining items in priority order.

Do **not** commit `.kilo/` or `kilo.json` (untracked tooling). Web/doc builds
write tracked bundles — include both old and new hashed assets in any commit.

## Constraints / gotchas to honor

- `db/repositories/*` must not import `agentkit.foundation.*` at module level
  (circular). New repo code inherits this.
- Async discipline: never `asyncio.run` from async code; use
  `agentkit._sync.run_sync` at sync seams. New DB writes go through the async
  repos layer.
- New `UsageRecord` columns are nullable/defaulted → auto-added by
  `db/migrations.py::apply_missing_columns` (no Alembic step needed).
- `hybrid` posture must stay a byte-for-byte no-op (asserted by
  `test_hybrid_full_matches_unpostured_full`); settings flags are a hard veto.
- Parse approvals/notifications stay registration-based; don't change that model.
- `web/` builds into `src/agentkit/webui/static/` (tracked); `docs/` is React
  Router (`cd docs && bun run build`).

## Tasks (ordered)

### T1 — Persist context telemetry + Usage context chart (item 1a)
- `src/agentkit/db/models.py` (`UsageRecord`, ~L58): add nullable columns
  `cache_read_tokens: int = 0`, `context_tokens: int = 0`,
  `context_window: int | None = None`.
- `src/agentkit/db/repositories/usage.py`: `UsageRepo.add(...)` gains the three
  kwargs; store them. `totals()` sums `cache_read_tokens` and `context_tokens`
  (do **not** sum `context_window`; it is a per-model constant).
- `src/agentkit/session.py` (`_record_usage`, ~L342): currently persists only
  `requests/input_tokens/output_tokens/total_tokens`; also pass
  `cache_read_tokens`, `context_tokens`, `context_window` from `totals`.
- `src/agentkit/webui/introspect.py` (`get_usage` `/usage`, ~L260): include the
  three fields in `recent` rows and in `totals`.
- `web/src/lib/api.ts`: extend `UsageRow` and `Usage.totals`.
- `web/src/routes/usage.tsx`: add a "Context window" chart plotting per-turn
  `context_tokens` against the row's `context_window` (bar + reference line), and
  add `cache_read_tokens` / `context_tokens` totals cards alongside existing ones.
- Tests: repo-level `add`/`totals` round-trip for the new fields; webui `/usage`
  surfaces them (extend `tests/test_webui.py`).

### T2 — Teams view (item 1b)
- `src/agentkit/webui/introspect.py`: add `GET /api/teams` returning
  `[{"name", "kind", "roster": sorted(spec.roster)}]` from
  `agentkit.teams.TEAMS`. (`stack_view` already lists `teams` names; this adds
  kind + members.)
- `web/src/lib/api.ts`: `Team` type + `api.teams()`.
- `web/src/routes/teams.tsx` (new): read-only list (name, kind, members) with a
  hint that a registered `team_<name>` tool runs the team from Chat. Note when a
  team has no `team_<name>` tool registered (roster not exposed to Chat).
- `web/src/App.tsx`: add nav item (e.g. `Network`/`Users` icon) + `<Route>`.
- Tests: `/api/teams` returns registered specs (extend `tests/test_webui.py`).

### T3 — Verify Lessons review still renders (item 1c)
- Confirm `/api/lessons` + `/api/lessons/{id}/approve|reject` (webui/learning_api)
  back `web/src/routes/lessons.tsx`. Add a webui regression test hitting
  `GET /api/lessons?status=proposed` if none exists. No UI rewrite expected.

### T4 — Web UI ephemeral "temporary chat" toggle (item 3)
- `src/agentkit/webui/app.py`: `ChatBody.ephemeral: bool = False`; `/api/chat`
  passes `ephemeral=body.ephemeral`; `/api/chat/stream` passes
  `ephemeral=body.ephemeral` to `ctx.app.stream(...)`.
- `src/agentkit/foundation/application.py` (`answer`, ~L945): `run_answer` gains
  `ephemeral: bool = False` and forwards it to `self.run(...)`.
- `web/src/lib/api.ts`: `chat(conversationId, text, ephemeral = false)`.
- `web/src/routes/chat.tsx`: add a "Temporary chat" switch; when on, skip the
  history query/refetch, show a banner, and send `ephemeral=true`.
- Tests: `POST /api/chat` with `ephemeral=true` writes no conversation/messages
  (assert `GET /conversations/{id}/messages` is empty); non-ephemeral still persists.

### T5 — Posture `settings_overrides` (item 4)
- **Decision (precedence):** a posture override applies **only when the setting
  is still at its field default**; an operator-set (non-default) value wins.
  `hybrid` and `specialized` declare `{}` (no-op); only `free` populates it.
- `src/agentkit/posture.py`: add `apply_settings_overrides(settings, profile) ->
  AgentSettings` returning `settings` unchanged when `profile` is `None` or has no
  overrides (or when every key is already non-default), else
  `settings.model_copy(update=<applicable keys>)`. Populate `_free()` with e.g.
  `{"tool_output_offload_threshold": 4000, "memory_nudge_every": 10}`.
- Apply in **both** resolution points:
  - `src/agentkit/foundation/application.py::boot()` at the very top (before
    runtime build and before the `memory_nudge_every` check ~L254), guarded so it
    runs once and only replaces `self._settings` when something changes — this
    makes `runtime.settings` / `deps.settings` (which read the same object) see
    the override.
  - `src/agentkit/foundation/agent.py::full()`: apply to the local `resolved`
    copy before the `enabled()`/`layer()` decisions so the builder path matches.
- Tests (`tests/test_posture.py`): `free` + defaults enables offload/nudges;
  explicitly-set non-default value survives `free`; `hybrid`/`specialized` leave
  settings byte-for-byte unchanged.

### T6 — Compaction telemetry (item 5)
- `src/agentkit/session.py`: in `_begin`, after the history processor runs,
  compare pre/post message counts (and `estimate_tokens`) and record
  `self._compaction = {"messages": dropped, "tokens": saved}` when it shrank.
  In `stream()`, yield `StreamEvent("compaction", text="...")` before the text
  stream. Add `compacted_messages` to `_usage_totals` so `ChatResult.usage`
  carries it for `/api/chat` too.
- `StreamEvent` docstring: document the `"compaction"` kind.
- `webui/app.py` `chat_stream` already forwards `kind`/`text` generically — no
  change (verify).
- `web/src/routes/chat.tsx`: show "context compacted (N)" when
  `usage.compacted_messages > 0`.
- Tests (`tests/test_session.py`): a shrinking history processor makes `stream()`
  emit a `compaction` event and sets `usage["compacted_messages"]`.

### T7 — Scheduling channel delivery (item 2)
- **Decision:** record the origin as `_deliver_to` inside the job's JSON `args`;
  deliver via a scheduler result sink wired to the app notifier.
- `src/agentkit/scheduler.py`: module-level `_result_sink: Callable[[str, str],
  Any] | None`, `set_result_sink(fn)`. In `invoke_task`, pop `_deliver_to` from
  the parsed args, run the task, then call the sink with
  `(conversation_id, result_text)` on success (best-effort; never mask the task
  result/error). Covers `tick`/`run_due_now`/`run_schedule_now` (all funnel
  through `invoke_task`).
- `src/agentkit/foundation/application.py::boot()`:
  `scheduler.set_result_sink(self._deliver_result)`. Add `_deliver_result(
  conversation_id, text)` mapping the conversation prefix
  (`conversation_id.split(":",1)[0]`, e.g. `telegram`/`cli`/`webui`) to a notifier
  channel name (fall back to `"conversation"`) and calling
  `self.notify(<Notification>, to=[channel], conversation_id=conversation_id)`
  (see `foundation/notifications.py`).
- `src/agentkit/toolkits/scheduler.py`: `schedule_task` and `schedule_natural`
  gain `deliver_to: str | None = None` (default `ctx.deps.conversation_id`),
  written into `args` as `_deliver_to`; `run_schedule_now` delivers to the
  current conversation.
- Tests (`tests/test_surfaces.py` or new): schedule with `deliver_to`, register a
  stub notifier channel, `invoke_task` posts the result; no `_deliver_to` → no
  delivery.

### T8 — Magentic LLM planner + member-writable ledger (item 6)
Two coordinated parts: a model-driven manager **and** real member ledger tools.

**8a — Model-driven manager**
- `src/agentkit/agents/team.py`: add `planner_model: Any = None` (and/or a
  `planner_agent`) to `MagenticTeam`. When set and no explicit `manager`, build an
  async manager that prompts the model with `ledger.render()` + the stalled member
  and parses returned plan steps; keep the deterministic `manager` as fallback.
  `_replan` already calls `self.manager` — route the LLM manager through it. The
  manager owns `ledger.plan`.

**8b — Member-writable ledger (essential)**
- **Decision (single-writer per field):**
  - `plan` + task **creation/assignment** → **manager only** (T8a's manager, or any
    explicit `manager`).
  - `facts` (append, deduped) + **own-task status** → members.
  - A member that needs to change direction records a *fact* (e.g.
    `"blocked: X; propose: add step Y"`); the manager reconciles on its next
    reconcile/replan. Members get a voice, not plan-write authority.
- **Access mechanism (decided):** shared ledger via `deps.extras`, exposed to local
  members through idempotently attached tools that resolve the *active* ledger at
  call time.
- `src/agentkit/agents/team.py` (or a new `src/agentkit/agents/ledger.py`):
  - `attach_team_ledger(agent, *, name=None)` — idempotent (mirror
    `attach_scheduler`'s `_agentkit_*_attached` guard). Registers `read_ledger` and
    `write_ledger` on anything with `.tool` (pydantic_ai Agent) or on
    `AgentHandle.agent`; no-op for plain callables/remote handles. Binds the calling
    member's `name` into the tool closure (for ownership checks).
  - Tools read `ctx.deps.extras["team_ledger"]`; when absent (no deps / remote /
    callable member), return a clear "no active ledger" string instead of raising.
  - `read_ledger() -> str` returns `ledger.render()`.
  - `write_ledger(fact: str | None = None, complete: int | None = None) -> str` —
    narrow writes only: append a (deduped) fact, or complete one task by id. Returns
    the updated render. **No `plan` and no task-creation param.**
    - `complete` must target a task the caller owns (or an unowned task); completing
      another member's task returns a clear rejection. Uses the bound member name.
  - Per-round marker: a `write_ledger` call sets `deps.extras["team_ledger_wrote"]`
    so the loop can reconcile (below).
- **Manager owns tasks:** after the manager sets a plan, `MagenticTeam` derives
  pending tasks from the plan steps (one task per step, deduped by description;
  `owner` left optional for a future richer manager). This satisfies
  "manager creates/assigns tasks" without changing the `manager` callable
  signature (`Callable[[TeamLedger, str], list[str]]`).
- `MagenticTeam.run(task, *, ctx=None)`: at start, if `ctx` has `deps`,
  `ctx.deps.extras["team_ledger"] = self.ledger`, attach the tools to each local
  member (with its roster name), and reset the per-round write marker each round.
- **Heuristic reconciliation (decided):** if a member wrote to the ledger this
  round, skip the auto-fact / auto-`complete_task(pending[0])` heuristic
  (`team.py:132-137`) for that round; otherwise keep the existing heuristic so the
  deterministic-manager path is unchanged. Facts already dedupe in
  `TeamLedger.add_fact`.
- Exports: `attach_team_ledger`, `read_ledger`, `write_ledger` via
  `agents/__init__.py` and `agentkit/__init__.py` (match existing teammates).

**8c — Tests** (`tests/test_multiagent.py`):
- With a stub planner, a stall triggers a model-derived plan update on the ledger;
  without a planner, behavior unchanged.
- A member that calls `write_ledger` adds a fact / completes a task, and the loop
  heuristic is suppressed that round (no spurious `pending[0]` completion).
- Ownership: completing an unowned/own task succeeds; completing another member's
  task is rejected with a clear message.
- Manager-derived tasks: setting a plan materializes one deduped pending task per
  step.
- With no `ctx`/deps, members fall back to prompt-only and the tools report "no
  active ledger" without raising.
- Idempotent attach: calling `attach_team_ledger` twice does not double-register.

### T9 — Optional-extra spot checks (item 8)
- For each extra (`jupyter`, `e2b`, `ssh`, `modal`, `daytona`, `vercel`, `s3`,
  `tui`): `uv sync --extra <name>`, construct the driver and exercise its happy
  path; keep/extend the skip-guarded test so CI without the extra still passes.
- Confirm the missing-extra path still raises `ConfigurationError` naming the
  extra (`_missing_extra` in `executors.py`).
- Record which extras were verified in `CHANGELOG.md`. Never add a hard core dep.

### T10 — Builds, `generate` tests, version, changelog (items 7, 9, 10)
- `cd web && bun run build` (writes hashed bundles to `src/agentkit/webui/static/`;
  stage both removed + new assets).
- `cd docs && bun run build`; verify nav/`DOC_PATHS` renders the 5 new guide pages
  (posture/search/group-chat/training/surfaces).
- Item 9: add unit tests for `_read_prompts` and the `agentkit generate` batch
  path in `src/agentkit/cli/commands/training.py`.
- Item 10: bump version. **Recommendation:** `0.2.0` in `pyproject.toml` and
  `src/agentkit/__init__.py::__version__` (`0.1.0` → `0.2.0`) given the scope, and
  move `CHANGELOG.md` `## [Unreleased]` entries under `## [0.2.0]`.
- Add CHANGELOG entries for Studio MVP (context chart, teams), ephemeral toggle,
  channel delivery, posture overrides, compaction event, the LLM planner, and the
  member-writable team ledger tools.

## Validation (run after implementing)

```bash
uv run ruff check src tests
uv run mypy src/agentkit
uv run pytest --cov=agentkit --cov-report=term        # gate ≥70%
cd web && bun run build
cd docs && bun run build
```

Also boot the generated scaffold canary (`tests/test_foundation_scaffold.py`)
since T4/T5/T7 touch `App.boot`/`session`/scaffold-adjacent paths.

## Risks

- **UsageRecord columns**: older DBs get columns via `apply_missing_columns`; make
  every new column nullable or defaulted, or it is skipped.
- **Posture precedence**: any change to `App.boot` ordering can perturb
  `runtime.settings` identity; keep the `hybrid` no-op assertion green and apply
  overrides before the runtime/nudge checks.
- **Result sink**: delivery must never turn a successful task into a failure —
  wrap in best-effort error handling and keep `_deliver_to` out of the task
  callable's kwargs.
- **Web bundle churn**: a rebuild deletes old hashed assets; stage both sides.

## Open questions (defaults chosen above)

- Version bump target: defaulting to `0.2.0`; confirm exact number/date before
  tagging.
- Ledger write policy is **resolved** (single-writer: manager owns plan+tasks;
  members own facts + own-task status). Only remaining optional: whether the
  manager callable should grow a richer return (tasks + owners) instead of
  deriving tasks from plan steps — deferred; current signature stays
  `Callable[[TeamLedger, str], list[str]]`.
