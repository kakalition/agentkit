# CONTINUATION — Posture Duality & Gap-Fill

Source-of-truth plan: `.kilo/plans/1792122358580-studio-mvp-and-remaining-gaps.md`
(the earlier `1792103850196-posture-duality-and-gap-fill.md` it superseded does
not exist). See also `.kilo/plans/1792071123307-competitive-improvement-roadmap.md`,
the contracts+drivers roadmap this builds on.

Branch: `main`, work in the tree (uncommitted at handoff time — see "Commit" below).
Do **not** commit `.kilo/` or `kilo.json` (untracked tooling; they are git-ignored
by convention, keep it that way).

---

## Status at handoff (2026-10-16)

All validation is **green** as of the last edit:

| Check | Command | Result |
| --- | --- | --- |
| Lint | `uv run ruff check src tests` | clean |
| Types | `uv run mypy src/agentkit` | clean (223 files) |
| Tests | `uv run pytest --cov=agentkit --cov-report=term` | all pass, **coverage 81%** (gate ≥70%) |
| Web build | `cd web && bun run build` | passes (bundles written to `src/agentkit/webui/static/`) |

Workstreams WS0, WS-DX, WS1, WS2, WS3, WS4 and WS5 are **complete** (see RESOLVED).

## Later plane — Extension Substrate (0.3.0, 2026-10-16)

The follow-on plan `.kilo/plans/1792131022744-agentkit-extension-substrate.md`
(extension substrate + gap-fill) is implemented and green:

| Check | Command | Result |
| --- | --- | --- |
| Lint | `uv run ruff check src tests` | clean |
| Types | `uv run mypy src/agentkit` | clean (263 files) |
| Tests | `uv run pytest --cov=agentkit` | 743 pass / 11 skip, **coverage 79%** (gate ≥70%) |
| Web build | `cd web && bun run build` | passes (App + Traces tabs added) |
| Docs build | `cd docs && bun run build` | passes (new guide pages prerender) |

Delivered: `agentkit.extensions` (manifest + registry + discovery + panel/action
SPI), `agentkit.specs` (spec registry, `definitions` store + migration, codegen,
spec CLI), run traces (`agentkit.runs`), checkpoints (`agentkit.checkpoints`),
computer-use (`agentkit.computer`), realtime (`agentkit.realtime`), graders
(`agentkit.graders`), catalog (`agentkit.catalog`), the Studio **App inspector**
(`GET /api/studio/app`) and **Traces** panel, plus `browser`/`realtime` extras and
`CHANGELOG.md` `[0.3.0]`. The `0.2.0` validation numbers above describe the
*earlier* handoff, not the current tree.

---

## DONE

### WS0 — Posture backbone (`specialized | hybrid | free`, default `hybrid`)
- **`src/agentkit/posture.py`** (new): `Posture`, `PostureProfile`, `POSTURES`,
  `register_posture`, `resolve_posture`, `LAYER_KEYS`, preambles.
- **`src/agentkit/policy.py`**: added `SPECIALIZED_DENY`, `FREE_APPROVAL_TOOLS`,
  `specialized_policy()`, `free_policy()`.
- **`src/agentkit/config.py`**: added `agent_posture: Posture = HYBRID`.
- **`src/agentkit/foundation/agent.py`**: `.posture()/.specialized()/.free()`,
  `posture_name`; `.full()` now resolves omitted layer toggles from the posture
  profile via module-level `_FULL_DEFAULTS` (precedence: explicit arg > builder
  method > posture > settings flag; settings flags still veto). `_resolve_profile`,
  `_apply_preamble`, `_default_workspace` helpers. Safety uses
  `profile.policy_factory()`; `free` also adds egress (web_search/web_fetch) and
  workspace/subagents/code.
- **`src/agentkit/foundation/application.py`**: `App.posture(...)`, `posture_name`,
  seeds `deps.extras["posture"]`.
- **`src/agentkit/webui/introspect.py`** + **`cli/commands/inspect.py`**: report
  the active posture.
- **`src/agentkit/foundation/scaffold/full.py`** + **`cli/commands/generators.py`**:
  `agentkit new --posture <name>` writes `.posture("<name>").full()` and
  `posture = "<name>"` into the generated `app/Agents/assistant.py`.
- **Tests**: `tests/test_posture.py`. **Docs**: `docs/guide/posture.md`.

### WS-DX — Laravel front door
- **`src/agentkit/foundation/application.py`**: `Application = App` alias;
  `ApplicationBuilder` + `App.configure(...)` with
  `withProviders/withConfig/withAgents/withChannels/withCommands/withPosture/withBasePath/create`.
- **`src/agentkit/foundation/discovery.py`** (new): `discover_providers`,
  `discover_agents`, `discover_channels`, `discover_commands`, `discover_config`,
  `discover_repositories`, `CONVENTIONAL_DIRS`.
- **`src/agentkit/foundation/agent.py`**: `AgentDefinition` base (class-based agents
  under `app/Agents/`), `_snake_case`, `to_builder`.
- **Scaffold rewrite**: `foundation/scaffold/minimal.py` + `full.py` now generate a
  ~4-line fluent `bootstrap.py`, a class-based `app/Agents/assistant.py`, and rely
  on convention discovery (no hand-listed providers, no `app.agent(...)` call).
  **`tests/test_foundation_scaffold.py` still boots the generated project in a
  subprocess and is green.**
- **Generators**: `make:agent` now emits a discoverable `AgentDefinition` under
  `app/Agents/`; paths use `app/…`; added `make:policy`; `cli/commands/generators.py`
  + `tests/test_foundation_cli.py` updated.
- **Exports**: `Application`, `ApplicationBuilder`, `AgentDefinition`,
  `discover_*` in `foundation/__init__.py` and `agentkit/__init__.py`.
- **Tests**: `tests/test_discovery.py`.

### WS1 — Context & memory parity
- **Ephemeral conversations**: `session.ChatRunner(persist=False)` (skips
  conversation/message/usage writes, sets `deps.extras["ephemeral"]`),
  `App.run/stream(ephemeral=)`, `agentkit tinker --ephemeral`. Memory writes are
  suppressed via `memory._writable`.
- **Tool-output offload**: **`src/agentkit/offload.py`** (new) —
  `offload_messages`, `attach_artifacts` (`read_artifact` tool), `estimate_tokens`;
  `tool_output_offload_threshold` setting; applied in `ChatRunner._offload_large_outputs`.
- **Indexed cross-session search**: **`src/agentkit/search.py`** (new) +
  **`src/agentkit/contracts/search.py`** (`SearchIndex`, `SearchHit`) +
  **`src/agentkit/db/fts.py`** (FTS5 `messages_fts` + triggers, created in
  `db/migrations.py::init_db`); `DriverKind.SEARCH`, `SearchDriver(fts|scan)`,
  `SearchManager`, `App.search`; `MessageRepo.search_text` (FTS5 with LIKE
  fallback); tools `search_history` + `search_sessions` in `toolkits/history.py`;
  `GET /api/search` in `webui/introspect.py`; web UI page
  `web/src/routes/search.tsx` + `App.tsx`/`api.ts` wiring.
- **Memory nudges**: **`src/agentkit/nudges.py`** (new) + `learning.propose_memories`
  (review-gated). Setting `memory_nudge_every` (0 = off); registered in `App.boot`.
- **Context telemetry**: `ChatRunner._usage_totals` adds `cache_read_tokens`,
  `context_tokens`, `context_window` to `ChatResult.usage`.
- **Exports**: `SearchIndex/SearchHit/SearchManager/FtsSearchIndex/ScanSearchIndex`,
  `offload_messages/attach_artifacts/estimate_tokens`, `register_memory_nudges`,
  `propose_memories`.
- **Tests**: `tests/test_offload.py`, `tests/test_nudges.py`, `tests/test_search.py`,
  additions in `tests/test_session.py`, `tests/test_webui.py`.
- **Docs**: `docs/guide/search.md`.

### WS2 — Multi-agent parity
- **`src/agentkit/contracts/speaker.py`** (new): `SpeakerStrategy` Protocol.
- **`src/agentkit/agents/speaker.py`** (new): `RoundRobinSpeaker`,
  `ModeratorSpeaker`, `AllSpeaker`, `SelectorSpeaker`, `ManualSpeaker`,
  `SpeakerManager`, drivers under `DriverKind.SPEAKER` / `SpeakerDriver`; setting
  `speaker_driver`; `App.speaker`.
- **`src/agentkit/agents/groupchat.py`** (new): `GroupChatRunner` (real turn loop,
  shared transcript, max-turns/terminator/consensus, `agent.message` events),
  `GroupChatResult`. `comms.GroupChatTopology.run()` delegates to it.
- **`src/agentkit/agents/team.py`** (new): `ManagedTeam` (manager-led rounds,
  replan-on-stall) + `TeamLedger` (facts/plan/tasks) + `TeamRunResult`.
- **`src/agentkit/teams.py`**: `TeamSpec`, `TEAMS`, `register_team`, `resolve_team`,
  `build_team`, `team_tool` (namespaced `team_<name>`); `Agent.team("name")`.
- **Introspection**: `stack_view` reports `teams`; `inspect` prints them.
- **Exports**: speakers, `GroupChatRunner`, `ManagedTeam`, `TeamLedger`, team regs.
- **Tests**: `tests/test_multiagent.py`. **Docs**: `docs/guide/group-chat.md`.

### WS3 — Execution backends
- **`src/agentkit/contracts/codeexec.py`**: added optional `HibernatingExecutor`
  Protocol (kept separate so base conformance still holds).
- **`src/agentkit/executors.py`**: real `JupyterExecutor` (jupyter_client) and
  `E2BExecutor` (e2b, with `hibernate`/`wake`); new `SSHExecutor` (paramiko),
  `ModalExecutor`, `DaytonaExecutor`, `VercelExecutor`, `SingularityExecutor`; all
  import-guarded naming their extra. `CodeExecDriver` gained
  ssh/modal/daytona/vercel/singularity. **Fixed a latent bug**: `CodeExecManager`
  read `codeexec_driver`; now `setting_name = "code_executor_driver"`.
- **`src/agentkit/foundation/storage.py`**: `S3FileSystem` (`StorageDriver.S3`, `s3`
  extra), lazy boto3; `_boto()` resolved before try so a missing extra is not masked.
- **`pyproject.toml`**: extras `jupyter`, `e2b`, `ssh`, `modal`, `daytona`,
  `vercel`, `s3`, `tui`.
- **Tests**: `tests/test_executors.py`. **Docs**: extended
  `docs/guide/code-execution.md`.

### WS4 — Training & migration
- **`src/agentkit/trajectory.py`** (new): `export_trajectory`, `compress_messages`,
  `compress_content`, `iter_trajectories`, `render_jsonl`.
- **`src/agentkit/migrate.py`** (new): `migrate_openclaw`, `MigrationReport`.
- **CLI**: `agentkit trajectory …` and `agentkit generate …` in
  `cli/commands/training.py`; `agentkit migrate openclaw <dir>` folded into the
  existing DB `migrate` command in `cli/commands/ops.py`.
- **Tests**: `tests/test_training.py`. **Docs**: `docs/guide/training.md`.

### WS5 — Surfaces & channels (partial)
- **Channels**: `ChannelDriver` gained `mattermost`/`linear`/`webhook`;
  **`gateways/mattermost.py`**, **`gateways/linear.py`**, **`gateways/webhook.py`**;
  registered in `gateways/registry.py`. Settings: `mattermost_*`, `linear_api_key`,
  `webhook_url`, `channel_pairing_enabled`.
- **DM pairing**: **`gateways/pairing.py`** (`PairingRegistry`), wired into
  `gateways/base.py` (`is_allowed`, `pair`, `confirm_pairing`).
- **TUI**: **`src/agentkit/tui.py`** (`run_tui`, lazy `textual`) + `agentkit tui`
  (`cli/commands/surfaces.py`).
- **MCP serve**: `mcp/server.py` gained `build_agent_mcp_server`/`serve_agent`
  (an `ask` tool) + `agentkit mcp:serve`.
- **NL scheduling**: **`src/agentkit/scheduling_nl.py`** (`parse_when`,
  `NaturalSchedule`) + approval-gated `schedule_natural` tool in
  `toolkits/scheduler.py`.
- **Exports**: `run_tui`, `build_agent_mcp_server`, `serve_agent`, `PairingRegistry`,
  `NaturalSchedule`, `parse_when`.
- **Tests**: `tests/test_surfaces.py`. **Docs**: `docs/guide/surfaces.md`.

### Cross-cutting
- Public exports added to `src/agentkit/__init__.py` for every new name above.
- `CHANGELOG.md` `## [Unreleased]` has an entry per workstream.
- `README.md` front door updated (fluent `Application.configure()` + class-based
  agent + posture). `docs/src/lib/nav.ts` gained posture/search/group-chat/training/
  surfaces. `docs/guide/AGENTS.md` documents `.posture(...)` and `.team(...)`.

---

## RESOLVED (2026-10-16)

The next-steps list that lived here was completed in the Studio MVP & gap-fill
pass (see `CHANGELOG.md` `[0.2.0]`):

1. **Studio MVP** — persisted `cache_read_tokens`/`context_tokens`/
   `context_window` telemetry with a web Usage context chart; `GET /api/teams` +
   a web Teams view; lessons review verified with a regression test.
2. **Channel delivery for scheduling** — `_deliver_to` recorded in a job's args;
   `scheduler.invoke_task` calls a result sink (`App._deliver_result`) that maps
   the conversation prefix to a notifier channel (`conversation` fallback).
3. **Web UI ephemeral toggle** — `ChatBody.ephemeral` → `/api/chat[/stream]` →
   `App.run/stream(ephemeral=)`; a Chat switch that skips history persistence.
4. **Posture `settings_overrides`** — `apply_settings_overrides` applied in
   `App.boot()` and `Agent.full()`; `free` enables offload + nudges (an
   operator-set non-default value wins); `hybrid`/`specialized` stay no-ops.
5. **Compaction event** — `StreamEvent("compaction")` + `usage.compacted_messages`,
   surfaced in the Chat route.
6. **Model-driven planner + member ledger** — `ManagedTeam(planner_model=.../
   planner_agent=...)` and member-writable `read_ledger`/`write_ledger` tools
   (`attach_team_ledger`), with the manager owning the plan/tasks.
7. **Docs/web builds re-run** — both green; the 5 guide pages prerender.
8. **Optional-extra paths** — all 8 extras spot-checked; missing-extra tests are
   skip-guarded so CI without an extra still passes.
9. **`agentkit generate`** — `_read_prompts` + batch CLI unit tests added.
10. **Version bump** — `0.2.0` (`pyproject.toml`, `agentkit.__version__`,
    `uv.lock`) with `CHANGELOG.md` `[Unreleased]` → `[0.2.0]`.

Also: the manager-led team class and its team kind were renamed to
`ManagedTeam`/`managed`; the web SPA's missing `@tanstack/react-query`/
`react-router-dom` deps added; the stale `docs/.vitepress/` directory removed
(now gitignored).

---

## Validation (run these first when you resume)

```bash
uv run ruff check src tests
uv run mypy src/agentkit
uv run pytest --cov=agentkit --cov-report=term        # expect ≥70% (currently 81%)
cd web && bun run build                                # if web/src changed
# docs (React Router) build, if node_modules present: (cd docs && bun run build)
```

---

## Gotchas / decisions to remember

- **Posture precedence** lives in `Agent.full()`: explicit arg > builder method >
  posture > settings flag; settings flags are a hard veto (AND). `hybrid` is the
  no-op profile (`_FULL_DEFAULTS` == old defaults), asserted by
  `test_hybrid_full_matches_unpostured_full`.
- **Discovery runs at boot** (`ApplicationBuilder.create`), never at import; explicit
  `with*` declarations are registered last and win. `discover_repositories` imports
  `app/Repositories/__init__.py` (AppRepositories lives there, not in a non-underscore
  module), so it does **not** skip `__init__`.
- **`migrate` CLI name is shared** with DB schema migration; the hub import is folded
  in as `agentkit migrate openclaw <dir>` (DB migrate stays `agentkit migrate`).
- **`code_executor_driver`** is the real setting name (`CodeExecManager.setting_name`
  override) — the kind is `codeexec`. Don't regress this.
- **Approvals are registration-based**: `ToolPolicy.require_approval` is informational
  only; real approval needs `requires_approval=True` (+ `approval_capability`).
- **FTS5**: `messages_fts` (external content over `messages`, triggers) is created in
  `init_db`; `MessageRepo.search_text` falls back to `LIKE` if FTS5 is unavailable.
  Use `session.exec(statement)` with `.bindparams(...)` (not `execute`) to avoid
  SQLModel's deprecation warning; the `TextClause` needs `# type: ignore[call-overload]`.
- **Async discipline**: never `asyncio.run` from async code — use
  `agentkit._sync.run_sync` for sync seams. SQLite single-writer: new writes go
  through the async repos layer.
- **`db/repositories/*` must not import `agentkit.foundation.*`** at module level
  (circular). New repos inherit this constraint.
- **Optional extras** are lazy-imported and raise `ConfigurationError` naming the
  extra (`_missing_extra` in `executors.py`). Never add a hard dep to core.
- **`web/` builds into `src/agentkit/webui/static/`** (tracked bundles): a rebuild
  deletes old hashed assets and adds new ones — include both in the commit.
- **Scaffold subprocess boot** (`tests/test_foundation_scaffold.py`) is the canary for
  any scaffold/discovery change.

---

## Commit

The user asked for a commit + push at handoff. Stage source/tests/docs/bundles and
`CONTINUATION.md`; **exclude** `.kilo/` and `kilo.json` (untracked tooling). Suggested:

```bash
git add -A ':!.kilo' ':!kilo.json'
git status --short          # sanity-check nothing secret/unwanted is staged
git commit -m "feat: posture duality + gap-fill (WS0–WS5 partial)"
git push
```

Note: the plan under `.kilo/plans/` (the Studio MVP & gap-fill plan this doc
references) stays untracked by design.
