# agentkit Web UI — Implementation Plan

Supersedes `.kilo/plans/1791714913020-agentkit-manager-plan.md` (that draft assumed a
separate `~/Workspaces/agentkit-manager` repo + subprocess supervision; the user chose
in-core, self-hosted instead).

## Goal

Ship an operator web UI **inside agentkit core** that is **served automatically by any
agentkit agent while it runs**. It lets the operator *explore* (conversations, chat,
usage, audit, A2A tasks, durable workflows) and *manage* (scheduler CRUD, workflow
cancel/resume, SOUL persona, config, artifacts) **the hosting agent only**. Frontend is
Vite + React + TypeScript + Tailwind + **shadcn/ui** (every UI element from shadcn; no
hand-rolled primitives).

Also adopt the `~/.agentkit/<agent_name>` storage convention and migrate the existing
local agents (Artemis, calliope, nudge) and their data.

## Confirmed decisions

- **Delivery**: the UI backend lives in `agentkit` core (`agentkit.webui`) and is served
  by the agent process itself; `run_all(...)` auto-appends it. No separate manager repo,
  no cross-agent discovery, no subprocess supervision.
- **Scope**: manages **only the hosting agent** via its in-process
  `Runtime` / `Repositories` / `scheduler` / `durability`.
- **Chat**: included. A chat panel sends turns through the agent's own `ChatRunner`
  (persisted to the same durable conversation store).
- **Storage**: `workspace_root` default `~/.agentkit`; `agent_home` defaults to
  `workspace_root/<agent_name>`. Legacy `~/.local/share/...` homes are detected and
  migrated.
- **Frontend stack**: Vite + React + TypeScript + Tailwind + shadcn/ui only.
- **shadcn skill**: install and follow it (it is **not** currently installed — see
  "shadcn skill" below).

## Non-goals

- No auth / multi-user / remote hosting (loopback only, single operator).
- No editing of an agent's Python/domain logic; the UI inspects infra tables and the
  public agentkit APIs.
- No agent-to-agent orchestration UI, no cross-agent dashboard.

## Architecture

```
agent process (`<agent> up`)
  ├─ worker (DBOS)          scheduler.init_scheduler(...)
  ├─ a2a / mcp servers
  ├─ bot (optional)
  └─ webui  ◀── run_all() auto-appends this Service (loopback :8787)
        FastAPI app  (built once, holds runtime + optional `answer`)
          ├─ /api/*        REST + SSE, reuses Repositories/scheduler/durability/soul
          └─ /             serves the built shadcn SPA (fallback page if not built)
        read/write ▼
     <agent_home>/agent.db      (conversations, messages, scheduled_jobs, usage, audit, a2a)
     <agent_home>/dbos.sqlite   (durable workflows)
     <agent_home>/SOUL.md, artifacts/
```

`run_all` appends the webui unless disabled, so **every** agentkit agent gets it with no
per-agent code. Chat is enabled only when the agent passes an `answer` callable (those
that don't still get full inspect/manage).

## shadcn skill

Not installed; `npx skills find shadcn` / `npx skills add <owner/repo@shadcn> -g -y`
(use the `find-skills` skill), or the official shadcn MCP (`npx shadcn@latest mcp`) / CLI
(`npx shadcn@latest init` + `add`). Load the skill before any UI work and follow it for
component choice, registry items, and Tailwind version.

## New / changed files

### A. agentkit storage convention + migration

- `src/agentkit/config.py`
  - add `workspace_root: Path` (alias `AGENTKIT_HOME`, `AGENTKIT_WORKSPACE_ROOT`;
    default `~/.agentkit`, `~` expanded).
  - `agent_home: Path | None = None` (keep `AGENT_HOME` override; `_expand` validator
    must tolerate `None`).
  - `@model_validator(mode="after")`: when `agent_home is None` set
    `workspace_root / agent_name`.
  - `ensure_dirs()` also creates `logs/` (additive). `db_path`, `artifacts_dir`,
    `resolved_database_url` unchanged.
  - add webui fields: `webui_enabled: bool = True`, `webui_host: str = "127.0.0.1"`,
    `webui_port: int = 8787`.
- `src/agentkit/workspace.py` (new)
  - `workspace_dir(name, *, root=None) -> Path`
  - `detect_legacy(name) -> Path | None` (checks `~/.local/share/agentkit`,
    `~/.local/share/<name>` for `*.db`/`artifacts`).
  - `migrate(name, *, root=None, move=True) -> dict` — refuse if target already
    populated; move/copy `*.db`, `dbos.sqlite`, `artifacts/`, `logs/`, `SOUL.md`;
    return a summary. Safe no-op when nothing to migrate.
- `src/agentkit/cli.py` (new) — Typer app: `api`/`webui` (serve standalone),
  `workspace list`, `workspace migrate <name>`. Add `[project.scripts]`
  `agentkit = "agentkit.cli:main"`. Re-export from `agentkit/__init__.py` where useful.

### B. agentkit webui backend

- `src/agentkit/webui/__init__.py` — exports `serve_webui`, `webui_service`,
  `build_webui_app`.
- `src/agentkit/webui/app.py` — FastAPI factory:
  `build_webui_app(*, runtime: Runtime, settings: AgentSettings, answer: Answer | None)`
  - mounts routers under `/api`, serves SPA, loopback `warn_if_exposed`.
  - holds `runtime`, `settings`, `answer`, and a per-request `repositories(runtime)`
    context (the existing process-wide `DB_LOCK`).
- `src/agentkit/webui/introspect.py` — DB reads:
  - conversations: add `ConversationRepo.list(limit, order_by updated_at desc)` and
    `get(id)`; messages via existing `messages.list(id)`.
  - `messages_view(payloads)` — decode with
    `agentkit.session.deserialize_messages` → map parts to
    `{kind, role, text, tool_calls:[{name,args}], ...}`, tolerant of unknown parts.
  - usage: add `UsageRepo.list(limit)` (totals already exist).
  - audit: `AuditRepo.entries(limit)` + `verify()` (exist).
  - a2a: `A2ATaskRepo.list()` / `get()` (exist).
- `src/agentkit/webui/scheduler_api.py` — wraps `agentkit.scheduler`:
  `list/schedule_cron/schedule_once/set_enabled/remove`. Add
  `scheduler.ensure_configured(settings, *, repos_factory)` that configures the module
  runtime **only if unset** (do not clobber a runtime already set by
  `init_scheduler` in the same process).
- `src/agentkit/webui/workflows_api.py` — uses `durability.client(settings)`:
  `list`, `get`, `cancel`, `resume`, `failed` (via `client.list_workflows(status=[...])`).
- `src/agentkit/webui/soul_api.py` — `read`/`write` `<agent_home>/SOUL.md`
  (`agentkit.soul.soul_path`, `DEFAULT_SOUL`).
- `src/agentkit/webui/config_api.py` — non-secret settings + masked secrets
  (`openai_api_key`, `libsql_auth_token`, telegram token, `database_url`).
- `src/agentkit/webui/artifacts_api.py` — list + download files under
  `settings.artifacts_dir` (guard against path traversal).
- `src/agentkit/webui/server.py`:
  - `serve_webui(*, runtime=None, settings=None, answer=None, host=None, port=None)` —
    builds runtime if absent, `uvicorn.run(app, ...)`.
  - `webui_service(*, runtime=None, settings=None, answer=None) -> Service` — factory for
    `run_all`.
- `src/agentkit/supervise.py` — extend
  `run_all(services, *, settings=None, runtime=None, webui_answer=None, webui=True)`:
  when `webui` and `settings.webui_enabled`, append the webui service. Backwards
  compatible (existing `run_all(services)` calls still work).
- `src/agentkit/webui/static/` — built SPA assets (populated by the web build).
- `pyproject.toml` — add `fastapi` (+ `uvicorn` already present) dependency; ensure the
  wheel includes `agentkit/webui/static` (hatchling includes package files; add
  `[tool.hatch.build.targets.wheel]` `artifacts`/include if needed).

REST surface (all under `/api`, JSON):
- `GET /info` — name, version, home, db url (masked), ports, channels, webui on/off.
- `GET /health` — `run_checks`/`db_check(runtime)`.
- `POST /chat` `{conversation_id, text}` → `{output, artifacts, usage}` (501 if no `answer`).
- `GET /conversations`, `GET /conversations/{id}`, `GET /conversations/{id}/messages`,
  `DELETE /conversations/{id}/messages`.
- `GET /schedules`, `POST /schedules`, `PATCH /schedules/{name}`, `DELETE /schedules/{name}`.
- `GET /workflows`, `GET /workflows/{id}`, `POST /workflows/{id}/cancel`,
  `POST /workflows/{id}/resume`, `GET /workflows/failed`.
- `GET /usage` (totals + recent), `GET /audit` (+ `GET /audit/verify`).
- `GET /a2a`, `GET /a2a/{id}`.
- `GET /soul`, `PUT /soul`.
- `GET /config`, `GET /artifacts`, `GET /artifacts/{path}` (download).
- `GET /events` (optional SSE: poll counts/health so the dashboard is live).

### C. agentkit webui frontend (`web/`)

- Scaffold `web/` with Vite `react-ts` (recommend `bun`; `npm` fallback). Tailwind per
  the shadcn Vite guide (`@tailwindcss/vite`), then `shadcn init`.
- Install shadcn components: `sidebar button card table badge tabs input textarea label
  select switch dialog alert-dialog dropdown-menu sheet tooltip separator scroll-area
  skeleton sonner alert breadcrumb collapsible command chart form avatar progress
  popover calendar`.
- `web/vite.config.ts`: proxy `/api` → `http://127.0.0.1:8787` in dev; build output to
  `web/dist` (script copies to `src/agentkit/webui/static/`).
- Router (`react-router`) + `@tanstack/react-query`; layout via the shadcn **sidebar**
  block; theme toggle (shadcn).
- Pages (`web/src/routes/*`, composed only from shadcn primitives):
  - **Overview** — info cards, health badge, quick counts (conversations, schedules,
    workflows, tokens).
  - **Chat** — conversation picker + message list (`ScrollArea`/`Card`) + composer
    (`Textarea`/`Button`); state via query; disabled when `/api/chat` is 501.
  - **Conversations** — `Table`; row opens `Sheet` with decoded messages.
  - **Scheduler** — `Table` + `Dialog` form (cron/once via `Input`/`Select`/`Calendar`)
    + enable `Switch` + `AlertDialog` delete.
  - **Workflows** — `Table`, status `Badge`, `DropdownMenu` cancel/resume, detail `Sheet`;
    failed tab.
  - **Usage** — stat `Card`s + shadcn `Chart` (tokens over time).
  - **Audit** — `Table` + verify `Alert`.
  - **A2A** — `Table` + detail `Sheet`.
  - **Persona** — `Textarea` + Save (`Sonner` toast).
  - **Config** — read-only fields (masked secrets).
  - **Artifacts** — `Table` with download links.
- No logs page (no supervision). Nav hides Chat when unavailable.
- `web/README.md` (or repo script) documenting `bun install && bun run build` and the
  dev proxy.

### D. agents + migration

- **Artemis** (`~/Workspaces/Artemis`): set `agent_name = "artemis"`, drop the custom
  `_default_home` (keep `ARTEMIS_HOME`/`AGENT_HOME` alias via agentkit), rely on
  `~/.agentkit/artemis`. In `up`, pass the runtime + an `answer` to `run_all`
  (reuse the existing A2A `answer` pattern) so the webui is served with chat. Update
  `.env.example`/`README`.
- **calliope / nudge** (`~/Workspaces/{calliope,nudge}`): inherit the new agentkit
  default (their `db_path` overrides already target `<home>/<name>.db`). In `up`, pass
  runtime + `answer` (`_answer` already exists for A2A). Update `.env.example`/`README`.
- **Migrate data**: `uv run agentkit workspace migrate calliope` (moves
  `~/.local/share/agentkit/calliope.db`), `... migrate artemis`
  (`~/.local/share/artemis/*`). Update README/CHANGELOG for the new layout and add a
  legacy-data banner/one-click migrate in the webui Overview when `detect_legacy` hits.

## Data flow & key behaviors

- Agent `up` → `run_all` appends webui → FastAPI holds the agent `Runtime` (shared
  `DB_LOCK`) + `answer`.
- Inspect endpoints read through `Repositories`/`repositories(runtime)`; scheduler writes
  go through `agentkit.scheduler` (DB rows are source of truth; the agent's worker
  executes them).
- Workflows read/inspect via `durability.client(settings)` against `dbos.sqlite`; never
  launch a second DBOS worker.
- Chat runs the same `ChatRunner` path as the CLI, so history/usage are shared.
- Only the SPA + `:8787` API are exposed; loopback only.

## Failure modes & risks

- **Static assets missing** (editable install before `bun run build`): serve a minimal
  fallback page and resolve `web/dist` first, then packaged `static/`.
- **FastAPI dependency**: adds a runtime dep to agentkit core. Alternative is Starlette
  (already a dep) — pick FastAPI for typed routes/models; flag if footprint matters.
- **Scheduler runtime clobber**: webui must not re-`configure` the module scheduler when
  `init_scheduler` already ran — use `ensure_configured`.
- **Port collisions**: default `:8787`; each agent can override `WEBUI_PORT`. Bind
  loopback; `warn_if_exposed`.
- **Chat cost/safety**: chat triggers model calls; loopback + approvals default-deny
  unchanged. Never expose secrets; mask on read; redact logs (agentkit already does).
- **DBOS schema drift**: only via `durability.client`, pin `dbos` to agentkit's range.
- **DB writes**: webui writes only documented repos (schedules, messages-clear, SOUL);
  agent DB remains otherwise read-only; reuse WAL/busy-timeout + `DB_LOCK`.
- **Migration** moves files: refuse non-empty target, never delete on copy mode; tests
  cover it.

## Validation

- agentkit: `uv run pytest`, `uv run ruff check src tests`, `uv run mypy src/agentkit`.
  New tests: default home resolution + env override + legacy detection + migrate; webui
  app endpoints against a seeded temp SQLite (info/health/conversations/schedules/usage/
  audit/a2a/soul/config/artifacts) with a stub `answer`; `run_all` auto-appends webui;
  static fallback when `static/` absent.
- Frontend: `bun run build`, `tsc --noEmit`, eslint; grep `components/ui` is shadcn-only;
  no primitive outside shadcn.
- Agents: run each `uv run pytest` + ruff + mypy after the home change.
- End-to-end smoke: `agentkit workspace migrate` in a temp root; start an agent `up`; open
  `http://127.0.0.1:8787`, send a chat turn, create a cron job, see it in Scheduler, cancel
  a workflow, edit SOUL.

## Ordered task list

1. `config.py` workspace_root + optional `agent_home` + webui fields; `workspace.py`;
   `agentkit/cli.py` + console script; tests + `.env.example`/README/CHANGELOG.
2. Webui backend skeleton: `webui/app.py`, `introspect.py` (+ repo `list` methods),
   routers, `server.py`, `supervise.run_all` integration; backend tests.
3. Frontend scaffold: Vite/React/TS/Tailwind + `shadcn init` (after installing the
   shadcn skill); sidebar shell + router + query; build → `webui/static`.
4. Frontend pages (Overview, Chat, Conversations, Scheduler, Workflows, Usage, Audit,
   A2A, Persona, Config, Artifacts); wire to `/api`.
5. Update Artemis/calliope/nudge defaults + `up` (runtime + answer) + docs; run their
   suites.
6. Migrate existing local data via `agentkit workspace migrate`; add legacy banner in the
   Overview.
7. Full validation (agentkit + web build + agents), README/CHANGELOG, end-to-end smoke.

## Open questions / out of scope

- Backend framework final call: FastAPI (recommended) vs Starlette-only (no new dep).
- Frontend package manager: bun assumed (present); npm fallback.
- Webui default port `8787`; loopback, no auth.
- `.env` editing in the UI: start read-only (`/config` masking) and add write only if
  needed later.
- Whether to commit built `webui/static` (recommended for zero-config editable installs)
  vs build in CI/setup.
