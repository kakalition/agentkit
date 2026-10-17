# agentkit — Contracts + Drivers Architecture (generalize everything)

## Goal

Turn agentkit into a **general, domain-agnostic kit**: wherever the code currently
commits to one implementation, introduce a **contract (Protocol) + a driver registry +
a default driver + an `extend()` hook**, Laravel-style. Keep every existing class and
public import working as the *default driver*. Nothing is ditched in favor of something
else — everything becomes selectable. Then add the missing capabilities (comms
topologies, tasks, subagents, middleware, graph executor, FS backends, code executors)
in the same shape.

## Locked decisions

- **Shape:** `contract → ≥1 core driver → registry → `extend()` → optional extras →
  user selects via settings`. Applies to memory, embeddings, RAG, storage, cache, queue,
  scheduler, durability, observability, pricing, rate limiting, auth, vault, prompts,
  audio, channels, notifications, ingest, guardrails, DB dialect, learning, comms, and
  every new capability.
- **Contracts:** `typing.Protocol` (runtime-checkable) in a new `agentkit/contracts/`
  package; optional `abc.ABC` convenience bases under each subsystem.
- **Manager:** one `agentkit.support.Manager` base + a global driver registry with
  `@register_driver("<kind>", "<name>")` and `Manager.extend("<name>", factory)`.
- **Selection:** a `<subsystem>_driver` setting per subsystem (plus options), surfaced by
  `agentkit inspect` / `/api/info`.
- **Compat:** existing classes become the default drivers; public import paths/signatures
  unchanged; new behavior opt-in.
- **Dependency posture:** core stays PydanticAI + SQLite/DBOS; heavy drivers ship as
  optional extras mirroring `pyproject.toml` (`observability`, `slack`, `discord`).
- **Self-learning default (change from today):** review-gated. `learning_enabled=true` still
  collects, but lessons are stored `proposed` and do **not** affect turns until approved (or
  an eval gate passes) → `learning_require_review=true` becomes the default. Auto-apply is an
  explicit opt-in. Rationale: specialized agents are usually built to be deterministic and
  auditable; self-learning must not silently drift behavior.

## The substrate (WS0 — do first)

1. `src/agentkit/contracts/` — one module per subsystem with its Protocol(s) (list below).
2. `src/agentkit/support/manager.py` — `Manager` base:
   - `driver(name=None)` resolves the configured/1st driver, caches singletons;
   - `create(name)` dispatches to `create_<name>_driver(app)`;
   - `extend(name, factory)` registers a custom driver (Laravel `Cache::extend`);
   - `default_driver` from `<kind>_driver` setting or built-in default.
3. `src/agentkit/support/drivers.py` — `Drivers.register(kind, name, factory)`,
   `@register_driver(kind, name)` decorator, `available(kind)`.
4. Container (`foundation/container.py`) gains **tagged bindings** (`tag`/`tagged`),
   **contextual binding** (`when().needs().give()`), and `App.extend(kind, name, factory)`
   proxying the right manager. Providers register drivers in `register()`.
5. Facades (`foundation/facades.py`) resolve through `app.manager("<kind>").driver()`
   instead of concrete services (`Cache`, `Storage`, `Queue`, `Memory`, …).
6. `config/drivers.py` section + `inspect`/`/api/info` report active driver per subsystem.
7. **Conformance suite:** `tests/contracts/test_<kind>_conformance.py` — a shared param
   suite every driver of a kind must pass.

## Subsystem conversions (each: contract, drivers, files, compat, tests)

| WS | Contract (`agentkit/contracts/`) | Core drivers (existing = default) | Optional extras | Key files |
| --- | --- | --- | --- | --- |
| WS2 Comms | `Topology` | mailbox, hub, outbox, pubsub, groupchat(+speaker strategies), blackboard, broadcast, handoff, swarm, hierarchy, pipeline, mesh | redis/nats transport | new `comms/`; adapters for `agents/mailbox.py`, `agents/handoff.py`, `orchestrator.py` |
| WS3 Memory | `MemoryStore`, `RecallStrategy` | repository hybrid recall (default); kinds registry | vector store, external memory | `db/repositories/memory.py`, `memory.py` |
| WS4 Embeddings | `Embedder` (exists) | hash, sentence-transformers, fastembed | openai, cohere, ollama | `embeddings.py` (`EmbedderManager`) |
| WS5 RAG | `Chunker`, `Retriever`/`VectorStore`, `Reranker` | semantic-splitter + repo search (default) | sqlite-vec, rerankers, http vector db | `knowledge.py`, `db/repositories/knowledge.py` |
| WS6 Filesystem | `FileSystem` | local `Filesystem` (default), state/memory | s3/gcs/http | `foundation/storage.py`, `sandbox.py`; add `edit_file`/`glob`/`grep` + composite backend |
| WS7 Cache | `CacheStore` | array `CacheStore` (default) | file, redis, memcached | `foundation/jobs.py` |
| WS8 Queue | `QueueDriver` | database (default), sync/inline | redis, sqs | `foundation/queue.py` |
| WS9 Scheduler | `SchedulerDriver` | dbos cron (default) | in-process cron, celery | `scheduler.py` |
| WS10 Durability | `Durability` | dbos (default) | temporal/restate | `durability.py` |
| WS11 Observability | `SpanExporter`/`Tracer` | console, otlp, phoenix (default) | langfuse, jaeger presets | `observability.py` |
| WS12 Pricing | `PriceProvider` | genai_prices (default), static table | custom | `pricing.py` |
| WS13 RateLimit | `RateLimiter` | fixed-window/db (default), sliding, token-bucket | redis backend | `ratelimit.py` |
| WS14 Auth+Vault | `AuthStrategy`, `Vault` | none/api-key/jwt (default), fernet (default), env | oidc, kms | `security/` |
| WS15 Prompts | `PromptStore` | file registry (default) | db, remote | `prompts.py` |
| WS16 Audio | `Transcriber`, `Synthesizer` | openai (default) | whisper-local, elevenlabs | `audio.py` |
| WS17 Channels | `Channel` (`Gateway` exists) + `NotificationChannel` | telegram, slack, email, discord, log, conversation | — | `gateways/`, `foundation/notifications.py` |
| WS18 Ingest | `DocumentLoader` | pdf, docx, html, text (default) | ocr, markdown | `ingest.py` |
| WS19 Guardrails | `Guard`/`Scanner` | regex PII + injection (default), moderation | openai moderation, llama-guard | `guardrails.py`, `moderation.py` |
| WS20 DB dialect | `Dialect` | sqlite+aiosqlite, libsql (default) | postgres, others | `db/engine.py` |
| WS21 Learning | `Extractor`, `LearningStrategy`, `LearningSink` | model-json + heuristic (default); reflect→learn→apply (default); memory/skill/profile sinks | feedback-driven, eval-gated, custom | `learning.py` |

For WS2/WS6 new tools, follow the naming/approval conventions in Cross-cutting below.

### WS21 design principles (self-learning)

- **Layered scope, not one switch:** facts/preferences (low risk) may auto-apply; procedural
  rules are gated; learned items **never override explicit instructions or policy/guardrails** —
  they are advisory context only.
- **Review-gated default (see Locked decisions):** lessons stored `proposed`; `approve_lesson`
  (or the eval gate) promotes to `active`; `reject_lesson` is permanent.
- **Safe by construction:** PII/secret redaction before storage (exists), importance decay,
  dedupe/merge (exists), max-lesson cap, and full reversibility (forget by id).
- **Selectable strategy:** `LearningStrategy` drivers (`reflect_apply` default, `feedback`,
  `eval_gated`, `preference_only`, `none`); `Extractor` (model-json / heuristic); `LearningSink`
  (memory / skill / owner-profile / custom). Specialized agents can choose `none`.
- **Specialized-agent posture:** rely on instructions/tools/policy for deterministic behavior;
  treat learning as an opt-in enhancement, and keep the digest injected into instructions capped
  and clearly delimited.

## New capabilities (same contract+driver shape)

| WS | Contract | Drivers | Files |
| --- | --- | --- | --- |
| WS22 Tasks | `TaskStore` + `PlanningStrategy` | memory/db store; in-loop todos, batch `Planner` | new `tasks.py`, `db/models.py`, `db/repositories/tasks.py`, `planning.py`; tools `write_todos`/`read_todos`/`add_todo`/`update_todo`/`clear_todos` |
| WS23 Subagents | `ContextStrategy` | isolated, shared, summarized | new `agents/subagent.py`; `teams.py`, `orchestrator.py`, `foundation/agent.py`; `task(subagent, prompt)` tool |
| WS24 Middleware | `AgentMiddleware` | turn (exists), before/after model, before/after tool, wrap_model_call, wrap_tool_call | `foundation/pipeline.py`, new `foundation/agent_middleware.py` |
| WS25 Graph | `GraphExecutor` | sequential (default), parallel (fan-out/join/reducers), checkpointed (DBOS) | `graph.py`, `durability.py` |
| WS26 Code exec | `CodeExecutor` | local-subprocess (default, limited) | docker, jupyter, e2b | new `executors.py`; approval-gated `run_code` |
| WS27 Evals | `Reporter` + trajectory assertions | pydantic_evals, phoenix/otlp (exists) | `evals.py` |

## Cross-cutting requirements

- Every new subsystem: `<subsystem>_driver` setting(s), `.full()` layer toggle,
  `fullstack()` section, `inspect`/`/api/info` reporting, and a scaffold hint.
- Deny-by-default allow-lists; writes approval-gated via `requires_approval=True` +
  `approval_capability` (see `CONTINUATION.md`); audit + `agent.*` events.
- Namespaced tool names + tests asserting unique `_function_toolset` keys.
- Contracts documented; each driver lists required options; `extend()` examples per kind.
- Docs: one guide page per subsystem (drivers table + how to add a driver), sidebar,
  README highlights, CHANGELOG `Added`; keep `tests/test_foundation_scaffold.py` green.

## Ordering

1. **WS0 substrate** (contracts, Manager, registry, container extensions, facade
   resolution, conformance harness) — no behavior change.
2. Convert leaf subsystems with low blast radius: WS4, WS7, WS8, WS9, WS12, WS15, WS16,
   WS18, WS20.
3. Convert stateful/security subsystems: WS3, WS5, WS10, WS11, WS13, WS14, WS19, WS21.
4. New capabilities: WS22 → WS23 → WS24; WS25, WS26, WS6; WS17 comms core (WS2) →
   group-chat strategies → surfaces; WS27.
5. Surfaces/docs/scaffold continuously with each WS.

## Risks & mitigations

- **Abstraction tax** → minimal Protocols (only methods drivers must implement); one
  default driver per kind; registries are thin.
- **Behavior drift during conversion** → conformance suite + existing tests unchanged;
  each default driver must reproduce current behavior exactly.
- **Prompt bloat** from memory/lesson/todo digests → caps + importance ranking.
- **Durability/concurrency** (WS2/WS25) → explicit dedupe keys, `thread_id` ownership,
  reducers; SQLite WAL discipline already in place.
- **Dependency creep** → extras only; core import graph unchanged.
- **Compat** → keep class names/import paths; new driver classes are additive; new
  behavior opt-in.

## Validation

- `uv run ruff check src tests` · `uv run mypy src/agentkit` · `uv run pytest --cov=agentkit`
  (≥70% gate); conformance suite per contract; web UI build + CLI smoke; scaffold subprocess boot.

## §Explicitly deferred / left (too detailed or niched)

- Distributed multi-process workers — revisit on demand (A2A covers cross-host).
- No-code Studio-style builder — later; inspector + driver config cover most needs.
- Provider-specific quirks — thin middleware, no dedicated subsystem.
- **No single-pattern commitment** — never hardcode a topology, speaker strategy, backend,
  executor, extractor, or context strategy.

## Open questions

- Driver registry namespacing: flat `"cache:redis"` vs nested `("cache","redis")`? (Recommend
  nested tuple keys, string convenience.)
- Settings granularity: one `drivers:` config section vs per-subsystem flags? (Recommend:
  per-subsystem `<name>_driver` + optional `<name>_<driver>_*` options.)
- Should `App.extend()` be the single public entry point (providers call it), or also allow
  module-level `@register_driver`? (Recommend: both — decorator for libraries, `extend()` for apps.)
