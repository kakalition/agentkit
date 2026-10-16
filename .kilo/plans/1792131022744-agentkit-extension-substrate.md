# AgentKit Extension Substrate + Gap-Fill (abstraction-first)

> Plan only. Implementation requires an implementation-capable agent (this plan was produced in Plan Mode).

## Goal

Close the competitive gaps identified against AutoGen / Microsoft Agent Framework, LangChain
DeepAgents, CrewAI, OpenAI Agents SDK, Google ADK, Strands, Letta, Mastra, Agno, PydanticAI and
LlamaIndex — **by introducing a first-class extension substrate** so every gap is expressed as
a registered Spec / Contract / Driver / Studio panel rather than one-off code.

Deliverable boundary chosen by the user: **full end-to-end implementations**, but built on the
backend: contracts + registries + specs + a Studio panel SPI. Extensibility is the primary
design constraint.

### In scope (gaps to fill)
1. Extension backbone (`agentkit.extensions`).
2. Unified Spec layer (agent / team / workflow / eval) + SpecStore + codegen targets.
3. Studio panel SPI (server-declared panels + JSON-Schema renderer + optional rich panels).
4. Playground v2 (streaming, step, cooperative pause, node inspector, trace link).
5. Checkpoint / time-travel (port + drivers + UI).
6. Agent builder + Workflow/graph builder (specs + panels).
7. Browser / computer-use (contract + driver kind + Playwright reference driver).
8. Realtime voice (contract + driver kind + PydanticAI passthrough).
9. Eval UX (datasets + graders + trace grading + panel).
10. Catalog / gallery (contract + sources + install + panel).
11. Codegen targets (python / yaml / json).
12. Docs, exports, version/changelog, tests, builds.

### Explicitly out of scope (confirmed with user)
- **TypeScript/JS** deliverable (no runtime SDK, no generated TS client). Keep a generic
  `CodegenTarget` seam; do **not** register a `typescript` target.
- **Control plane / hosted SaaS / deployment targets / multi-tenant orgs.** Keep the current
  single-owner auth surface unchanged.

---

## Architecture (the abstraction substrate)

Build ON the existing substrate, do not replace it:
`agentkit.contracts.*` (runtime-checkable Protocols) + `agentkit.support.drivers` (global
`(kind,name)` registry) + `agentkit.support.manager.Manager` (+ per-app `extend`) +
`support/kinds.py` `DriverKind`/per-kind enums + `App.extend`.

### Layers
1. **Extension manifest** — `agentkit.extensions.ExtensionManifest`: an object a package/app
   returns to declare what it contributes (specs, panels, actions, catalogs, drivers, codegen
   targets). Registered via Python entry points (`agentkit.extensions` group), the
   `AGENTKIT_EXTENSIONS` env var (`module:callable[,module:callable]`), or
   `app.extensions(*manifests)`. Applied idempotently at `App.boot()`; **load failures are
   isolated and logged, never fatal** (mirror `foundation/fullstack.py` `_never fatal` idiom).
2. **Spec layer** — `agentkit.specs`: a `Spec` protocol + `SpecKind` (`agent|team|workflow|eval`)
   + `SpecRegistry` (kind → pydantic model, JSON Schema, materializer, codegen targets) +
   a `SpecStore` contract with a repository driver over a new `definitions` table.
   `agentkit.studio.TeamDefinition` becomes the `team` spec (public alias kept).
3. **Studio panel SPI** — backend declares `GET /api/studio/specs` (kind → JSON Schema) and
   `GET /api/studio/panels` (panel descriptor: id, title, spec kinds, actions, layout hint).
   The SPA ships ONE schema-driven form/panel renderer + a small build-time `richPanels` map
   (workflow canvas, playground flow viz) keyed by panel id, falling back to the generic
   renderer. No remote code execution.
4. **Run trace port** — `RunEvent` / `RunRecorder` contract; every runner (ChatRunner,
   GroupChatRunner, ManagedTeam, graph executors) can emit a uniform trace. `/api/studio/runs`
   (SSE) + a run-event store back Playground v2 and trace grading.
5. **Checkpoint port** — `CheckpointStore` contract + `CHECKPOINT` driver kind; graph +
   session runners checkpoint through it; UI browses/resumes.
6. **New driver kinds** (contract + `Manager` subclass + `extend` support): `COMPUTER`,
   `REALTIME`, `CHECKPOINT`, `CATALOG`, `DATASET`, `EVAL_GRADER`.
7. **Catalog port** — `Catalog` contract + `CatalogItem` schema + sources (local dir, skills
   registry, git, http index); install targets: definitions store, skills dir, MCP registry.
8. **Codegen targets** — `CodegenTarget` registry; reference targets `python`, `yaml`, `json`.

### Resolved decisions
- **D1** Extension substrate wraps `contracts`/`drivers`/`Manager`; `register_driver` stays the
  low-level escape hatch.
- **D2** Server-declared panels + JSON-Schema renderer + optional rich panels; no remote UI code.
- **D3** TS/JS skipped; `CodegenTarget` supports python/yaml/json only.
- **D4** Control plane / deploy / tenancy skipped.
- **D5** Specs unify in a `definitions` table; `TeamDefinition` retained as the `team` spec +
  public alias; one-time **idempotent** migration copies `team_definitions` rows in.
- **D6** Generalize `session.StreamEvent` into a `RunEvent` contract; keep `StreamEvent` as the
  session subtype for back-compat; runners accept an optional `recorder`.
- **D7** Step/pause is **cooperative**: a `Steppable` protocol (graph + managed) exposes explicit
  `advance()`; groupchat uses run-with-limit + streaming; "pause" maps to approvals/deferred
  tools (already present). No thread suspension.
- **D8** Optional SDKs are import-guarded extras raising `ConfigurationError` naming the extra
  (mirror `executors.py::_missing_extra`); tests skip-guard when the extra is absent.
- **D9** Discovery order: programmatic `app.extensions(...)` > `AGENTKIT_EXTENSIONS` > entry
  points; applied once, guarded by a `_extensions_loaded` flag.

---

## Workstreams (ordered; each = a task list with acceptance)

### WS0 — Extension backbone
Files: `src/agentkit/extensions/{__init__,manifest,registry,discovery}.py`,
`src/agentkit/foundation/application.py` (boot hook + `extensions()`), `src/agentkit/__init__.py`
(exports), `src/agentkit/cli/commands/extensions.py`, `src/agentkit/webui/studio_api.py`.
- `ExtensionManifest(name, version, specs=..., panels=..., actions=..., catalogs=..., drivers=...,
  codegen=...)`; `Extensions` registry with `register_manifest()`, `apply(app)`, `describe()`.
- Discovery via `importlib.metadata.entry_points(group="agentkit.extensions")` +
  `AGENTKIT_EXTENSIONS` env + `app.extensions(*m)`; idempotent; failures logged, not fatal.
- `GET /api/studio/extensions` (list) + CLI `agentkit extensions list`.
- Accept: two manifests register conflicting names → deterministic last-wins + warning; a broken
  extension does not break boot (test); idempotent re-apply.

### WS1 — Unified Spec layer
Files: `src/agentkit/contracts/spec.py`, `src/agentkit/specs/{__init__,base,registry,store}.py`,
`src/agentkit/db/models.py` (`DefinitionRecord`), `src/agentkit/db/repositories/definitions.py`,
`src/agentkit/db/repositories/{container,__init__}.py`, `src/agentkit/studio.py` (re-express
`TeamDefinition` as spec kind `team`; keep `__all__` alias), `src/agentkit/webui/studio_api.py`
(switch CRUD to spec store; keep `/api/studio/teams` back-compat).
- `Spec`: `kind`, `name`, `model_dump_json`, `from_json`, `json_schema()`, `render(target)`.
- `SpecRegistry`: register/get/list + `schema_for(kind)`.
- `SpecStore` contract + `RepositorySpecStore` over `definitions(id, owner_id, kind, name,
  version, spec, created_at, updated_at)`.
- Idempotent migration: on `init_db`/boot, copy `team_definitions` rows → `definitions`
  (`kind="team"`), skip existing; never delete the old table.
- `CodegenTarget` registry with `python` (existing `render_team_code` generalized), `yaml`, `json`.
- Accept: existing `/api/studio/teams` behavior preserved; round-trip JSON; schema emitted for
  each kind; old rows visible after migration.

### WS2 — Agent + Workflow + Eval specs
Files: `src/agentkit/specs/{agent,workflow,eval}.py`, `src/agentkit/graph.py`
(`StateGraph.to_spec` / `from_spec`), materializer registrations.
- `AgentDefinition` (name, instructions, model, tools[], capabilities[], posture, memory/skills
  toggles, output type) → materializes via `Agent.make(...)` into a live agent.
- `WorkflowDefinition` (nodes[], edges[], entry, state schema, per-node agent/function ref) →
  `StateGraph.from_spec` → existing `GraphManager` executors.
- `EvalDefinition` (dataset ref, grader refs, criteria, threshold).
- Each is registered in `SpecRegistry` and gets a materializer.
- Accept: agent spec → runnable agent in tests; workflow spec → graph runs end-to-end;
  eval spec → `EvalSuite` run.

### WS3 — Studio panel SPI (backend + SPA)
Files: `src/agentkit/webui/studio_api.py` (`/specs`, `/panels`, `/actions/{id}`),
`web/src/lib/studio.tsx` (schema-form + panel host), `web/src/routes/studio/*` (refactor
`studio.tsx` into a panel host), `web/src/lib/api.ts`.
- Panel descriptor schema: `{id, title, spec_kind?, actions[], layout, order}`; built-in panels
  registered by core (agents, teams, workflows, evals, catalog, playground).
- SPA: generic JSON-Schema form renderer + `richPanels` map (`workflow-canvas`,
  `playground-flow`, `catalog-browser`); unknown panel → generic renderer.
- Actions are named handlers server-side (`POST /api/studio/actions/{id}`) with a JSON body.
- Accept: adding a new spec kind server-side shows a new builder panel with no SPA rebuild
  (generic case); existing team builder unchanged.

### WS4 — Run trace + Playground v2
Files: `src/agentkit/contracts/run.py`, `src/agentkit/runs.py` (`RunEvent`, `RunRecorder`,
`RunStore`), wire emitters into `session.py`, `agents/groupchat.py`, `agents/team.py`,
`graph.py`, `webui/studio_api.py` (`/api/studio/runs` SSE + `GET /runs/{id}`).
- `RunEvent(kind: start|turn|tool|compaction|checkpoint|approval|error|final, ...)`; keep
  `StreamEvent` as the session subtype (D6).
- Runners accept `recorder=None`; no behavior change when absent.
- Playground v2: token streaming, `advance()` stepping (Steppable), cooperative pause via
  approvals, node inspector (per-turn/tool payload), OTel trace link.
- Accept: a team run streams events; a graph run can step; events persist and replay.

### WS5 — Checkpoint / time-travel
Files: `src/agentkit/contracts/checkpoint.py`, `src/agentkit/checkpoints.py`
(`CheckpointStore`, `CheckpointManager`, memory + repository + file drivers),
`src/agentkit/support/kinds.py` (`CheckpointDriver`), `graph.py` + `session.py` integration,
`webui/studio_api.py` (`/api/studio/checkpoints`), repo table `checkpoints`.
- `CheckpointStore`: `put(run_id, seq, state)`, `get`, `list(run_id)`, `latest`, `delete`;
  drivers: `memory`, `repository` (default), `file`.
- `CheckpointedGraphExecutor` and `ChatRunner` checkpoint when enabled; UI browses + resumes.
- Accept: run → inspect intermediate checkpoints → resume from one; drivers conform to contract.

### WS6 — Browser / computer-use
Files: `src/agentkit/contracts/computer.py`, `src/agentkit/computer.py` (`ComputerContract`,
`BrowserContract`, `PlaywrightComputer`, `LoopbackComputer`), `src/agentkit/support/kinds.py`
(`ComputerDriver`), `src/agentkit/toolkits/computer.py` (approval-gated tools),
`pyproject.toml` extra `browser`.
- `PlaywrightComputer` import-guarded (`_missing_extra("browser")`); loopback driver for tests.
- Toolkit exposes `browser_goto/snapshot/click/type/screenshot/evaluate` behind approval.
- Accept: contract conformance; `LoopbackComputer` tools work; missing extra raises naming
  `browser`; tests skip-guarded (mirror T9 pattern).

### WS7 — Realtime voice
Files: `src/agentkit/contracts/realtime.py`, `src/agentkit/realtime.py` (`RealtimeSession`,
`PydanticAIRealtime`, `LoopbackRealtime`), `support/kinds.py` (`RealtimeDriver`),
`pyproject.toml` extra `realtime`; wire a surface/channel.
- Contract: `connect`, `send_audio`, `send_text`, `stream_events`, `interrupt`, `close`.
- `PydanticAIRealtime` wraps `pydantic_ai` realtime (import-guarded); loopback for tests.
- Accept: loopback session round-trips events; missing extra names `realtime`; skip-guarded.

### WS8 — Eval UX
Files: `src/agentkit/contracts/eval_dataset.py`, `src/agentkit/evals.py` (extend),
`src/agentkit/graders.py` (`Grader`, exact-match, schema, LLM-judge via model),
`support/kinds.py` (`DatasetDriver`, `EvalGraderDriver`), db tables `eval_datasets`,
`eval_graders`, `eval_runs`, `webui/studio_api.py` + Studio eval panel,
`cli/commands/evals.py` (`dataset`, `grade`).
- `Dataset` (cases) + `Grader` contracts; **trace grading** reuses WS4 `RunEvent`s.
- Accept: dataset CRUD; grade a dataset with each reference grader; grade a stored run trace.

### WS9 — Catalog / gallery
Files: `src/agentkit/contracts/catalog.py`, `src/agentkit/catalog.py` (`Catalog`,
`CatalogItem`, `LocalCatalog`, `SkillsCatalog`, `GitCatalog`, `HttpCatalog`),
`support/kinds.py` (`CatalogDriver`), install targets, Studio catalog panel,
`cli/commands/catalog.py`.
- `Catalog.search/get/install`; install writes into the definitions store / skills dir / MCP
  registry; sources are pluggable drivers.
- Accept: list + install a team spec and a skill from a local source; http/git drivers parse a
  JSON index; install is idempotent.

### WS10 — Codegen targets + spec CLI
Files: `src/agentkit/specs/codegen.py`, `cli/commands/spec.py` (`export`, `import`, `schema`),
Studio export bound to targets.
- Reference targets `python`, `yaml`, `json`; `agentkit spec export <kind> <name> --target yaml`.
- Accept: round-trip export/import for agent/team/workflow specs.

### WS11 — Cross-cutting
- Driver kinds surfaced in `webui/introspect.py` `stack_view` + `cli/commands/inspect.py`.
- Fullstack provider registers new managers (checkpoint, computer, realtime, catalog, eval).
- `pyproject.toml` extras (`browser`, `realtime`) + optional-extra tests skip-guarded.
- Exports in `agentkit/__init__.py`; version bump + `CHANGELOG.md`.
- Docs: `docs/guide/extensions.md` (new), update `studio.md`, add `computer-use.md`,
  `realtime.md`, `catalog.md`, update `evals.md`; `docs/src/lib/nav.ts` entries; docs build.

---

## Data model & migrations
- New tables: `definitions`, `checkpoints`, `run_events`, `eval_datasets`, `eval_graders`,
  `eval_runs` (SQLModel; created by `init_db`; drift handled by `sync_missing_columns`).
- One-time idempotent copy `team_definitions` → `definitions` (`kind="team"`); old table kept
  read-only for one release. No destructive migration.
- Repos: `db/repositories/{definitions,checkpoints,run_events,eval_*}.py`, wired into
  `Repositories.__post_init__` + `repositories/__init__.py`.

## Failure modes & guardrails
- Extension load / apply errors: logged, isolated, never fatal; boot remains idempotent.
- Spec validation: invalid spec → HTTP 422 with the pydantic error; never a 500.
- Optional SDKs absent → `ConfigurationError` naming the extra (`_missing_extra`).
- Run streaming: recorder errors are swallowed; a failed run still returns a final event.
- Checkpoints: bounded per-run retention (configurable), never unbounded growth.
- Catalog install: validates spec/skill before writing; idempotent; no path escapes.
- Computer tools: approval-gated by default; egress policy respected.
- Back-compat: `/api/studio/teams` and `TeamDefinition` public surface unchanged.

## Validation plan
- `uv run ruff check src tests`; `uv run mypy src/agentkit`.
- `uv run pytest --cov=agentkit` (gate ≥70%); contract conformance tests under `tests/contracts`
  for every new contract; `tests/test_foundation_scaffold.py` canary must stay green.
- Optional-extra tests skip-guarded (present + absent runs).
- `cd web && bun run build` and `cd docs && bun run build` green; new guide pages prerender.
- Manual: Studio shows agents/workflows/evals/catalog panels; a workflow run steps + checkpoints;
  a browser tool call and a realtime loopback session succeed.

## Risks
- **Scope size**: 12 workstreams is large; sequence WS0→WS1→WS3 first (they unblock the rest) and
  land WS6–WS9 as optional-extra drivers so core stays dependency-light.
- **Spec unification** touches `studio.py` + `team_definitions`; mitigate with alias + migration
  + back-compat tests.
- **Step/pause** is cooperative only (D7); document the limitation rather than implying true
  suspension.
- **Playwright/realtime extras** add CI cost; keep them out of the default sync.

## Open questions
- None blocking. Deferred by user decision: TS/JS, control plane, deploy targets, tenancy.
