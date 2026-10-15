# Full-Stack Platform Roadmap — Auth, Ops, Interfaces, Learning Quality

Goal: evolve agentkit from a single-operator, local-first agent runtime into a
deployable "full stack" platform **without breaking the local-first default**. Every
phase below is independently shippable and must leave `ruff`/`mypy`/`pytest`
green.

## Locked decisions (from planning interview)

1. **Identity**: opt-in auth; `owner_id` **is the tenant key** (already threaded
   through every repo). Local-first default (loopback, no auth, `settings.owner_id`)
   stays byte-for-byte compatible.
2. **Auth mechanism**: API keys **and** JWT/OIDC (JWKS) behind one `Authenticator`;
   chosen by settings.
3. **Storage/deploy**: SQLite/libSQL remains the default and only required backend;
   add a tested, optional Postgres engine path. Vertical scale first.
4. **Dependencies**: new capability libs go into **base dependencies** (no extras).

## Constraints & non-negotiables

- `auth_enabled=False` (default) must produce today's behavior exactly.
- Do not break the public import surface (`agentkit/__init__.py`) or existing tests.
- `agentkit` has no hosted account; secrets never logged (extend the existing
  redaction in `logging.py` / `webui/config_api.py`).
- New tables use the existing schema-drift mechanism (`init_db` +
  `apply_missing_columns` in `db/migrations.py`); no destructive migrations.
- Keep `LearningRunRepo`-style plain repo classes (no `agentkit.foundation.*`
  import at module scope → circular imports).

## Codebase grounding (key seams to reuse)

- Owner threading: `runtime.repositories()` (`runtime.py:62`) constructs repos with
  `runtime.settings.owner_id`; `App.repositories()` / `App.deps()` wrap it
  (`foundation/application.py:512`, `:515`). `Deps.owner_id` is a property over
  settings (`deps.py:52`). **This is the only place owner resolution must become
  dynamic.**
- HTTP surfaces: `build_webui_app` (`webui/app.py:87`) mounts routers via
  `include_router`; `WebUIContext` (`webui/context.py:25`); A2A `build_a2a_app`
  (`a2a/server.py:96`, Starlette); MCP `serve_mcp` (`mcp/server.py:12`, FastMCP).
- Tool gating: `lifecycle_hooks` / `policy_hooks` (`foundation/middleware.py`),
  `ToolPolicy` (`policy.py`), approvals registration.
- CLI: modules imported in `cli/commands/__init__.py`; Typer app in `cli/_app.py`.
- Repos container: `db/repositories/container.py` `Repositories.__post_init__`.
- Health: `health.py` (`run_checks`, `health_routes`). Supervision: `supervise.run_all`.
- Config masking: `webui/config_api.py`. Stack view: `webui/introspect.stack_view`.

## Data model additions (`db/models.py`)

- `APIKey`: `id`, `owner_id` (index), `name`, `key_hash` (sha256), `prefix`,
  `roles` (JSON str), `created_at`, `last_used_at`, `revoked_at`.
- `Credential`: `id`, `owner_id` (index), `name`, `kind`, `ciphertext`,
  `metadata` (JSON str), `created_at`, `updated_at`; unique `(owner_id, name)`.
- `RateWindow`: `id`, `owner_id` (index), `key`, `window_start`, `count`; unique
  `(owner_id, key, window_start)`.
- `Webhook`: `id`, `owner_id`, `url`, `events` (JSON str), `secret`,
  `enabled`, `created_at`.
- `WebhookDelivery`: `id`, `webhook_id`, `event`, `payload`, `status`,
  `attempts`, `error`, `created_at`.
- `LessonReview` **or** add `Memory.status` (`proposed|active|rejected`,
  default `active` for backward compat). Prefer a `status` column on `Memory`.
- `EvalCapture` (optional): `id`, `owner_id`, `conversation_id`, `case` (JSON),
  `created_at`.
- Register new repos in `Repositories.__post_init__` (`api_keys`, `credentials`,
  `rate_windows`, `webhooks`, `evals_capture`).

## Settings additions (`config.py`, all default-safe)

- Auth: `auth_enabled=False`, `auth_api_keys` (JSON map or `name:owner:roles` CSV),
  `auth_jwks_url`, `auth_issuer`, `auth_audience`, `auth_algorithms="RS256"`,
  `auth_owner_claim="sub"`, `auth_roles_claim="roles"`, `auth_default_owner=""`,
  `auth_required_roles` (per-surface overrides acceptable).
- Credentials: `credentials_enabled=False`, `credentials_key` (Fernet; env
  `AGENTKIT_CREDENTIALS_KEY`).
- Rate limits: `rate_limit_enabled=False`, `rate_limit_per_minute`,
  `rate_limit_tool_per_minute`, `rate_limit_burst`.
- Data lifecycle: `data_export_enabled=True`, `data_forget_enabled=False`
  (destructive → explicit opt-in).
- Learning review: `learning_require_review=False` (when true, lessons stored
  `proposed` until approved).
- Ingestion: `ingest_max_bytes`, `ingest_allowed_schemes`.
- Metrics: `metrics_enabled=False`, `metrics_path="/metrics"`.
- Interfaces: `openai_api_enabled=False`, `webhooks_enabled=False`.

---

## Phase 0 — Foundations (no behavior change)

1. Add `Actor` (frozen dataclass) in new `agentkit/security/__init__.py`:
   `owner_id`, `subject`, `roles: frozenset[str]`, `method` (`none|api_key|jwt`).
2. Add `Deps.actor: Actor | None` (default `None`); change `Deps.owner_id` to
   return `actor.owner_id` when set, else `settings.owner_id`.
3. Make owner explicit: `repositories(runtime, owner_id=None)` and
   `App.repositories(owner_id=None)`; default preserves `settings.owner_id`.
   `App.deps()` accepts `actor` and sets `Deps.actor`.
4. Add `WebUIContext.actor` and a `get_actor(request)` dependency returning
   `Actor` (defaults to the settings owner when auth is off).
5. Unit tests proving defaults unchanged (existing suite + a `Deps.owner_id`
   regression test).

## Phase 1 — Auth & RBAC (opt-in)

1. `agentkit/security/keys.py`: `hash_key`, `parse_api_keys` (env/config → Actor).
   Base dep: `cryptography` (already pulled; verify) — API keys need no crypto lib.
2. `agentkit/security/jwt.py`: `JWTAuthenticator` — fetch/cache JWKS (httpx),
   verify signature/issuer/audience, map claims → `Actor`. Base deps: `pyjwt`
   (or `joserfc`) + `cryptography`.
3. `agentkit/security/authenticator.py`: `Authenticator` (compose api-key + jwt),
   `authenticate_request(request) -> Actor`, `require_roles(*roles)` dependency.
   Fail-closed when `auth_enabled=True` and the request is unauthenticated.
4. Wire surfaces:
   - web UI: middleware + dependencies on `/api/*`; SPA sends
     `Authorization: Bearer`; add `GET /api/whoami`.
   - A2A: Starlette middleware on `build_a2a_app` (card route stays public).
   - MCP http: auth hook in `serve_mcp` (stdio unaffected).
5. RBAC: extend `ToolPolicy` with `require_roles`; enforce in `policy_hooks`
   (deny when the actor lacks a role). Add per-route role requirements.
6. Audit: include `actor`/`subject` on `repos.audit` writes via `Deps.actor`.
7. Injection hardening: auto-`wrap_untrusted` for web/MCP/A2A-sourced content
   (config-gated).
8. CLI: `agentkit auth:key create|list|revoke` (DB-backed, hashed);
   `agentkit auth:whoami`.
9. Web UI: token entry + actor display; docs page `docs/guide/authentication.md`.
10. Tests: auth off = unchanged; api-key happy/deny; JWT verify + JWKS cache + bad
    signature/expiry; role denial; A2A/MCP 401.

## Phase 2 — Credentials vault

1. `CredentialRepo` + `agentkit/security/credentials.py` encryption via Fernet
   (`AGENTKIT_CREDENTIALS_KEY`); refuse to enable when the key is absent.
2. `Credentials` facade/service; expose `Deps.credentials` for tools/channels.
3. Channels/gateways read tokens from the vault first, env fallback (Telegram/
   Slack/Discord/Email); no plaintext in logs or `config_api` output.
4. CLI `agentkit credentials:set|list|delete` (values never echoed).
5. Docs + stack_view reporting (names only).

## Phase 3 — Rate limiting & abuse control

1. `agentkit/ratelimit.py`: DB-backed fixed-window (works on SQLite + Postgres)
   keyed `(owner_id, key, window_start)`; in-process cache to cut round-trips.
2. Enforce at the HTTP boundary (middleware → 429 with `Retry-After`) and
   optionally per-tool in `lifecycle_hooks`.
3. Settings + `agentkit inspect`/stack_view reporting; tests for burst/limit/reset.

## Phase 4 — Learning quality & data lifecycle

1. Lesson review: `Memory.status`; `.learning()` lists/lists-active only; `learn`
   and `reflect` honor `learning_require_review`; CLI
   `learning:review approve|reject <id>`; web UI review inbox.
2. Eval-driven learning: `agentkit.evals.capture_turns(repos, ...)` → eval cases;
   optional post-reflect eval gate (`learning_eval_gate`); surface pass/fail.
3. Data lifecycle: `agentkit data:export --owner <id>` (JSON bundle) and
   `agentkit data:forget --owner <id> --yes` erasing conversations/messages/
   memories/profile/knowledge/learning_runs/feedback/usage; **audit entries kept as
   tombstones** preserving the hash chain. API endpoints (authz-gated) + web UI.
   Dry-run by default; destructive requires confirmation.
4. Ingestion: `agentkit/ingest.py` — pdf (`pypdf`), docx (`python-docx`), html
   (`beautifulsoup4`), url (httpx), plain text; `KnowledgeBase.add_file/add_url`;
   CLI `knowledge:add-file`; size/scheme guards. Base deps for parsers.
5. Tests: review gating, export/forget round-trip + tombstone verify, ingestion per
   format, retrieval-quality smoke.

## Phase 5 — Interfaces & ecosystem

1. OpenAI-compatible API (new router in webui or a dedicated FastAPI app):
   `GET /v1/models`, `POST /v1/chat/completions` (streaming SSE + non-streaming),
   mapped to `app.answer`; auth via Phase 1; usage recorded.
2. Webhooks: `Webhook` model + dispatcher listener with HMAC signature, retries
   (bounded), `WebhookDelivery` log; CLI `webhook:add|list`; docs.
3. Tool ecosystem: OpenAPI→tools loader (`agentkit/tools_from_openapi.py`),
   built-in catalog entries (browser/code-exec/web-search) via capabilities,
   per-tool rate/cost limits.
4. Presets/blueprints: `agentkit new --preset support|research|ops` composing the
   existing scaffold + evals + policies + tools.
5. Tests + docs for each.

## Phase 6 — Ops & scale

1. Metrics: base dep `prometheus-client`; `/metrics` endpoint; counters/histograms
   for turns, tool errors, queue depth, scheduler runs, cost; instrument
   `session.py`, `foundation/queue.py`, `scheduler.py`. `metrics_enabled` gate.
2. Migrations/backup CLI: `agentkit migrate` (alembic + `sync_missing_columns`),
   `agentkit db:backup`/`db:restore` (SQLite WAL-safe via `VACUUM INTO`).
3. Postgres path: branch `create_async_db_engine` on URL scheme; base dep async
   driver (`asyncpg` or `psycopg`); document single-writer caveats for
   scheduler/queue; add a Postgres test job/matrix (skippable locally).
4. Deploy: Dockerfile + compose (single node), per-dependency readiness checks in
   `health.py`, queue-worker scaling notes.
5. Docs: `docs/guide/deployment.md` updates, ops runbook.

## Phase 7 — Product UX

1. Web UI: streaming chat (SSE to `App.stream`), inline **approval UI** (wire the
   existing approvals), lesson-review inbox, schedule/config editors, and
   metrics/rate-limit panels.
2. Cancellation: `App.cancel(conversation_id)` + `ChatRunner` cancellation;
   resumable long tasks (build on `App.resume`).
3. E2E tests for the UI flows (API-level) + docs.

## Security & failure modes

- **Fail-closed** when `auth_enabled=True`; fail-open (today's behavior) only when
  disabled. A config error (bad JWKS URL, missing vault key) must deny, not allow.
- **Never** log secrets/tokens/API keys or credential values; extend redaction and
  `config_api` masking.
- Loopback bind + `warn_if_exposed` remain; auth is additive, not a replacement.
- Erasure vs. audit integrity: tombstones keep the chain verifiable.

## Migration & rollout

- All new tables created by the existing `init_db`/`apply_missing_columns` path.
- `Memory.status` added as a **nullable/defaulted** column → old rows default to
  `active` (non-breaking).
- Auth, credentials, rate limits, metrics, OpenAI API, webhooks are all default-off;
  enabling is a documented, reversible config change.
- Ship each phase as its own change with docs + CHANGELOG entries.

## Validation (per phase; final gate must all pass)

- `uv run ruff check src tests`
- `uv run mypy src/agentkit`
- `uv run pytest` (coverage ≥70%; currently ~80%)
- Per-phase: targeted tests listed above; new docs pages linked in
  `docs/.vitepress/config.mts`; `CHANGELOG.md` **and**
  `docs/reference/changelog.md` updated; keep
  `tests/test_foundation_scaffold.py` subprocess smoke green (re-run if the
  scaffold changes).

## Risks

- Owner-resolution refactor touches ~108 `owner_id` sites → keep the default path
  identical and gate all dynamic behavior behind an explicit owner/actor.
- Postgres breaks single-writer assumptions in the scheduler/queue → constrain the
  Postgres job to one scheduler/worker leader.
- Base-dependency growth conflicts with the lean-install ethos → document and keep
  capability gating so nothing imports heavy libs unless enabled.
- Web UI token storage is XSS-sensitive → prefer `Authorization` header over
  persistent localStorage; short-lived tokens; loopback default.
- Two changelogs + VitePress sidebar must stay in sync.

## Out of scope (unless separately requested)

- True multi-user-within-one-owner (teams) and per-user private memory.
- Hosted/marketplace distribution of skills/tools.
- OCR for scanned documents; browser automation runtime.

## Open questions (non-blocking; sensible defaults chosen)

- OIDC claim names: default `sub` for owner (fallback `email`) and `roles` for
  roles — confirm against the intended IdP.
- Credential scope: per-owner by default; confirm app-global secrets are not needed.
- Preset blueprint set (`support|research|ops`) — confirm names/content.
- Postgres async driver choice (`asyncpg` vs `psycopg`) — pick during Phase 6 based
  on constraint/JSON support needs.
