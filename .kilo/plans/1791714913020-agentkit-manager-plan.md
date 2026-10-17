# agentkit-manager — Implementation Plan

Manage agents built with **agentkit** from one local web app: a registry of agents,
supervised processes (start/stop/restart with live logs), inspection of every
infra surface agentkit writes (conversations, schedules, durable workflows,
usage, audit, A2A), persona/config editing, and the embedded **Phoenix**
observability UI.

## Confirmed decisions

- **Backend:** Python **FastAPI** reusing `agentkit` directly (`durability.client`,
  `repositories`, `scheduler`), driving each agent's `uv` CLI as supervised
  subprocesses.
- **Frontend:** **Vite + React + TypeScript + Tailwind + shadcn/ui** only. All
  primitives come from shadcn; no hand-rolled UI components.
- **Discovery:** auto-discover agentkit agent repos under a configurable
  workspace root, merged with a registry override file.
- **Workspaces:** update **agentkit** to a `~/.agentkit/<agent_name>` workspace
  convention (env override preserved); the manager also injects explicit
  `AGENT_HOME`/ports per supervised instance.
- **Lifecycle:** manager supervises child processes with captured logs.
- **Phoenix:** embed the existing local UI (`127.0.0.1:6006`) via iframe, with a
  backend reverse-proxy fallback for frame-header/CSP issues.
- **Features:** all of — registry & discovery, process lifecycle & logs,
  conversations & messages, scheduler CRUD, durable workflows, usage & tokens,
  audit & A2A, persona/config/artifacts, Phoenix.

## Non-goals

- No auth / multi-user / remote hosting (loopback-only, single local operator).
- No rewriting agent domain logic; the manager treats agents as external
  processes with a CLI and a DB.
- No new agentkit public API beyond the workspace convention + migration helper.

## Architecture

```
                     ┌─────────────────────────────────────────────┐
   browser ──HTTP──▶ │ FastAPI (agentkit-manager)  :7788           │
                     │  ├ discovery/registry  (scan + overrides)   │
                     │  ├ process supervisor  (uv CLI children)    │
                     │  ├ inspectors (agentkit APIs + SQLite read) │
                     │  └ /phoenix/* reverse proxy (frame-safe)    │
                     └───────┬───────────────┬─────────────────────┘
                             │ subprocess    │ sqlite/libSQL (read-only)
                             ▼               ▼
               uv run --directory <repo> <cli> up|worker|mcp|a2a|bot
                             │ writes
                             ▼
        ~/.agentkit/<agent>/  {<agent>.db | agent.db, dbos.sqlite, artifacts, logs, SOUL.md}
                             │ OTLP
                             ▼
                     Phoenix UI 127.0.0.1:6006  ──iframe──▶ manager
```

Manager state lives in `~/.agentkit-manager/` (`registry.json`, `state.json`,
`logs/`). Frontend dev on `:5173`, proxying `/api` and `/phoenix` to `:7788`.

## Repo layout (`~/Workspaces/agentkit-manager`)

```
agentkit-manager/
  pyproject.toml                 # uv: fastapi, uvicorn, httpx, agentkit (../agentkit, editable)
  README.md
  .env.example
  agents.example.json            # registry overrides template
  src/agentkit_manager/
    __init__.py
    config.py                    # ManagerSettings: workspace_root, state_dir, phoenix_url, ports
    registry.py                  # discovery + override merge + cache
    introspect.py               # run agent CLI to resolve home/db/ports/name
    workspaces.py               # layout helpers + legacy detection/migration
    agentsettings.py            # build AgentSettings for a given home (reuse agentkit)
    inspect/
      __init__.py
      db.py                     # read-only engine/session for an agent's libSQL
      conversations.py          # list/get conversations, messages (decode payload JSON)
      schedules.py              # list/add/update/remove/enable scheduled_jobs
      workflows.py              # durability.client -> list/get/cancel/resume/failed
      usage.py                  # usage totals + per-conversation
      audit.py                  # audit entries + verify()
      a2a.py                    # a2a tasks + agent card probe + peers
      soul.py                   # read/write SOUL.md
      envfile.py                # read/write .env with secret masking
      artifacts.py              # browse agent_home/artifacts
    process/
      supervisor.py             # spawn/stop/restart, port alloc, process table
      logs.py                   # per-service log files + SSE stream
      health.py                 # /healthz, /readyz, port liveness probes
      commands.py               # run arbitrary CLI subcommands, capture output
    api/
      app.py                    # FastAPI app, CORS, static serving of web/dist
      routes_agents.py
      routes_process.py
      routes_data.py
      routes_phoenix.py
    cli.py                      # `agentkit-manager serve` / `discover` / `migrate`
  tests/                        # pytest: discovery, inspectors, API, supervisor
  web/
    package.json                # vite, react, react-router, @tanstack/react-query, tailwind, shadcn
    components.json
    index.html, vite.config.ts, tsconfig.json
    src/main.tsx, App.tsx
    src/components/ui/*         # shadcn-generated ONLY
    src/components/app/*        # page-level composition from shadcn primitives
    src/routes/*.tsx
    src/lib/api.ts, src/lib/utils.ts
```

## Part A — agentkit workspace convention

Files: `src/agentkit/config.py`, new `src/agentkit/workspace.py`, `soul.py`,
`durability.py` (unchanged logic, new default path), `README.md`, `.env.example`,
`tests/`.

1. Add `AgentSettings.workspace_root: Path` (env aliases
   `AGENTKIT_HOME`, `AGENTKIT_WORKSPACE_ROOT`; default `~/.agentkit`), expanding
   `~`.
2. Make `agent_home: Path | None = None` (keep `AGENT_HOME` env override). Add a
   `@model_validator(mode="after")` that, when `agent_home is None`, sets
   `agent_home = workspace_root / agent_name` (expanded). Update the existing
   `agent_home` before-validator to tolerate `None`.
3. Add `workspace_root.ensure()` / keep `ensure_dirs()`; `ensure_dirs()` also
   creates `logs/` (harmless additive). Keep `db_path = agent_home/agent.db`,
   `artifacts_dir`, `resolved_database_url` unchanged.
4. New `agentkit/workspace.py`:
   - `workspace_dir(name, *, root=None) -> Path`
   - `detect_legacy(name) -> Path | None` (checks `~/.local/share/agentkit`,
     `~/.local/share/<name>` for an existing DB/artifacts).
   - `migrate(name, *, root=None, move=True) -> dict` — refuse if target exists;
     move/copy `*.db`, `dbos.sqlite`, `artifacts/`, `logs/`, `SOUL.md`; return a
     summary. Read-only-safe; never deletes when `move=False`.
5. Update `.env.example` and README: document `AGENTKIT_HOME`/`AGENT_HOME` and the
   `~/.agentkit/<name>` layout. Bump `CHANGELOG.md`.
6. Tests: assert default resolution (`agent_name="foo"` → `~/.agentkit/foo`),
   env override still wins, legacy detection, migration moves files. Existing
   tests that pass `agent_home=tmp_path` keep working.

## Part B — update the three agents

- **Artemis** (`~/Workspaces/Artemis`): `config.py` `_default_home()` →
  `~/.agentkit/artemis`; keep `ARTEMIS_HOME`/`AGENT_HOME` alias. Update
  `.env.example`/README.
- **calliope**, **Nudge**: they rely on the new agentkit default
  (`agent_name` already `calliope`/`nudge`), so DBs move to
  `~/.agentkit/calliope/calliope.db` and `~/.agentkit/nudge/nudge.db`. Update
  `.env.example`/README; no code change needed beyond verifying `db_path`.
- Re-run each agent's `uv run pytest` + ruff + mypy; fix any path assertions.
- Provide migration via the manager (Part C) for existing
  `~/.local/share/agentkit/calliope.db` and `~/.local/share/artemis`.

## Part C — manager backend (FastAPI)

1. `pyproject.toml` (uv): deps `fastapi`, `uvicorn[standard]`, `httpx`,
   `pydantic-settings`, `agentkit = { path = "../agentkit", editable = true }`,
   dev `pytest`, `pytest-asyncio`, `ruff`, `mypy`.
2. `config.py` — `ManagerSettings`: `workspace_root=~/.agentkit`,
   `state_dir=~/.agentkit-manager`, `host=127.0.0.1`, `port=7788`,
   `phoenix_url=http://127.0.0.1:6006`, `registry_file`, `vite_origin`.
3. `registry.py` + `introspect.py` — discovery:
   - Scan `workspace_root`/`workspace_root.parent` (configurable) for
     `pyproject.toml` whose deps include `agentkit` (parse with `tomllib`).
   - Derive package + console script from `[project.scripts]` (e.g.
     `artemis = "artemis.cli:main"`).
   - Run `uv run --directory <repo> <cli> version` for liveness, then an
     introspection one-liner importing the agent's `Settings` (fallback
     `AgentSettings`) to print `agent_name`, `agent_home`,
     `resolved_database_url`, `a2a_port`, `mcp_port` as JSON.
   - Merge `registry.json` overrides: `id`, `name`, `enabled`, `agent_home`,
     `a2a_port`, `mcp_port`, `db` filename, `env` extras, `commands` allowlist.
   - Detect `*.db` + `dbos.sqlite` in the resolved home; flag legacy data
     (`workspaces.detect_legacy`). Cache in `state.json` with a manual refresh.
4. `agentsettings.py` — construct an `agentkit.config.AgentSettings` for a
   target home (`agent_home=<home>`), reading the agent `.env`
   (`LIBSQL_URL`/`LIBSQL_AUTH_TOKEN`) so inspectors connect to the right DB,
   local or Turso.
5. `inspect/*`:
   - **db.py**: `create_db_engine(resolved_database_url, auth_token=...)` +
     `Repositories(session, owner_id)` (owner from introspection or `owner`).
   - **conversations.py**: `conversations` list + `messages` per conversation,
     decoding the `Message.payload` JSON into role/content parts.
   - **schedules.py**: read `scheduled_jobs`; write via `scheduler.configure`
     then `schedule_cron`/`schedule_once`/`remove_job`; toggle `enabled`.
   - **workflows.py**: `durability.client(settings)` →
     `list_workflows`/`retrieve_workflow().get_status()`/`cancel_workflow`/
     `resume_workflow`; `failed_workflows()` dead-letter view.
   - **usage.py**: `UsageRepo.totals(since=...)` + per-conversation grouping.
   - **audit.py**: `AuditRepo.entries()` + `verify()`.
   - **a2a.py**: `a2a_tasks` list/get; probe the A2A card
     (`/.well-known/agent-card.json`) and MCP `/healthz` when running.
   - **soul.py / envfile.py / artifacts.py**: read/write `SOUL.md`; read/edit
     `.env` with secret values masked on read and only overwritten when provided;
     list files under `artifacts/`.
6. `process/supervisor.py` — per agent, per service (`worker`, `a2a`, `mcp`,
   `bot`, and `up` as the "all" preset):
   - Spawn `uv run --directory <repo> <cli> <service>` with
     `start_new_session=True`, env = base env + `AGENT_HOME=<home>` +
     `A2A_PORT`/`MCP_PORT` (registry- or auto-allocated, checking port liveness)
     + registry `env`; stdout/stderr → `state_dir/logs/<id>/<service>.log`.
   - Track `{id, service, pid, pgid, started_at, status, exit_code}` in
     `state.json`; stop via `SIGTERM` to the process group with a timed `SIGKILL`
     fallback; restart = stop+start. Reconcile stale PIDs on startup.
   - `commands.py`: run a whitelisted one-off `<cli> <args...>` (e.g. `report`,
     `import`, `chat` non-interactive) and return captured output.
7. `process/logs.py` — SSE endpoint tailing a log file (`tail -f` semantics via
   polling) and a "last N lines" REST read.
   `health.py` — TCP liveness on the A2A/MCP ports + HTTP `/healthz`,`/readyz`.
8. `api/app.py` + routes — REST + SSE:
   `GET /api/agents`, `POST /api/agents/refresh`, `GET /api/agents/{id}`,
   `POST /api/agents/{id}/services/{svc}/{start|stop|restart}`,
   `GET /api/agents/{id}/logs/{svc}` (+ SSE), `GET /api/agents/{id}/health`,
   `GET /api/agents/{id}/conversations[/{conv}/messages]`,
   `GET/POST/PATCH/DELETE /api/agents/{id}/schedules`,
   `GET /api/agents/{id}/workflows` (+ `POST .../{wf}/cancel|resume`),
   `GET /api/agents/{id}/usage`, `GET /api/agents/{id}/audit` (+ `/verify`),
   `GET /api/agents/{id}/a2a`, `GET/PUT /api/agents/{id}/soul`,
   `GET/PUT /api/agents/{id}/env`, `GET /api/agents/{id}/artifacts`,
   `POST /api/agents/{id}/commands`, `GET /api/migrate/preview`,
   `POST /api/migrate`. Serve `web/dist` at `/` when built.
9. `routes_phoenix.py` — `GET /api/phoenix/status` (probe 6006) and
   `ANY /phoenix/{path:path}` reverse proxy to `phoenix_url` stripping
   `X-Frame-Options`/`CSP frame-ancestors` and rewriting `Location` so the iframe
   always frames; support websockets if Phoenix uses them.
10. `cli.py` — Typer: `agentkit-manager serve`, `discover`, `migrate <name>`.

## Part D — manager frontend (Vite + React + shadcn)

1. Scaffold: `bun create vite web --template react-ts`; add Tailwind per the
   shadcn Vite guide; `npx shadcn@latest init` (`components.json`, `lib/utils`).
2. **shadcn skill**: install the shadcn skill via the skills CLI
   (`npx skills find shadcn` → `npx skills add <pkg> -g -y`); if unavailable, use
   the official shadcn MCP/CLI docs. Follow it for every UI decision.
3. Add shadcn components only: `button card table badge tabs sidebar sheet dialog
   alert-dialog input textarea label select switch dropdown-menu tooltip
   separator scroll-area progress skeleton sonner alert breadcrumb collapsible
   popover command calendar chart form`. Use the **sidebar** block for nav and the
   **dashboard** block as the layout base.
4. Router (`react-router`) + TanStack Query + SSE hook for logs.
   - `/` Dashboard: agent cards (Card/Badge) with running/health status, service
     toggles, quick links to Phoenix.
   - `/agents/:id` Tabs: Overview, Services, Logs, Conversations, Scheduler,
     Workflows, Usage, Audit, A2A, Persona, Config, Artifacts, Commands.
   - `/observability`: Phoenix iframe page (status Alert when down; "open
     externally" button; fall back to `/phoenix` proxy if the direct iframe
     refuses).
   - `/settings`: workspace root, registry file, Phoenix URL, refresh/migrate.
5. **Component discipline:** no bespoke primitives in `components/ui` (generated
   by shadcn); `components/app/*` only composes shadcn primitives + layout.
   Tables/lists/dialogs/toasts all use the shadcn components above.

## Part E — data flow & key behaviors

- Registered agent → introspection (cached) → home/DB/ports → inspector reads.
- Start service → supervisor spawns with injected env → logs stream via SSE →
  health polls update status badges.
- Scheduler writes go through `agentkit.scheduler` (DB rows are the source of
  truth); the agent's `worker` executes them.
- Workflows are read via `durability.client(settings)` against
  `<home>/dbos.sqlite`; cancel/resume are pass-through to DBOS.
- Only the `web/dist` build + `:7788` API are exposed; loopback only.

## Failure modes & risks

- **Phoenix iframe blocked** (`X-Frame-Options`/CSP): fall back to the
  `/phoenix/*` proxy; last resort, "open in new tab". Verify early.
- **Port collisions** (agents default to A2A `:9000`, MCP `:8765`): manager
  allocates/overrides `A2A_PORT`/`MCP_PORT` per agent; registry can pin them.
- **DBOS schema drift**: read workflows through `durability.client`, not raw SQL;
  pin `dbos` to agentkit's range.
- **Concurrent DB access**: open agent DBs read-only with WAL/busy-timeout
  (agentkit engine already sets these); never write agent DBs except via
  documented repos (schedules) with the same lock semantics.
- **Secret leakage**: `/env` masks secrets on read and never echoes them in logs;
  audit-log and log redaction already exist in agentkit.
- **Agent CLI differences** (only Artemis exposes `workflows`/`schedule-*`): the
  manager uses agentkit APIs, not agent CLIs, for inspection, so it works for all
  three uniformly.
- **Remote/Turso DBs**: token read from the agent `.env`; if absent, surface a
  clear "cannot read DB" state rather than failing the whole page.
- **Killing wrong process**: track `pgid` and verify liveness before acting.

## Validation

- agentkit: `uv run pytest`, `uv run ruff check src tests`, `uv run mypy src/agentkit`.
- each agent: `uv run pytest` (+ smoke where present) after the workspace change.
- manager backend: `uv run pytest` (temp workspace fixture: discovery, inspectors
  against a seeded SQLite, API via `httpx`/TestClient, supervisor start/stop of a
  stub command) + ruff + mypy.
- manager frontend: `bun run build`, `tsc --noEmit`, eslint; no component outside
  shadcn primitives.
- End-to-end smoke (temp `AGENTKIT_HOME`): discover → migrate legacy → start
  `worker` → see logs → create a cron job → list workflows → embed Phoenix status.

## Ordered task list

1. agentkit: `workspace_root` + `agent_home` default + `workspace.py`
   (detect/migrate) + tests + docs/changelog.
2. Update Artemis/calliope/Nudge defaults + docs; run their test suites.
3. Scaffold `~/Workspaces/agentkit-manager` (uv backend skeleton + `web/` Vite
   React TS + Tailwind).
4. Install the shadcn skill; `shadcn init` + add the component set; build the
   sidebar/dashboard shell.
5. Backend: `config`, `registry`/`introspect`, `agentsettings`, `inspect/*`.
6. Backend: `process/*` (supervisor, logs/SSE, health, commands) + reconcile.
7. Backend: FastAPI routes (agents, process, data, phoenix proxy) + static serve;
   Typer CLI.
8. Frontend: Dashboard + Agent detail tabs wired to the API; SSE logs; Phoenix
   page.
9. Persona/config/artifacts/commands pages; migration UI.
10. Tests (backend + frontend build), lint/typecheck, end-to-end smoke; README.

## Open questions / out of scope

- Registry file location (`~/.agentkit-manager/registry.json` assumed) and whether
  to git-track `agents.json` — assumed override-only, untracked, template
  committed.
- Frontend package manager: **bun** assumed (available); npm fallback.
- Manager port `7788` and no-auth loopback assumed.
- Multi-instance-per-agent (two homes for one agent) is supported by registry
  overrides but not surfaced as a first-class UI concept initially.
