# agentkit — Posture Duality + Competitive Gap-Fill

## Goal

Give agentkit a first-class **posture** so the same runtime can build either a
tightly-scoped **specialized/closed** agent or a free **autonomous generalist**
(nanobot/Hermes-style), selected by the user — *two postures, one runtime*. Then
close the concrete feature gaps versus AutoGen, LangChain DeepAgents, nanobot
(HKUDS) and Hermes Agent (Nous Research) that the four postures need to be
credible, following the existing contract + driver + Manager conventions.

Separately, make the **front door genuinely Laravel-like rather than .NET-ish**.
Today a bootstrap hand-lists `App(name=..., settings=..., repos_factory=...)`,
providers, and `app.agent(agent)`; the plan replaces that ceremony with a fluent
`Application.configure(...)`, convention-based auto-discovery, class-based agents
under `app/Agents/`, and facades/helpers as the promoted surface — while keeping
the explicit builder as the documented low-level path.

## Locked decisions

- **Duality shape:** two postures over the *existing* layers — no forked code
  paths. A single `Posture` value changes defaults; explicit builder args and
  settings always win.
- **`specialized | hybrid | free`**, **default `hybrid`** (today's `.full()`
  behavior → no breaking change).
- **Scope included:** context & memory parity, multi-agent parity, execution
  backends, training & migration, surfaces & channels, Studio **MVP**.
- **Out of scope:** distributed multi-process/queued runtime (user declined);
  full node-graph Studio; JS/TS parity; provider-specific quirks.
- **Dependency posture:** heavy drivers ship as optional extras (`pyproject.toml`),
  mirroring `docker`/`s3`; core stays PydanticAI + SQLite/DBOS.
- **Compat:** existing classes/import paths/signatures unchanged; new behavior
  opt-in.
- **Laravel DX:** `Application` is the canonical container name (`App` kept as an
  alias); a fluent `Application.configure()` is the entry point; providers,
  config, agents, channels and commands are **auto-discovered** by convention
  from `app/` and `config/`; agents may be defined as **classes** under
  `app/Agents/` with no manual registration; facades/helpers are the promoted
  surface and the explicit builder is the low-level path.

## Posture matrix (defaults; explicit args always override)

| Dimension | `specialized` (closed) | `hybrid` (default) | `free` (open) |
| --- | --- | --- | --- |
| `.full()` layers | persona + instructions + explicit tools + policy only | today's `.full()` | hybrid + workspace, subagents, code, web, channels, autonomous schedule |
| Memory | off / read-only | on (durable) | on + nudges + agent-curated |
| Skills | fixed; no authoring | discover; authoring approval-gated | discover + self-authoring/self-improving |
| Learning | off | review-gated (current default) | auto-apply low-risk; procedural still gated |
| Approvals / policy | deny-list egress+destructive; approvals required | `default_policy()` | relaxed low-risk; destructive/egress still gated |
| Code / workspace | off / read-only | opt-in | on, sandboxed |
| Egress (web) | off | opt-in | on |
| Budgets | tight caps | per settings | generous |
| Prompt preamble | "focused specialist, stay in scope" | neutral (none) | "autonomous generalist" |
| Channels / cron | off | configured only | on + result delivery |

## Competitor comparison (basis for the gap list)

| Capability | AutoGen | DeepAgents | nanobot | Hermes | agentkit today |
| --- | --- | --- | --- | --- | --- |
| Multi-agent group chat + LLM speaker | yes (round-robin/selector/swarm) | sub-agents | delegation | subagents | PARTIAL (`GroupChatTopology`, fixed enum) |
| Manager-led team w/ ledger | yes (Magentic) | — | — | — | ABSENT |
| Ephemeral chat | — | — | yes | — | ABSENT |
| Offload tool output to disk | — | yes | yes | yes | ABSENT |
| Indexed cross-session search | — | — | sessions | FTS5+LLM | PARTIAL (linear scan) |
| Memory nudge + user model | — | — | Dream | dialectic | PARTIAL (offline consolidate) |
| Context/token/cache telemetry | — | — | yes | yes | PARTIAL (tokens/cost only) |
| Self-authoring skills | — | skills | skills | yes (+self-improve) | PARTIAL (authoring only) |
| Sandbox backends | docker+ | local/remote | local | 7 incl. serverless | PARTIAL (local/docker; jupyter/e2b stubs) |
| Remote/S3 filesystem | — | yes | — | yes | ABSENT |
| Chat channels | — | — | 10+ | 6 | PARTIAL (telegram/slack/email/discord) |
| MCP serve (as server) | yes | — | yes | yes | PARTIAL (DIY helper) |
| NL scheduling + delivery | — | — | automations | cron+delivery | PARTIAL (cron only) |
| TUI | — | CLI | yes | yes | ABSENT (`tinker` REPL) |
| Studio / no-code | yes | — | WebUI | — | ABSENT |
| Trajectory export/training | — | — | — | yes | PARTIAL (`eval:capture` only) |

## WS0 — Posture backbone (do first; no behavior change)

1. `src/agentkit/posture.py` (new):
   - `class Posture(StrEnum): SPECIALIZED="specialized"; HYBRID="hybrid"; FREE="free"`.
   - `@dataclass PostureProfile`: `preamble: str`, `layers: dict[str,bool]` (feeds
     `full()` kwargs), `settings_overrides: dict[str, Any]`,
     `policy_factory: Callable[[], ToolPolicy]`, optional `budget`.
   - `POSTURES: dict[Posture, PostureProfile]` populated from the matrix;
     `register_posture(name, profile)` + `resolve_posture(name)`.
2. `policy.py`: add `SPECIALIZED_DENY` (web_search/web_fetch/x_search/run_code/
   send_email/send_to/broadcast), `specialized_policy()`, `free_policy()`
   (narrower approval set); keep `default_policy()` untouched.
3. `config.py`: `agent_posture: Posture = Posture.HYBRID`; plus new flags listed
   per workstream below (all default-off / behavior-preserving).
4. `foundation/agent.py`:
   - `Agent.posture(name)`, `.specialized()`, `.free()` set `self._posture`.
   - `full()` reads the profile when explicit args are omitted: layer booleans
     default to profile values; `safety=True` uses `profile.policy_factory()`;
     prepend `profile.preamble` as instructions. Idempotent via existing
     `_full_layers`.
   - Precedence rule (document + test): explicit arg > builder method > posture >
     settings flag.
5. `foundation/application.py`: `App.posture(...)`; seed posture into `Deps` extras
   so toolkits see it.
6. Introspection: `webui/introspect.py` `stack_view` + `cli/commands/inspect.py`
   report the active posture and the (profile-derived) enabled layers.
7. `foundation/scaffold/full.py`: `--posture` option; generated `assistant.py`
   uses `.posture("<name>").full()`; keep `tests/test_foundation_scaffold.py`
   subprocess boot green.
8. Tests `tests/test_posture.py`: matrix defaults; explicit-arg override; preamble
   present; policy per posture; inspect reports posture; `hybrid` == current
   `full()` tool set.

## WS-DX — Laravel front door (land early to avoid churn)

Goal: the pasted .NET-ish bootstrap becomes a ~3-line Laravel-style one, and the
docs lead with that path.

1. **Naming + container.** Add `Application` as the canonical class; keep
   `App = Application` alias and all existing signatures. Settings `App(...)`
   keeps working.
2. **Fluent boot.** `Application.configure(name=None, settings=None,
   base_path=None).withProviders([...]).withConfig(...).create()` in
   `foundation/application.py`; `name`/`settings` auto-detected from
   `config/app.py` and env when omitted.
3. **Auto-discovery** (new `foundation/discovery.py`):
   - providers: every `Provider` subclass in `app/Providers/`;
   - config sections: every module in `config/`;
   - agents: every agent definition in `app/Agents/`;
   - channels: every factory in `app/Channels/`;
   - commands: every command in `app/Console/Commands/`.
   Symmetric with the existing package entry-point discovery; side-effect-free at
   import (discovery runs at boot, `Provider.register/boot` order preserved).
4. **Class-based agents.** Add `AgentDefinition` base (in `foundation/agent.py`):
   subclasses declare `name` and `define(self, agent) -> Agent` (builder) and may
   set `posture`. `Agent` subclasses `AgentDefinition` so `Agent.make(...)` still
   returns the builder (backward compatible); discovery auto-builds and registers
   each subclass. `app/Agents/Assistant.py` becomes a class, not a
   `build_assistant()` function + manual `app.agent(...)`.
5. **Facades/helpers promoted.** Update scaffold + docs + examples to use
   `Memory.remember(...)`, `Schedule.cron(...)`, `DB.transaction()`, `config()`,
   `app()`, `dispatch()`, `storage()` as the day-to-day surface; document
   `from pydantic_ai import Agent` + explicit builder under "Advanced / low-level".
6. **Generators.** `make:agent`, `make:provider`, `make:tool`, `make:policy`,
   `make:channel`, `make:command` (`cli/commands/generators.py`), each writing a
   discoverable class into the right `app/` folder (overwrite-guarded, consistent
   with existing `make:*`).
7. **Trim .NET remnants.** Make `repos_factory` and driver overrides
   convention-based (auto-selected from `app/Repositories`/providers) rather than
   constructor args; the explicit params remain as overrides. Lazy `build()` in
   examples where the app can build the agent itself.
8. **Docs/README.** Rewrite the front door (README `## 60-second agent`,
   `docs/guide/getting-started.md`, `introduction.md`, `application.md`) to lead
   with `Application.configure()` + `app/Agents/` + facades; move the explicit
   wiring to an "Advanced" page. Keep the Laravel→agentkit concept map accurate.
9. **Scaffold + tests.** `agentkit new` emits the new minimal `bootstrap.py` and a
   class-based `app/Agents/Assistant.py`; keep
   `tests/test_foundation_scaffold.py` subprocess boot green; add
   `tests/test_discovery.py` (find providers/config/agents/channels/commands;
   auto-registration; explicit args still win) and a `make:agent` test.

## WS1 — Context & memory parity

1. **Ephemeral conversations**
   - `session.py`: `ChatRunner.run/stream(..., persist: bool = True)`; when
     `persist=False`, skip `conversations.get_or_create` / `save_new_messages`,
     use an in-memory conversation, and suppress memory/learning writes.
   - `application.py`: `App.run/stream(..., ephemeral=False)`; `webui/app.py`
     temporary-chat mode; CLI `--ephemeral` on `tinker`/one-shot.
   - Document that tool side effects still occur in ephemeral mode.
   - Tests: no rows written; memory tool no-op; normal path unchanged.
2. **Tool-output offload**
   - `foundation/agent_middleware.py`: `offload_large_outputs(threshold_tokens)`
     middleware — when a tool result exceeds the threshold, write it to
     `<AGENT_HOME>/artifacts/offload/<conversation>/<call_id>.txt` and replace the
     message with a head/tail preview + path; expose `read_artifact(path)` tool.
   - Setting `tool_output_offload_threshold` (default `0` = off; `free` enables).
   - Tests: round-trip (offload → read_artifact returns full text); under-threshold
     passthrough.
3. **Indexed cross-session search**
   - `contracts/search.py`: `SearchIndex` Protocol (`index`, `search`, `remove`).
   - `support/kinds.py`: `DriverKind.SEARCH`, `SearchDriver.FTS`/`SCAN`.
   - Drivers: `fts` (SQLite **FTS5** over `messages`; fallback SQL `LIKE` if FTS5
     unavailable) default, `scan` (current linear scan). New `SearchManager`.
   - DB: FTS5 virtual table + triggers in `db/` schema sync.
   - Wire `toolkits/history.py search_history` and a new `search_sessions` tool;
     add a web UI search box (`webui/*_api.py`, `web/src/routes/`).
   - Tests: ranking/keyword hits; fallback driver; conformance per driver.
4. **Memory nudges**
   - `src/agentkit/nudges.py` (new): listener on `turn.end` that, every
     `memory_nudge_every` turns, proposes review-gated memory writes via the
     existing learning review queue (never auto-persist). Setting default off;
     `free` enables.
   - Tests: cadence; proposals land `proposed`; no writes when off.
5. **Context telemetry**
   - `session.py`: add `context_tokens`, `context_window`, `cache_read_tokens` to
     `ChatResult.usage`; emit a `compaction` stream event (before/after tokens).
   - Surface in `/api/chat`, `/v1/chat/completions` `usage`, `/api/overview`;
     web UI context chart + compaction progress.
   - Tests: fields populated; SSE event emitted.

## WS2 — Multi-agent parity

1. **Speaker selection**
   - `contracts/speaker.py`: `SpeakerStrategy` Protocol (`select(roster, transcript)`).
   - `support/kinds.py`: `DriverKind.SPEAKER`, `SpeakerDriver.ROUND_ROBIN`/
     `MODERATOR`/`ALL`/`SELECTOR`/`MANUAL`; register drivers.
   - `agents/groupchat.py` (new): `GroupChatRunner` — real turn loop over agents
     with a shared transcript, termination (max turns / terminator / consensus),
     `agent.*` events. `GroupChatTopology` delegates to it.
   - `SELECTOR` uses the model to pick the next speaker.
   - Tests: each strategy; termination; transcript recorded.
2. **Manager-led team with ledger**
   - `agents/team.py` (new): `TeamLedger` (facts, plan, task list, per-task
     progress) + `MagenticTeam` that replans and picks next speaker, built on
     `StateGraph`/`Supervisor`; ledger tools (`write_ledger`/`read_ledger`).
   - Tests: ledger maintained across steps; replan on stall; cap on rounds.
3. **Named team presets**
   - `register_team(name, roster, *, kind="groupchat"|"supervisor"|"magentic")` +
     `TEAMS`; `Agent.team("name")`; surface in `inspect`, `/api/info`, Studio.
   - Tests: preset resolves a runner with the right roster.

## WS3 — Execution backends

1. **Code executors** (`executors.py`, `support/kinds.py`):
   - Implement `JupyterExecutor` and `E2BExecutor` (real).
   - Add `SSHExecutor`, `ModalExecutor`, `DaytonaExecutor`, `VercelExecutor`,
     `SingularityExecutor` as optional-extra drivers (lazy import →
     `ConfigurationError` naming the extra, per existing pattern).
   - Add optional `hibernate()`/`wake()` to `contracts/codeexec.py` for serverless
     backends (no-op default).
2. **Filesystem** (`foundation/storage.py`, `contracts/storage.py`,
   `support/kinds.py`): add `S3FileSystem` (`StorageDriver.S3`, extra `s3`) using
   the existing file-tool surface; composite backend already exists.
3. Tests: driver selection; missing-extra error; a fake-backend conformance test
   for the `CodeExecutor` and `FileSystem` contracts.

## WS4 — Training & migration

1. `src/agentkit/trajectory.py` (new): `export_trajectories(owner, path,
   format="jsonl")` emitting (messages, tool calls, tool results, final output,
   model, tokens); `compress_trajectory(...)` (dedupe/truncate tool outputs,
   summarize via `Compactor`). CLI `data:trajectories`.
2. Batch generation: run an `EvalSuite`/dataset through the agent and capture
   trajectories (reuse `evals.capture_turns`).
3. `cli/commands/migrate.py` (new): `agentkit migrate openclaw` importing SOUL.md,
   MEMORY.md/USER.md, `skills/`, command allowlist, channel config, allowlisted
   API keys; `--dry-run` and `--overwrite`; never import unlisted secrets.
4. Tests: JSONL schema; compression shrinks tokens; migration dry-run output.

## WS5 — Surfaces & channels

1. **TUI** (`cli/commands/chat.py`, extra `tui`): `agentkit chat` using Textual —
   streaming, slash commands (`/new`, `/model`, `/sessions`), interrupt, resume;
   falls back to `tinker` when the extra is missing.
2. **Channels** (`gateways/`, `support/kinds.py`, `ChannelDriver`): add
   `mattermost` + `linear` first (API-based), plus a generic signed **webhook**
   channel; then `teams`. Optional extras; per-channel allowlist via existing
   `Gateway.is_allowed`. Add **DM pairing** (code exchange → allowlist) to
   `gateways/base.py`. Document Signal/WhatsApp/WeChat as extension points.
3. **MCP serve builder** (`mcp/server.py`, `cli/commands/`): `serve_agent(agent,...)`
   + `agentkit mcp:serve` exposing the agent's tools and a `chat` tool via FastMCP.
4. **NL scheduling + delivery** (`toolkits/scheduler.py`, `scheduler.py`, models):
   scheduled jobs gain `deliver_to`; a `schedule_from_text(text)` tool parses
   ("every day at 8am send me X") into task + cron via the model; scheduler
   delivers results through the notifier/channel. Setting `automation_delivery`.
5. **Studio MVP** (`webui/studio_api.py`, `web/src/routes/studio`): a form that
   composes an agent/team — posture, persona, instructions, tools/allow-lists,
   channel, schedule — with a live `inspect` preview and save to `config/`. No
   node graph.

## Cross-cutting requirements

- Every new subsystem: contract in `contracts/`, enum in `support/kinds.py`,
  `Manager` subclass, `@register_driver`, `<x>_driver` setting, `App.extend`
  support, `inspect`/`/api/info` reporting, scaffold hint, conformance test.
- Deny-by-default allow-lists; writes approval-gated; audit + `agent.*` events;
  namespaced tool names with a uniqueness test on `_function_toolset`.
- Optional extras added to `pyproject.toml`; lazy imports raise
  `ConfigurationError` naming the extra.
- Export new public names from `src/agentkit/__init__.py`.
- Docs: one guide page per new subsystem (drivers table + "add a driver"),
  a `docs/guide/posture.md`, sidebar entries, README highlights, CHANGELOG
  `Added`. Keep `tests/test_foundation_scaffold.py` green.

## Ordering

1. WS0 posture backbone (no behavior change).
2. WS-DX Laravel front door (land early; it changes bootstrap/scaffold/docs, so
   doing it before the parity work avoids re-churning examples).
3. WS1 context & memory parity.
4. WS2 multi-agent parity.
5. WS3 execution backends.
6. WS4 training & migration.
7. WS5 surfaces & channels (+ Studio MVP).
8. Docs/scaffold/inspect updated continuously with each WS. Posture and DX meet in
   `config/app.py` (`posture = ...`) and in `app/Agents/*` (`posture = ...`).

## Risks & mitigations

- **Posture precedence ambiguity** → single documented rule (explicit > method >
  posture > settings flag) + precedence tests.
- **Auto-discovery "magic" / import-time effects** → discovery runs at boot, not
  import; deterministic order; an explicit `withProviders(...)` still wins;
  `agentkit inspect` lists what was discovered.
- **`App`→`Application` rename churn** → keep `App` as an alias and never break
  existing signatures; add a deprecation note only in docs, not warnings.
- **Class-based `Agent` vs builder confusion** → `Agent.make(...)` stays the
  backward-compatible builder entry; the definition base is additive and
  documented under one page.
- **Ephemeral mode leaks side effects** → suppress conversation/memory/learning
  writes, document remaining tool side effects, test for zero rows.
- **Offload breaks tool semantics** → always expose `read_artifact`; round-trip
  test; head/tail preview.
- **FTS5 unavailable (libSQL variants)** → `scan` fallback driver, capability
  probe at boot.
- **Heavy extras** → lazy import + `ConfigurationError`; core import graph
  unchanged; conformance tests skip without the extra.
- **Prompt bloat** (nudges, ledgers, digests) → caps + importance ranking.
- **Backward compat** → default `hybrid`; all new behavior opt-in; existing tests
  unchanged.

## Validation

- `uv run ruff check src tests` · `uv run mypy src/agentkit` ·
  `uv run pytest --cov=agentkit` (≥70% gate); per-contract conformance suites;
  `web/` build + CLI smoke; scaffold subprocess boot
  (`tests/test_foundation_scaffold.py`); `docs/` build.
- Acceptance: `Agent.make("x").specialized()` produces a constrained,
  egress-free, approval-gated agent; `Agent.make("x").free().full()` produces an
  autonomous agent with memory nudges, offload, self-authoring skills, sandboxed
  code, channels and NL automations — both on the same runtime, selected by
  posture, with `inspect` reporting the active posture.
- Acceptance (DX): a freshly scaffolded project boots from a ~3-line
  `bootstrap.py` with no hand-listed providers; a class in `app/Agents/` is
  registered with no manual `app.agent(...)`; `agentkit make:agent` produces a
  discoverable class; README/docs front door shows the Laravel path first.

## Explicitly deferred / left

- Distributed multi-process / cross-process pub-sub (queue + A2A cover current
  needs).
- Full Studio node-graph editor.
- JS/TS parity; provider-specific quirks.
- Signal/WhatsApp/WeChat channel bridges (documented extension points).

## Open questions

- Channel subset for WS5: implement `mattermost`+`linear`+webhook first (default)
  vs prioritize `teams`/`whatsapp`. Recommendation: mattermost + linear + webhook.
- TUI framework: Textual (extra) vs a Rich-only client. Recommendation: Textual,
  with a Rich fallback.
- Agent class naming: keep `Agent` as the builder (with an additive
  `AgentDefinition` base for `app/Agents/`) vs rename the builder to `AgentBuilder`
  and make `Agent` the definition base (more Laravel, breaking). Recommendation:
  keep `Agent.make(...)` and add `AgentDefinition` (no break).
