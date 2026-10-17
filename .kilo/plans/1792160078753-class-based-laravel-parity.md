# agentkit — full class-based Laravel parity (rearchitecture)

Sequel to `1791722900826-agentkit-laravel-facade-plan.md`. That plan built the
substrate (`App`/`Provider`/`Facade`/`Container`/fluent `Agent`/thin `Model`). This
plan finishes the job so **everything the app author touches is a class, with
Laravel ergonomics** — not functions, closures, or bare strings.

Read the premise literally: agentkit is an **all-in-one agent framework, not an
HTTP framework**. There is no request/response web app to mirror, so Laravel's
`Controller`/`FormRequest`/`JsonResource`/routing layer is **out of scope**. The
agent's real callable surface is **tools** and **channels**, and those — not
routes — are where Laravel's controller ergonomics must land.

## Goal

Every author-facing concept is a class with Laravel-expressiveness:

- **Eloquent-class models**: relationships, eager loading, casts, accessors/mutators,
  scopes, observers/model events, soft deletes, collections, pagination, factories,
  seeders, class-based migrations.
- **Class-based Console**: `Command` with a `signature` string, `handle()` with
  container injection, arguments/options, output helpers — and **all ~24 built-in
  `cli/commands/*.py` modules converted** to it.
- **Event/Listener classes** (not string names + loose payloads), with
  `ShouldQueue`/`ShouldBroadcast`, discovery, and `Event::fake()`.
- **Middleware classes** with groups/aliases.
- **ValidationRule classes** + `Rule` objects + a `Validator` (string rules stay as
  sugar).
- **Gate/Policy** authorization over tools, models, and channels.
- **Tools, Toolkits, and Channels as classes** (the controller analogue).
- **Queued units**: `ShouldQueue` listeners/notifications, job batches/chains.
- **Testing fakes** (`Event::fake`, `Queue::fake`, `Notification::fake`,
  `Cache::fake`, `Gate` assertions).

## Locked decisions

1. **Additive.** Existing exports, modules, the async engine, `Repositories`,
   `session_scope`, and the `~/.agentkit/<agent>` layout keep working. New surface
   is a strict superset; built-in CLI command *names/behavior* are preserved.
2. **ORM foundation: extend SQLModel/SQLAlchemy in place.** No new ORM dependency,
   no replacement of `db/models.py`. Relationships/casts/collections are built over
   the existing async session + `Model`.
3. **Console stays hosted on Typer/Click.** A Laravel `signature` string is compiled
   to a Click command; the top-level Typer app remains the dispatcher.
4. **Tools/Toolkits/Channels become classes**, but function/decorator forms keep
   working (PydanticAI-native) during migration.
5. **Gate/Policy subject = tools + models + channels.** Owner/role checks against
   the run's `Actor`. Supersedes `ToolPolicy`'s role logic but `ToolPolicy` keeps
   working.
6. **Helpers stay.** Laravel ships global helpers (`config()`, `env()`, …); so does
   agentkit. Primary API is class-based; helpers are thin sugar over it.
7. **Convention dirs** (discovery already exists in `foundation/discovery.py`):
   `app/Models/`, `app/Events/`, `app/Listeners/`, `app/Policies/`, `app/Tools/`,
   `app/Toolkits/`, `app/Channels/`, `app/Console/Commands/`, `app/Providers/`,
   `config/`, `database/factories/`, `database/seeders/`, `database/migrations/`.
8. **Migration is staged**, one workstream at a time; no big-bang. Clients
   (nudge → calliope → artemis) migrate last.

## Non-goals

- HTTP Controllers / FormRequests / API Resources / route model binding / HTTP
  middleware groups — **explicitly excluded** (not a web framework).
- Replacing FastAPI (internal web UI), MCP, or A2A transports.
- Replacing the PydanticAI agent core, DBOS durability, or Alembic-free schema init
  (class-based migrations are additive over it).
- Multi-tenant auth or hosted deployment.

---

## Parity matrix — current vs target

| Concern | Today (evidence) | Target |
|---|---|---|
| Models | `foundation/model.py` thin: equality filters + CRUD; docstring "It is not Eloquent" | Full Eloquent: relationships, eager load, casts, mutators, scopes, observers, soft deletes, `Collection`, `Paginator`, factories, seeders |
| Migrations | schema auto-create (`db/engine.py`, `init_db`) | `Migration` classes (`up()`/`down()`) + `Schema` builder (additive) |
| Console | `cli/commands/*.py` = Typer **functions**; `Command` stub `run(app)` (`foundation/commands.py:21`) | `Command` class: `signature`, args/options, `handle()` + DI, output helpers; **built-ins converted** |
| Events | `app.on("turn.end", listener)` strings; `Event` dataclass, `Listener` base (`foundation/events.py`) | Event **classes** (`TurnEnded`, …) + `Listener` subclasses + `ShouldQueue` + discovery + fakes |
| Middleware | factory **functions** returning closures/`Hooks` (`foundation/middleware.py:118`) | `Middleware` classes + groups/aliases + provider `middleware()` registration |
| Validation | string rules + static `Rule` factories (`foundation/validation.py:185`) | `ValidationRule` ABC + `Rule` objects + `Validator`; strings stay sugar |
| Authorization | absent (only `ToolPolicy` RBAC, `policy.py:21`) | `Gate` + `Policy` classes + discovery + `authorize()`/`can()` helpers |
| Tools | plain functions / `@agent.tool`; `attach_*` toolkit functions (`toolkits/__init__.py:80`) | `Tool` class (schema + `handle()` + DI) + `Toolkit` class + discovery |
| Channels | `Gateway` class exists (`gateways/base.py:28`); registration via factory funcs | `Channel` classes + discovery + provider `channel()` typed concern |
| Queued units | `Job`/`Queue` class-based ✓ | + `ShouldQueue` listeners/notifications, batches/chains, job middleware |
| Notifications | class-based ✓ (`foundation/notifications.py:56`) | + `ShouldQueue`, on-demand channel methods, fakes |
| Testing | none | `Event::fake`, `Queue::fake`, `Notification::fake`, `Cache::fake`, `Gate` asserts, factory `make/create`, time travel |

---

## Object model (target)

```
app/
  Models/         → Eloquent Models (relationships, scopes, casts, soft deletes)
  Tools/          → Tool classes (the "controller action" analogue)
  Toolkits/       → Toolkit classes (grouped tools)
  Channels/       → Channel classes (gateway transports)
  Events/         → Event classes          Listeners/ → Listener classes
  Policies/       → Policy classes         Providers/ → Provider classes
  Console/
    Commands/     → Command classes (signature + handle)
  Providers/      → register()/boot(), bindings, policies(), middleware()
config/           → Section classes
database/
  migrations/     → Migration classes (up/down)
  factories/      → Factory classes
  seeders/        → Seeder classes
```

Facades to add (extend `foundation/facades.py`): `Gate`, `Bus` (batch/chain), plus
`DB`, `Cache`, `Storage`, `Queue`, `Events`, `Memory`, `Schedule`, `Log`,
`Feedback` already exist. Helpers to add: `policy()`, `authorize()`, `can()`,
`tool()`, `validator()`.

---

## Phased task list

### WS0 — foundation primitives (no behavior change)
1. `foundation/signature.py`: parse a Laravel signature (`"make:model {name} {--force} {--F|full}"`) → argument/option schema; compile to a Click command.
2. `foundation/casts.py`: `Cast` ABC + built-ins (`int`, `float`, `bool`, `datetime`/`date`, `json`/`array`, `encrypted`, `AsCollection`).
3. `foundation/collection.py`: `Collection` (map/filter/pluck/groupBy/each/…) + `CursorCollection`; return from queries/relationships.
4. `foundation/validation.py` (extend): `ValidationRule` ABC (`validate(attribute, value, fail)`), `Rule` object factory (`required`, `in_`, `unique`, `exists`, `regex`, `between`, …); keep string→predicate compilation as sugar; add `Validator` class.
5. `foundation/gate.py`: `Gate` (define/allows/denies/authorize/for_user), `Policy` base, ability→policy resolution, discovery from `app/Policies/`.
6. `foundation/pagination.py`: `Paginator` / `LengthAwarePaginator` (items, total, per_page, links, `to_dict`); keep the current dict return as a compat shim.
7. `foundation/events.py` (extend): `ShouldQueue`/`ShouldBroadcast` marker mixins; keep `Event`/`Dispatcher` working with strings (dual dispatch).
8. Re-export additively from `foundation/__init__.py` and `agentkit/__init__.py`.

### WS1 — Eloquent models (over SQLModel/SQLAlchemy in place)
9. `foundation/model.py` (extend) — relationships: `has_many`, `has_one`, `belongs_to`, `belongs_to_many`, `has_many_through`; lazy + eager (`with_`, `load`, `load_missing`) with an N+1 guard in debug.
10. Casts + accessors/mutators: `casts = {...}` dict and `Attribute` descriptors; `appends`; serialize with casts applied.
11. Scopes: local `scope_*` methods + `GlobalScope` classes; `without_global_scope`; `with_trashed`/`only_trashed`/`restore`/`force_delete` via `SoftDeletes` mixin.
12. Observers + model events (`retrieved/creating/created/updating/updated/saving/saved/deleting/deleted`); `Observer` class; dispatch through the event bus.
13. Mass assignment (`fillable`/`guarded`), `firstOrCreate`/`updateOrCreate`/`upsert`/`chunk`/`cursor`, `Query` extended with `whereIn`/`whereNull`/`whereBetween`/`when`/`with`.
14. `foundation/factory.py`: `Factory` (definition/state/afterCreating/make/create/count) + `HasFactory` trait; `foundation/seeder.py`: `Seeder` base + runner; `db:seed` command.
15. `foundation/migration.py`: `Migration` (`up`/`down`) + `Schema` builder (create/table/drop/add/drop_column over SQLAlchemy); a `MigrationRepository` table and `migrate`/`migrate:rollback` commands. Existing `init_db` auto-create stays as the default when no migrations exist.
16. Wire relationships to the ambient session (`foundation/db.py` scopes) so `Model` works inside `DB.transaction()` and inside tools.

### WS2 — class-based Console (convert built-ins)
17. Replace the `Command` stub (`foundation/commands.py`) with a full base: `signature`, `description`, `aliases`, `hidden`, `handle()` (container-injected, sync/async), `output()` (`info`/`error`/`warn`/`table`/`ask`/`confirm`/`progress`), `argument()`/`option()`.
18. `foundation/console.py`: a `Kernel`/registry that collects commands from providers + `app/Console/Commands/`, compiles each `signature` to Click, and installs them on the Typer app; groups via `namespace:` prefixes. DI resolves `handle()` params (`App`, repositories, services, `Gate`).
19. **Convert all built-in `cli/commands/*.py`** (auth, catalog, core, credentials, data, evals,
    extensions, generators, inspect, knowledge, learning, memory, ops, queue, runtime,
    schedule, skills, spec, surfaces, training, webhooks, workspace) to `Command`
    subclasses with equivalent signatures; keep command names/flags identical.
20. `foundation/generators.py` + `make:*` emit the new class forms (`make:model`,
    `make:command`, `make:event`, `make:listener`, `make:policy`, `make:tool`,
    `make:toolkit`, `make:channel`, `make:migration`, `make:factory`, `make:seeder`).

### WS3 — Events & Listeners as classes
21. Define event classes for real seams: `Booted`, `TurnStarted`, `TurnEnded`, `ToolStarted`, `ToolEnded`, `ApprovalRequested`, `ChannelMessageReceived`, `GuardrailsFlagged`, `JobProcessed`/`JobFailed`, `ScheduleRan`, `MemoryWritten`, `SkillLoaded`. Emit these alongside the existing string names (dual dispatch) so listeners can `listen(TurnEnded, ...)`.
22. Listener discovery from `app/Listeners/` (class-based `Listener` with `handle(Event)`); auto-wire by `event` attr or a `#[listens(TurnEnded)]`-style marker.
23. `ShouldQueue` listener/notification support: dispatch onto the durable queue; `ShouldBroadcast` → webhook/realtime fan-out.
24. `Event::fake()` / `Event::assertDispatched(...)` testing helpers.

### WS4 — Middleware classes
25. `foundation/middleware.py` (extend): keep the `Middleware` base; add groups/aliases, `app.middleware(Group(...))`, per-turn and per-tool middleware registration via provider `middleware()`; port `logging`/`policy`/`guardrails` factories to thin classes implementing `Middleware`.

### WS5 — Validation classes
26. Integrate `Validator` + `ValidationRule` with tool-input validation and job payloads; `Rule::unique(Note, "name")`/`Rule::exists(...)` backed by the active repositories; expose `validator()` helper and a `ValidatesRequests`-like mixin for tools/jobs. Strings keep working.

### WS6 — Authorization (Gate/Policy)
27. `Gate` facade + `policy()`/`authorize()`/`can()` helpers; `Policy` classes with abilities `viewAny/view/create/update/delete/restore/forceDelete` for models, `run` for tools, `handle` for channels.
28. Discovery from `app/Policies/`; register via provider `policies()`; map model→policy, tool name→policy, channel name→policy.
29. Supersede `ToolPolicy` role checks with `Gate` (keep `ToolPolicy` as an adapter).

### WS7 — Tools, Toolkits, Channels as classes
30. `foundation/tool.py`: `Tool` class (`name`, `description`, `schema()`/annotations, `handle(...)` with DI, `requires_approval`, `cache_ttl`, `timeout`), `ToolGroup`; builder `.tool(SomeTool)` + provider `tools()`; discovery from `app/Tools/`. Function tools keep working.
31. `foundation/toolkit.py`: `Toolkit` class (`tools()`), replacing `attach_*` functions; convert built-in toolkits (`database`, `scheduler`, `queue`, `notifications`, `history`, `usage`, `knowledge_admin`, `skills_admin`) to classes; keep `attach_*` as shims.
32. `foundation/channel.py`: `Channel` class base (extends `gateways.base.Gateway`); discovery from `app/Channels/` (class-based, in addition to the existing factory discovery); `App.channel(ChannelClass)`.

### WS8 — Queued units
33. Job batches (`Bus::batch([...])->then()->catch()`) and chains; job middleware; `Queue::fake()`/assertions. Notifications gain `ShouldQueue`.

### WS9 — Testing ergonomics
34. `Testing` helpers: `Event::fake`, `Queue::fake`, `Notification::fake`, `Cache::fake`, `Gate` assertions, factory `make`/`create`, time travel; a `TestCase` base wiring a booted `App`.

### WS10 — Migrate clients + docs
35. Rewrite **nudge** on the fully class-based API as the reference app (Models, Tools, Events, Commands); assert parity with its existing test suite.
36. Migrate **calliope**, then **artemis**.
37. Update README + a "Laravel-to-agentkit" concept map to cover the new classes; document deprecations (`ToolPolicy` role checks, `attach_*`, function commands).

---

## Back-compat & migration

- New surface is a **superset**; nothing existing is removed in this plan.
- Dual dispatch: string events keep firing while event classes are added.
- Function tools, `attach_*` toolkits, factory-based channels, and the old `Command`
  shim keep working; deprecate, then remove in a later release.
- Built-in CLI command names/flags are preserved exactly; only the implementation
  becomes class-based.
- `AgentApp` stays a shim over `App`.
- Clients migrate one at a time; no coordinated big-bang.

## Risks & mitigations

- **Relationship + async session pitfalls** (detached instances, lazy load outside a
  session): require eager loading when a session isn't ambient; N+1 guard in debug;
  test every relationship inside `DB.transaction()` and inside a tool.
- **Signature parsing vs Click** (variadics, negatable flags, defaults): pin the
  supported grammar (Laravel-familiar subset) in WS0 tests before converting
  built-ins; keep an escape hatch for hand-written Click commands.
- **Migration vs auto-create drift**: only run class migrations when
  `database/migrations/` exists; otherwise keep `init_db`.
- **Mass assignment / casts security**: `guarded` by default for `owner_id`; `encrypted`
  cast uses the existing vault; never log cast values.
- **Import cycles** (`gate ↔ policy ↔ application ↔ facades`): keep foundation
  modules dependency-light; resolve policies/gates lazily via the current app.
- **Discovery side effects**: importing `app/**` modules must stay side-effect-free;
  wrap discovery failures to log-and-continue (as `discover_providers` does).
- **Scope creep**: the largest risk given "everything". Land WS0+WS1 first; each later
  WS is independently shippable and gated by its tests.

## Validation

- Unit tests per WS: signature parsing → Click params; relationship queries equal to
  equivalent raw-repo calls; eager vs lazy load; casts round-trip; scope/soft-delete
  filters; observer/model-event firing order; factory/seeder determinism; migration
  up/down idempotence; command class == old command output; event class payloads ==
  old string payloads; `ShouldQueue` actually queues; Gate allow/deny per ability for
  model/tool/channel; fakes assert dispatch.
- Equivalence test: a converted built-in command produces byte-identical output to its
  pre-conversion version.
- Parity test: nudge (then calliope/artemis) pass their existing suites unchanged.
- Keep gates green: `uv run pytest --cov=agentkit`, `ruff check src tests`,
  `uv run mypy src/agentkit`, bandit; README quickstart examples executable.

## Open questions (decide during implementation; defaults noted)

- Signature grammar breadth (variadics `{names*}`, negatable `{--force}`, arrays) —
  default: full Laravel subset except `{--*}` array options in v1.
- Whether `Collection` is returned by default from `Model.where().all()` or only when
  `->collect()` is called — default: return `Collection` (Laravel behavior).
- Morph relationships (`morph_many`/`morph_to`) — default: defer to a follow-up.
- Migration storage table name (`migrations`) and format (batch number) — default:
  `migrations(name, batch, ran_at)`, Laravel-style batches.
- Whether `ShouldBroadcast` fans out over the existing webhook/realtime subsystem or a
  new broadcaster — default: reuse webhooks + realtime.

## Handoff

Implementation requires source edits; switch to an implementation-capable agent to
execute this plan. Start at WS0 (additive, no behavior change), then WS1.
