# agentkit as a full-stack agent

## Goal

Make agentkit a **full-stack agent suite**: one agent that ships the entire agent
capability stack, integrated and on by default, the way Laravel ships the entire
web stack. Five parts, all in scope:

1. **Unify** — a single, opinionated way to get the whole suite (`Agent.full(...)`
   + `FullStackProvider` + the default `agentkit new` project).
2. **Complete** — close the three thin/missing capability layers: multi-provider
   models, richer memory, and more channels.
3. **Communicate** — make agent-to-agent communication and modern multi-agent
   patterns first-class: a unified agent registry/handle, a message bus, handoffs,
   and one orchestrator/supervisor.
4. **Replace** — swap hand-rolled code for libraries (Pydantic-ecosystem), per the
   table in Workstream F.
5. **Concurrency** — move to a **full async data layer** and concurrency-safe
   primitives (Workstream G).

"Fullstack" here is the **agent** stack, not a web framework: model layer, memory,
knowledge, skills, tools, planning, multi-agent, interop (MCP/A2A), durability,
HITL, safety, observability, evals, persona, multimodal/audio, channels, sandbox.

## Decisions (locked)

- **Unify API**: fluent `Agent.full(...)` (agent capabilities) + a framework
  `FullStackProvider` (app services), used by the default scaffold.
- **Scaffold default**: `agentkit new` produces the full Laravel-like project;
  `agentkit new --minimal` keeps today's bare skeleton.
- **Complete** these layers: (1) multi-provider model registry, (2) typed memory +
  owner profile + scheduled consolidation, (3) shared `Gateway` base + Slack,
  Email, Discord (Telegram refactored onto the base).
- **Config**: provider config = `MODEL_NAME=provider:model` prefix + per-provider
  env fields.
- **Multi-agent (first-class)**: an `AgentRegistry` + unified `AgentHandle` (local
  agents and remote A2A agents behind one handle); a `Mailbox` message bus with
  `send`/`ask`/`broadcast` (in-process by default, `durable=True` via DBOS
  `send`/`recv`, A2A over the wire for remote handles); a `handoff` that transfers
  control + full transcript (brief opt-in, `max_handoffs` guard); one unified
  `Orchestrator`/`Supervisor` with capability-based routing, fallbacks, and
  `agent.*` lifecycle events.
- **Libraries (Pydantic ecosystem)**: replace hand-rolled code with the libraries in
  Workstream F (`pydantic-graph`, `genai-prices`, `cachetools`, `numpy` +
  `sqlite-vec`, `PyYAML`, `sse-starlette`, `semantic-text-splitter`). Model
  providers stay on PydanticAI-native provider classes (no LiteLLM); PII redaction
  stays local (no Presidio).
- **Concurrency**: migrate to a **full async data layer** — async SQLAlchemy
  sessions everywhere, and a **clean break to async-only** (`async with
  app.repositories()`, `await Model...`; the old sync path is removed, not shimmed).
  Remove the process-wide `DB_LOCK`; keep SQLite single-writer via WAL +
  busy-timeout retry. Concurrency-safe primitives and off-loop blocking work
  (Workstream G).
- **"Like Laravel"**: config-first; sane defaults; the app boots without any
  external account; a feature activates when its config/env is present and stays
  idle (never fatal) otherwise; every layer has an `X_ENABLED` opt-out; the default
  project ships everything wired and you delete what you don't need.

## Out of scope

Realtime/streaming voice, generative UI / AG-UI, and auth/tenancy were explicitly
excluded. Leave the existing file-based `transcribe`/`synthesize` and the
single-operator loopback console unchanged. Also excluded for now (candidates for
a later pass): group chat / manager pattern, reflection / critic loop, parallel
fan-out / map-reduce, and hierarchical / recursive teams. Library swaps explicitly
not adopted: `LiteLLM` (providers stay PydanticAI-native) and `Presidio` (redaction
stays a local regex).

## Design constraints

- `Agent.full()` and `FullStackProvider` are additive: the bare builder/provider
  path may still be used without them. (The async data-layer change in Workstream G
  is the one breaking change; it applies to everything.)
- **Async-first.** The data layer and all I/O are async; blocking libraries
  (embeddings, HTTP, file I/O) run off the event loop. No sync DB path remains.
- Importing providers/providers-of-capabilities must stay side-effect free;
  effects go in `register`/`boot`.
- Optional third-party deps (Slack/Discord) ship as extras; Email uses stdlib
  (`imaplib`/`smtplib`/`email`) and needs no extra.
- New library deps are added to core only when small and pure-Python or optional;
  heavier ones (sentence-transformers) stay extras.
- No new external services; state stays in the local SQLite/libSQL DB.

---

## Workstream A — Unify: `.full()` + `FullStackProvider` + scaffold

**A1. `Agent.full(...)`** — `src/agentkit/foundation/agent.py`
Add a chainable `full()` that expands, in order, to the agent-side capabilities,
each toggleable and idempotent:
```python
def full(self, *, persona=True, memory=True, skills=True, knowledge=None,
         hitl=True, safety=True, workspace=None) -> Agent
```
- `persona` → `.persona()`; `memory` → `.memory()`; `skills` → `.skills()`;
  `knowledge` → `.knowledge(knowledge)` when a path/KB is given.
- `hitl` → `.approvals()` + `.clarify()`; `safety` → `.policy(default_policy())`.
- Respect settings flags (`memory_enabled`, `skills_enabled`, `approvals_enabled`)
  so a disabled layer is silently skipped. `.full()` must not duplicate tools if
  called twice.

**A2. `FullStackProvider`** — new `src/agentkit/foundation/fullstack.py`
The framework "everything wired" provider (the analog of a starter-kit
`AppServiceProvider`). `register()` declares config sections and nothing with side
effects; `boot()` performs effects **only for configured layers**:
- Register config sections for each concern (memory, channels, interop, queue).
- Register a durable `memory:consolidate` schedule (default daily).
- Register gateway channels that are enabled **and** configured (D1–D5).
- Register notifier senders for enabled channels.
- Register MCP registry / A2A only when settings are present.
- Never raise when a layer is unconfigured; log at debug and skip.
Export as `agentkit.FullStackProvider`; add `app.fullstack()` sugar that calls
`app.providers([FullStackProvider])`.

**A3. Scaffold** — `src/agentkit/foundation/scaffold.py`, `src/agentkit/cli.py`
- Split the template set: `MINIMAL_FILES` (today's `_files()`) and a `FULL_FILES`
  overlay. `scaffold_project(name, ..., full=True)` defaults to full.
- `agentkit new` gains `--full/--minimal` (default `--full`).
- Full overlay adds: `app/Agents/assistant.py` using `Agent.make(...).full()`;
  `bootstrap.py` adding `FullStackProvider`; `app/Console/Kernel.py` scheduling
  `memory:consolidate`; `app/Channels/` example; `config/channels.py`,
  `config/memory.py`; `.env.example` documented for all providers/channels;
  README section "The full stack" + opt-out map.
- Keep the bare skeleton selectable and byte-identical for `--minimal`.

**A4. Introspection** — `src/agentkit/cli.py` (`inspect`), `webui/introspect.py`
`agentkit inspect` and `/api/info` report the enabled stack (providers, channels,
memory mode, interop) so "full" is observable.

---

## Workstream B — Complete: multi-provider model registry

**B1. Registry** — new `src/agentkit/model_providers.py`
```python
def resolve_model(name: str, settings) -> Model        # dispatch on "prefix:model"
def register_model_provider(prefix: str, factory)      # extensibility
```
Built-in prefixes → PydanticAI providers: `openai`, `openai-compatible`,
`anthropic`, `google`, `groq`, `mistral`, `ollama`. `register_model_provider`
lets an app add its own. Unknown prefix raises `ConfigurationError` naming the
supported set.

**B2. Settings** — `src/agentkit/config.py`
Add per-provider fields next to the existing OpenAI ones: `anthropic_api_key`,
`google_api_key`, `groq_api_key`, `mistral_api_key`, `ollama_base_url`. Reuse
`openai_api_key`/`openai_base_url`. `MODEL_NAME` stays `provider:model`.
A missing required key for the chosen provider raises `ConfigurationError` with
the exact env var name.

**B3. Refactor `build_model`** — `src/agentkit/config.py:172`
`build_model(settings)` becomes a thin wrapper over `resolve_model(settings.model_name, settings)`;
preserve current OpenAI behavior (timeout/retries via the async OpenAI client) and
`model_settings`/`usage_limits` unchanged.

**B4. Routing + pricing** — `src/agentkit/routing.py`, `src/agentkit/pricing.py`
`ModelRouter` keeps routing by full `provider:model` strings (no change).
`pricing.py` stops hand-rolling prices and becomes a thin wrapper over
**`genai-prices`** (the library PydanticAI uses): `estimate_cost`/`usage_cost`/
`default_pricing` delegate to it, covering every provider in B1. Model without a
known price → tokens recorded, `cost_usd=0.0` (logged once at debug).

**B5. Tests** — `tests/test_model_providers.py`
Resolution per prefix (monkeypatched constructors, no network), missing-key error
message, unknown-prefix error, `ModelRouter` across providers.

---

## Workstream C — Complete: typed memory, profile, consolidation

**C1. Models** — `src/agentkit/db/models.py`
- Extend `Memory` (keep `kind`): add `importance: float = 0.5`,
  `last_used_at: datetime | None`, `access_count: int = 0`,
  `source_conversation_id: str | None`, `expires_at: datetime | None`.
- New `OwnerProfile` table: `owner_id` (PK), `name`, `timezone`, `locale`,
  `preferences` (JSON string), `notes`, `updated_at`.
- Kinds: `fact | preference | person | date | episodic | procedural` (validated in
  the repo, default `fact`). No DB enum — a check in `MemoryRepo`.

**C2. Repositories** — `src/agentkit/db/repositories.py`
- `MemoryRepo`: `add(..., kind, importance, source_conversation_id, expires_at)`;
  `search(query, *, kind=None, limit)` with **hybrid scoring** (normalized
  `w_sim*similarity + w_recency*recency + w_importance*importance`, weights in
  settings); `record_use(ids)` (bump `access_count`/`last_used_at`);
  `expired()`; `near_duplicates(threshold)` (embedding cosine); `merge(canonical,
  others)`; `prune_expired()`.
- New `OwnerProfileRepo`: `get()`, `set(**fields)` (upsert), `merge(**fields)`.
- Attach `profile` in `Repositories.__post_init__`.

**C3. Tools** — `src/agentkit/memory.py`
Extend `attach_memory`: `remember(fact, kind="fact")`, `recall(query, kind=None)`
(records use), `forget_memory(id)`, plus `remember_person`, `update_profile(...)`,
`get_profile()`. The instructions digest shows the profile + typed facts, grouping
by kind. All tools degrade gracefully when the store/embedder is absent.

**C4. Consolidation** — new `src/agentkit/consolidation.py` (memory)
`consolidate_memories(repos, *, embedder=None, duplicate_threshold=0.92, dry_run=False)`:
merge near-duplicates (keep canonical, sum `access_count`, max `importance`),
summarize long same-kind groups into one consolidated memory, and prune
`expires_at < now`. Offline heuristic; optional `model=` for model-based summaries
(mirrors `Compactor`). Register durable task `memory:consolidate`; schedule daily
via `FullStackProvider`; expose `agentkit memory:consolidate [--dry-run]`,
`memory:list`, `memory:forget <id>`, `memory:profile` in `src/agentkit/cli.py`.

**C5. Migration** — reuse `db/engine.py` `sync_missing_columns` (verify it adds
the new `Memory` columns and creates `OwnerProfile`); add a test asserting an
existing DB upgrades in place.

**C6. Tests** — `tests/test_memory_typed.py`, `tests/test_consolidation.py`,
`tests/test_profile.py`.

---

## Workstream D — Complete: channels on a shared Gateway base

**D1. `Gateway` base** — new `src/agentkit/gateways/base.py`
Abstract `Gateway` owning the shared bot concerns, factored out of Telegram:
allow-list check, `run_turn` (runs `app.answer`/`app.stream` against a
conversation id), approval broker (approve/deny via channel UI), live status /
keepalive, markdown-safe send, and a `Service` factory. Each concrete channel
implements `start()`, `send(conversation_id, text)`, `ask_approval(...)`, and an
id→conversation_id mapping.

**D2. Refactor Telegram** — `src/agentkit/gateways/telegram.py`
`TelegramGateway(Gateway)`; keep `is_allowed`, `react_seen`, `send_markdown`,
`run_turn`, `ApprovalBroker` working (re-export) so existing callers/tests pass.

**D3. Slack** — new `src/agentkit/gateways/slack.py`
Socket-mode (`slack_bolt`) bot: channel/thread → conversation id; approval via
message actions. Settings: `slack_bot_token`, `slack_app_token`,
`slack_allowed_channel_ids`. Extra: `agentkit[slack]`.

**D4. Email** — new `src/agentkit/gateways/email.py` (stdlib only)
IMAP poll for inbound (`imaplib`), SMTP reply (`smtplib`), thread keyed by
`Message-ID`/`References`. Settings: `email_imap_host/port/user/password`,
`email_smtp_host/port`, `email_from`, `email_poll_interval_s`,
`email_allowed_senders`. No extra dependency.

**D5. Discord** — new `src/agentkit/gateways/discord.py`
`discord.py` bot: guild channels/DMs → conversation id; approvals via message
components. Settings: `discord_bot_token`, `discord_allowed_guild_ids`.
Extra: `agentkit[discord]`.

**D6. Wiring** — `src/agentkit/gateways/__init__.py`,
`src/agentkit/foundation/notifications.py`, `src/agentkit/foundation/fullstack.py`,
`src/agentkit/config.py`
Register each gateway as an `app.channel(...)` only when enabled **and**
configured; add notifier senders and `Notification.to_slack/to_email/to_discord`;
add the settings fields; each channel starts only if its token/env is present.

**D7. Tests** — `tests/test_gateways_base.py` (base behaviors with a fake
transport), `tests/test_email_gateway.py` (fake IMAP/SMTP), and skips for
Slack/Discord when extras are absent.

---

## Workstream E — First-class agent communication + multi-agent patterns

New package layout: `src/agentkit/agents/` (`registry.py`, `handle.py`,
`mailbox.py`, `handoff.py`) plus a unified `src/agentkit/orchestrator.py`.

**E1. `AgentRegistry` + `AgentHandle`** — `src/agentkit/agents/registry.py`,
`src/agentkit/agents/handle.py`
- `AgentHandle`: name, description, capabilities/skills, plus `invoke(ctx, task)`
  and identity. One handle type wraps **both** a local agent (in-process) and a
  remote A2A peer (wire call via `agentkit.a2a.client`), so callers do not branch.
- `AgentRegistry`: `register(handle)`, `get(name)`, `resolve(query)` (capability/
  skill match), `list()`. Populated from local agents (`app.agent`, specialists,
  Supervisor rosters) and from A2A peers (`peers_file` / settings). Discoverable at
  boot so "which agents exist and what can they do" is first-class.
- Builder sugar: `.subagent(agent, name=, description=, capabilities=[...])` and
  `.agents(registry)` on `foundation/agent.py`.

**E2. `Mailbox` message bus** — `src/agentkit/agents/mailbox.py`
- `Mailbox` keyed by agent name; `send(to, message)` (fire-and-forget),
  `ask(to, message) -> reply` (request/response), `broadcast(message, to=[...])`.
- In-process by default (messages delivered to the running/subscribed agent). A
  `durable=True` mode persists via DBOS `send`/`recv` (wrap the primitives the
  durability module deliberately left unwrapped — `agentkit/durability.py`) so a
  message survives a restart. Remote handles always go over A2A.
- Exposed as tools so the model can talk to peers: `send_to`, `ask_agent`,
  `broadcast`, and `list_agents`. Wired via a builder `.mailbox(...)` / a Mailbox
  attached to `Deps` (`src/agentkit/deps.py`) so tools resolve the bus from context.
- Delivery records `agent.message` lifecycle events (see E4).

**E3. `handoff`** — `src/agentkit/agents/handoff.py`
- `handoff(target, *, brief=None, conversation_id=None, deps=None)` transfers
  control to another agent **in the same conversation**: by default the target
  receives the full transcript (same `conversation_id`, same history); with
  `brief=` it receives a focused brief instead.
- Exposed as a tool (`handoff_to(agent, brief=None)`), on the builder
  (`.handoff_to(agents)`), and as a Python API. Multi-hop chains are capped by a
  `max_handoffs` guard (settings + per-run override) to prevent loops; each hop
  records an `agent.handoff` event (E4). Distinct from delegation, which *returns*
  to the caller.

**E4. Unified `Orchestrator`/`Supervisor`** — `src/agentkit/orchestrator.py`,
`src/agentkit/teams.py`
- Merge `Orchestrator` and `Supervisor` into one implementation (keep both names as
  aliases for backward compatibility), driven by the registry: roster from handles,
  capability/skill-based routing (`route` picks a handle by capability, not just
  name), ordered fallbacks, and `delegate` still forwards `deps`/`usage`/`model`.
- Add lifecycle/communication events on the existing dispatcher
  (`foundation/events.py`): `agent.started`, `agent.finished`, `agent.message`,
  `agent.handoff`, `agent.error` — emitted on delegation, messaging, and handoff so
  multi-agent activity is observable (web console + auditors can subscribe).
- `run_all_agents` becomes a thin use of the registry (map agents → handles).

**E5. Wiring** — `foundation/fullstack.py`, `config.py`, `__init__.py`, `deps.py`
- `FullStackProvider` registers the registry (local + configured A2A peers) and the
  default in-process mailbox at boot; `Agent.full()` attaches the peer tools
  (`send_to`/`ask_agent`/`broadcast`/`list_agents`/`handoff_to`) when
  `subagents_enabled` is set. Remote registration happens only when A2A is
  configured (graceful otherwise). Add `subagents_enabled`, `mailbox_durable`,
  `max_handoffs` settings. Export `AgentRegistry`, `AgentHandle`, `Mailbox`,
  `handoff`, `Orchestrator`, `Supervisor` from `agentkit`.

**E6. Tests** — `tests/agents/`
- Registry resolve by name/capability; handle facade over a local agent and over a
  fake A2A client; mailbox `send`/`ask`/`broadcast` in-process; durable mailbox with
  a stubbed DBOS; handoff transcript-vs-brief and the `max_handoffs` guard;
  orchestrator capability routing + fallbacks; event emission for each `agent.*`.

---

## Workstream F — Replace hand-rolled code with libraries

Each swap keeps the public behavior and tests; only the engine changes. Add deps
to `pyproject.toml` (core when pure-Python/small, extras when heavy).

**F1. `StateGraph` → `pydantic-graph`** — `src/agentkit/graph.py`
Reimplement `StateGraph`/`END`/`GraphError` over `pydantic_graph` (typed nodes,
`Graph.run`, persistence hooks). Keep the existing `add_node/add_edge/
add_conditional_edges/set_entry/run` surface as a thin compatibility wrapper so
`teams`/docs keep working; expose `pydantic_graph`'s durable/persistent run for the
multi-agent workstream. This also lets graphs share PydanticAI's durable-execution
path.

**F2. `validation.py` → `pydantic`** — `src/agentkit/foundation/validation.py`
Keep the Laravel-style `validate(data, rules)` / `Rule` API, but compile rules to
Pydantic (`TypeAdapter`/model validators) and surface `ValidationError` from
Pydantic's errors. Delete the regex/`_BUILTINS` engine; keep `email` via
`pydantic.EmailStr` and `min/max/between/in/one_of/regex` via constraints.

**F3. `pricing.py` → `genai-prices`** — `src/agentkit/pricing.py` (see B4).

**F4. `cached_tool` → `cachetools`** — `src/agentkit/cache.py`
Use `cachetools.TTLCache(maxsize, ttl)` (under an `asyncio.Lock` for concurrent
tasks) instead of the hand-rolled `OrderedDict`; keep the signature/`cache_clear`.

**F5. Vectors → `numpy` + `sqlite-vec`** — `src/agentkit/embeddings.py`,
`src/agentkit/db/repositories.py`, `db/models.py`
- `numpy` for cosine/similarity math and vector packing; `pack_vector`/
  `unpack_vector` become numpy-backed (keep the base64 format for compatibility or
  migrate via a one-time backfill).
- Replace the brute-force Python scan in `MemoryRepo._semantic_search` /
  `KnowledgeRepo._semantic_search` with an indexed search. Prefer **`sqlite-vec`**
  (`vec0` virtual table + `vec_distance_cosine`); fall back to numpy-vectorized
  cosine when the extension is unavailable. libSQL remote may use native
  `F32_BLOB`/`vector_distance_cos` instead — decide by driver support.
- Keep the `hash`/keyword fallback path so no-embedder installs still work.

**F6. Front matter → `PyYAML`** — `src/agentkit/skills.py`, `src/agentkit/prompts.py`
Make `PyYAML` a core dep and delete `_parse_front_matter_minimal`/`_parse_scalar`;
parse with `yaml.safe_load`, erroring clearly on malformed front matter.

**F7. SSE → `sse-starlette`** — `src/agentkit/webui/app.py`
Replace the hand-rolled `StreamingResponse(stream())` + `asyncio.sleep` loop with
`EventSourceResponse`. (Pairs with G3 async endpoints.)

**F8. Chunking → `semantic-text-splitter`** — `src/agentkit/knowledge.py`
Replace `chunk_text`'s char-window heuristic with the Rust splitter (boundary-aware,
fast, releases the GIL); keep `chunk_text` as a thin wrapper with the same
`chunk_chars`/`overlap` options.

**F9. Deps + tests** — `pyproject.toml`
Add `pydantic-graph`, `genai-prices`, `cachetools`, `numpy`, `PyYAML`,
`sse-starlette`, `semantic-text-splitter`; `sqlite-vec` as an extra with graceful
fallback. Add per-swap tests (vectorized search parity, TTL eviction, rule parity
vs the old engine, front-matter edge cases).

---

## Workstream G — Full async data layer + concurrency

The largest change; do it as one coherent migration (clean break, no sync shim).

**G1. Async runtime** — `src/agentkit/runtime.py`, `src/agentkit/db/engine.py`
- `create_async_engine` + `async_sessionmaker`; `build_runtime` builds an async
  engine (default local driver: `sqlite+aiosqlite`; remote libSQL per driver
  support — see open questions).
- `repositories()` becomes `@asynccontextmanager async def repositories(...)`
  yielding an `AsyncSession`.
- **Remove `DB_LOCK`.** Keep single-writer semantics via WAL +
  `busy_timeout` + a bounded retry on `database is locked`; rely on the DB for read
  concurrency instead of a process lock.
- `build_deps` / `Deps.repos` carry the async session; tools already async.

**G2. Async ORM facade (clean break)** — `foundation/model.py`,
`foundation/repository.py`, `foundation/db.py`, `foundation/facades.py`
- `Model`/`Query`, `Repository`/`RepositoryQuery`, `DB.transaction()/session()`,
  and `session_scope` become async-only (`await Note.create(...)`,
  `async with DB.transaction():`). Remove the sync builds and update the class
  docstrings/type stubs. `active_repos` stays a contextvar but is scoped per task.

**G3. Migrate every caller** — async end to end
- `session.py` (`ChatRunner`), `app.py`/`foundation/application.py`
  (`run`/`stream`/`resume`/`replay`/`answer`), `memory.py` (tools),
  `knowledge.py`, `notifications.py` (`_send_conversation`), `hitl.py`/`approvals`,
  `evals.py`, `a2a/task_store.py`, `mcp/server.py`.
- `webui/*`: every endpoint async; no blocking DB call on the loop (F7).
- `scheduler.py`: DBOS step/workflow bodies use async DB access; confirm DBOS
  async support (open question) — otherwise run the sync seam in a worker thread.
- `gateways/*` and `supervise.py`: each service runs its own loop; sessions are
  created per task.
- Update the scaffold and README examples to the async API.

**G4. Off-loop blocking work** — concurrency safety for CPU-blocking calls
- Embeddings (`SentenceTransformerEmbedder`/`FastEmbed`) and file/HTTP I/O run via
  `asyncio.to_thread` (or a bounded `ThreadPoolExecutor`) so they never block the
  event loop; batch document embedding.
- Keep a single, locked embedder singleton (`embeddings.configure/get_default`).

**G5. Concurrency-safe primitives**
- `Mailbox` (E2): async-native, per-agent `asyncio.Queue` behind a lock; safe for
  concurrent senders; durable variant uses DBOS.
- `AgentRegistry` (E1): writes under an `asyncio.Lock`.
- `cached_tool` (F4), `Compactor._state` (per-conversation instance), and any
  shared mutable state get explicit locking or per-task scoping.

**G6. Concurrency policy** — document and enforce
- One in-flight turn per `conversation_id` (per-conversation `asyncio.Lock`);
  different conversations and different agents run concurrently.
- Multi-agent fan-out/broadcast uses `asyncio.gather` behind a bounded
  `Semaphore`; per-branch usage is aggregated into the same accounting as
  `ChatRunner`.
- Channels run concurrently; a slow channel never blocks a turn.

**G7. Migrations/DDL** — `db/migrations.py`, `db/engine.py`
Run schema bootstrap / `sync_missing_columns` / Alembic via the async engine
(`connection.run_sync(...)`), still at startup before serving.

**G8. Tests** — `tests/`
Convert DB-touching tests to async (pytest-asyncio already configured); add a
concurrency test (two conversations + two subagents in parallel, no lock errors),
a lock-removal test (concurrent reads succeed under WAL), and a migration test on
an existing DB.

---

## Workstream H — Docs, README, changelog, final validation

- `docs/guide/`: new `fullstack.md` (what `.full()`/`FullStackProvider` enable,
  the opt-out map); extend `memory.md` (types, profile, consolidation),
  `configuration.md` (providers, channels, new env vars), `agents.md` (`.full()`),
  and add `channels.md` (Gateway base + Telegram/Slack/Email/Discord) and
  `multi-agent.md` (registry/handles, mailbox, handoff, orchestrator/supervisor —
  update `orchestrator.md`/`teams.md` to point at it).
- New `docs/guide/async.md` (the async data layer, the concurrency policy, and the
  off-loop rules) plus an **upgrade guide** for the breaking sync→async change
  (before/after snippets for `repositories()`, `Model`, `DB`, facades, tools).
- Update every guide/README snippet to the async API.
- `README.md`: update Highlights, the Laravel→agentkit table (`Gateway`,
  `FullStackProvider`, provider registry, memory types, `AgentRegistry`/`Mailbox`/
  `handoff`), the Orchestrator section, and Quickstart (`new` is now full;
  `--minimal` for bare).
- `CHANGELOG.md`: one entry per workstream, the breaking-change banner, and the
  version bump (pre-1.0).

## Data flow (unified full-stack agent)

```
agentkit new (full)  ── bootstrap.py: App + FullStackProvider
        │
App.boot ─► Provider.register (config sections) ─► Provider.boot (schedules, channels, senders)
        │
Agent.make(name).full() ─► persona+memory+skills+knowledge+HITL+safety ─► pydantic_ai.Agent
        │
run/stream ─► model = resolve_model(MODEL_NAME) [provider registry]
        │        └─► memory tools store typed rows + profile; recall = hybrid score
        │
subagents ─► AgentRegistry (local handles + A2A peers)
        │        ├─► delegate/spawn (returns) ─► orchestrator/supervisor
        │        ├─► Mailbox send/ask/broadcast (in-process | durable DBOS | A2A)
        │        └─► handoff (control transfer, full transcript | brief)
        │                └─► agent.* events on the dispatcher
        │
channels (CLI/webui/Telegram/Slack/Email/Discord) ─► app.answer ─► same ChatRunner path
        │
scheduler ─► memory:consolidate (dedupe/summarize/prune)

async: every DB touch is `async with repositories()` (async engine; WAL, single
writer, busy-timeout retry, no process lock). Blocking work (embeddings, files,
HTTP) runs off the loop. One turn per conversation; conversations and agents run
concurrently; fan-out/broadcast via asyncio.gather behind a semaphore.
```

## Failure modes

- Missing provider key → `ConfigurationError` naming the env var (build time).
- Unknown `MODEL_NAME` prefix → `ConfigurationError` listing supported prefixes.
- Channel enabled without config → skipped with a debug log; never fatal.
- No embedder → memory/knowledge fall back to keyword matching; consolidation
  dedupes by normalized text only.
- `.full()` called twice or a layer disabled by settings → no duplicate tools, no
  error.
- Unknown agent name / no matching capability → `ask`/`handoff` return a clear
  "no such agent" result (tool-safe) rather than raising into the model loop.
- Handoff loop → `max_handoffs` guard stops the chain and records an
  `agent.error`; messaging to a remote handle with A2A unconfigured is skipped with
  a debug log.
- Durable mailbox without DBOS initialised → falls back to in-process delivery.
- `database is locked` under concurrent writes → bounded retry, then a clear
  `UpstreamError`; reads never block on the writer (WAL).
- `sqlite-vec` unavailable → numpy-vectorized cosine fallback (same results,
  slower); no embedder → keyword fallback.
- DBOS async not available for a given primitive → that step runs its sync seam in
  a worker thread (documented), never on the event loop.
- Existing DB → new columns/table added by `sync_missing_columns`; old rows keep
  `kind="fact"`, `importance=0.5`. Vector format migration is a one-time backfill.

## Rollout / migration

- **Breaking (version bump, pre-1.0):** the data layer is async-only. `repositories()`,
  `Model`/`Query`, `Repository`, `DB`, `session_scope`, and the DB-backed facades
  (`Memory`/`Schedule`/`Feedback`) all change to `async`/`await`; the sync path is
  removed. Ship a dedicated upgrade guide and update every snippet.
- **Additive:** `Agent.full()`/`FullStackProvider`, the library swaps (behavior-
  preserving), the multi-agent primitives, and the new channels.
- `agentkit new --minimal` reproduces today's skeleton (now async).
- New deps are core-small or extras; Email is stdlib-only so the default install
  gains no third-party channel dependency, and `sentence-transformers` stays an
  extra.
- Default scaffold change is user-visible → call it out in README/CHANGELOG and
  cover both `--full` and `--minimal` in tests.

## Validation

```bash
uv run pytest --cov=agentkit          # existing suite + new tests, ≥70% gate
uv run ruff check src tests
uv run mypy src/agentkit
uv build
```
Add: a scaffold smoke test that boots the generated full project; a
provider-resolution test with monkeypatched constructors (no network); a memory
migration test; a consolidation unit test with the offline `hash` embedder; a
gateway-base test with a fake transport; per-library-swap parity tests (vector
search, TTL eviction, validation rules, front matter); a multi-agent test suite
(registry, mailbox, handoff, orchestrator, events); and async/concurrency tests
(parallel conversations + subagents under WAL with no lock errors, off-loop
embedding). All DB-touching tests run under `pytest-asyncio`.

## Assumptions / open questions for implementation

- Slack uses `slack_bolt` socket mode and Discord uses `discord.py`; if either
  library is undesirable, fall back to a webhook/HTTP gateway behind the same
  `Gateway` interface. Confirm the library choice before implementing D3/D5.
- **Async driver for the DB**: local default becomes `sqlite+aiosqlite`; confirm the
  async story for **remote libSQL/Turso** (verify whether `sqlalchemy-libsql`
  supports async, or whether a different driver/HTTP path is needed) before G1.
- **DBOS async support**: verify DBOS supports `async` workflows/steps in the
  pinned version (`dbos>=3.2,<4`); if not, the scheduler keeps a sync seam run in a
  worker thread (documented) rather than blocking the loop.
- **Vector search backend**: `sqlite-vec` (loadable extension) vs libSQL native
  `F32_BLOB`/`vector_distance_cos`. Pick by driver support; keep the numpy-vectorized
  cosine fallback so installs without the extension still work.
- `semantic-text-splitter` ships platform wheels (Rust); confirm wheel availability
  for the supported Python/platform matrix, else keep `chunk_text` as the fallback.
- `OwnerProfile` is a single owner-scoped row (single-user framework); multi-tenant
  is out of scope.
- Hybrid-recall weights and the consolidation duplicate threshold are settings
  with the defaults above; tune after first use.
- `kilo.json`/`AGENTS.md` are untouched; plan only.
