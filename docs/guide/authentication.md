# Authentication

## Introduction

Agentkit is **local-first**: with `AUTH_ENABLED=false` (the default) every
request and turn runs as the single owner named by `OWNER_ID`, exactly as before.
Turning auth on makes the runtime multi-tenant: each request resolves to an
[`Actor`](#the-actor) whose `owner_id` is the tenant key already threaded through
every repository.

Auth is **opt-in**, **fail-closed** (when enabled, an unauthenticated request is
rejected), and **reversible** (a config change, no migration).

## The Actor

```python
from agentkit import Actor

Actor(owner_id="acme", subject="ci", roles=frozenset({"admin"}), method="api_key")
```

- `owner_id` — the tenant key; every DB read/write is scoped to it.
- `subject` — who authenticated (key name or JWT `sub`).
- `roles` — used by [RBAC](#tool-rbac).
- `method` — `none`, `api_key`, or `jwt` (`authenticated` is `method != "none"`).

When auth is disabled the runtime builds a `system_actor(settings)` from
`OWNER_ID` with no roles — byte-for-byte the old behavior.

## Enabling auth

```bash
AGENTKIT_AUTH_ENABLED=true
# a JSON map of name -> {key, owner, roles} ...
AGENTKIT_AUTH_API_KEYS='{"ci": {"key": "sk-live-…", "owner": "acme", "roles": ["admin"]}}'
# ... or a compact CSV: name:key:owner:role1|role2;name2:key2
```

JWT/OIDC (JWKS) is enabled by pointing at the issuer:

```bash
AGENTKIT_AUTH_JWKS_URL=https://idp.example/.well-known/jwks.json
AGENTKIT_AUTH_ISSUER=https://idp.example/
AGENTKIT_AUTH_AUDIENCE=agentkit
AGENTKIT_AUTH_ALGORITHMS=RS256
AGENTKIT_AUTH_OWNER_CLAIM=sub        # falls back to email, then AUTH_DEFAULT_OWNER
AGENTKIT_AUTH_ROLES_CLAIM=roles
```

Signing keys are fetched once and cached (`AUTH_JWKS_CACHE_TTL`); an unknown
`kid` triggers one refetch for key rotation. Verification is fail-closed: a bad
signature, expiry, issuer, or audience raises, never an allow.

## Database-backed API keys

Static keys live in config. For managed keys, hash them in the database:

```bash
agentkit auth:key create ci --owner acme --roles admin   # prints the key once
agentkit auth:key list
agentkit auth:key revoke ci
agentkit auth:whoami
```

Keys are stored as SHA-256 hashes (`api_keys.key_hash`); the plaintext is shown
once and never persisted or logged.

## HTTP surfaces

- **Web UI / `/api/*`** — the SPA sends `Authorization: Bearer <token>`. Because
  `EventSource` cannot set headers, `/api/events` also accepts
  `?access_token=<token>`. `GET /api/whoami` reports the resolved actor. Health
  and docs stay public; everything else is gated when auth is on.
- **A2A** — Starlette middleware guards the JSON-RPC route; the agent card and
  `/healthz` stay public.
- **MCP** — HTTP transports accept a bearer token through FastMCP's token
  verifier when auth is enabled; stdio is unaffected.

## Tool RBAC

Extend a [`ToolPolicy`](/guide/safety) with role requirements; the `policy_hooks`
capability denies a tool the run's actor is not allowed to use:

```python
from agentkit import ToolPolicy

policy = ToolPolicy(require_roles={"db_delete": {"admin"}})
```

Role checks are **fail-closed**: with no actor (auth disabled) a role-gated tool
is denied. The default policy declares no role requirements, so local use is
unaffected.

## Credential vault

Channel and provider secrets can be stored encrypted at rest instead of in the
environment. The vault is opt-in and needs a Fernet key:

```bash
AGENTKIT_CREDENTIALS_ENABLED=true
AGENTKIT_CREDENTIALS_KEY=…            # a Fernet key; any passphrase is derived to one
```

```bash
agentkit credentials:set telegram_bot_token --value '…'   # encrypted; never echoed
agentkit credentials:list                                  # names only
agentkit credentials:delete telegram_bot_token
```

At boot `FullStackProvider` hydrates settings from the vault **first**, falling
back to the environment for anything unset, so channels pick up vault secrets
transparently. Values are stored as ciphertext (`credentials` table) and are
masked in `/api/config`; the stack view reports the vault as enabled/disabled
only. Using the vault without a key raises rather than silently storing
plaintext.

## Rate limiting

An opt-in fixed-window limiter guards the HTTP boundary and returns `429` with a
`Retry-After` header when exceeded:

```bash
AGENTKIT_RATE_LIMIT_ENABLED=true
AGENTKIT_RATE_LIMIT_PER_MINUTE=60
AGENTKIT_RATE_LIMIT_BURST=10            # extra headroom on top of the limit
AGENTKIT_RATE_LIMIT_TOOL_PER_MINUTE=0   # optional per-tool cap (0 = off)
```

Counters live in the `rate_windows` table keyed `(owner_id, key, window_start)` so
limits hold across processes; an in-process cache short-circuits once a key is
over its limit. `RateLimiter` (`agentkit.ratelimit`) is the reusable seam for
per-tool enforcement. `agentkit inspect` / `/api/info` report the enabled flag.

## Safety notes

- Loopback bind + `warn_if_exposed` remain; auth is additive, not a replacement.
- Never log tokens: `auth_api_keys` is masked in `/api/config` and secret
  redaction covers keys in logs.

## Drivers

### What authentication and a vault are, in plain English

These are two different jobs that are easy to mix up:

- **Authentication** answers *"who is this?"* It is the **bouncer at the door**:
  a request arrives carrying a key (an API key or a signed token), and the
  authenticator checks whether it is genuine and looks up which person and team
  it belongs to. If the key is bad, the request is turned away. agentkit's auth
  is **opt-in** (off by default, so local use is unchanged) and **fail-closed**
  when enabled: a request that cannot be authenticated is rejected rather than
  let through.
- A **secret vault** answers *"where are the passwords kept?"* It is the **safe**
  behind the desk: instead of leaving bot tokens and API keys lying around in
  environment variables in plain text, the vault stores them encrypted and hands
  them back by name when a channel or provider needs them. The vault says nothing
  about who is calling; it only stores secrets.

Both are **drivers**: pluggable implementations selected by a setting.

### A runnable example

```python
from agentkit import App, DriverKind

app = App()   # reads AUTH_ENABLED / AUTH_DRIVER / VAULT_DRIVER from env / .env

# Default: local-first. AUTH_ENABLED is false, so every request runs as the
# single owner named by OWNER_ID. The authenticator exists but is not enforced.
print(app.manager(DriverKind.AUTH).driver().enabled)      # -> False

# Turn it on with AUTH_ENABLED=true; requests must then present a valid API key
# or JWT, or they are rejected (fail-closed).
print(app.manager(DriverKind.AUTH).configured_driver())   # -> "default"
print(app.manager(DriverKind.AUTH).available())           # -> ["anonymous", "default"]

# The vault stores secrets encrypted at rest (VAULT_DRIVER=fernet by default).
print(app.manager(DriverKind.VAULT).configured_driver())  # -> "fernet"

# Switch drivers by setting env vars and rebuilding the app:
#   AUTH_DRIVER=anonymous   (never authenticates; always the system actor)
#   VAULT_DRIVER=env        (read-only over the environment)
```

### Built-in drivers

**Authentication** (`AUTH_DRIVER`):

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `default` (default) | One authenticator that accepts static config API keys, database-backed API keys, and JWT/JWKS tokens, resolving each request into an `Actor`. Only enforced when auth is enabled. | Real multi-tenant deployments that need to identify callers. |
| `anonymous` | Never authenticates; every request resolves to the settings owner via `system_actor`. | Local development, or to turn auth off explicitly. |

**Secret vault** (`VAULT_DRIVER`):

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `fernet` (default) | Stores channel/provider secrets encrypted at rest in the `credentials` table, keyed by name. Needs `AGENTKIT_CREDENTIALS_KEY` and refuses to run without it. | Keeping secrets out of the environment and in the database. |
| `env` | A read-only vault that reads secrets from the settings/environment; writes raise, and deletes are no-ops. | Using environment variables only, with no database secret store. |

::: tip Environment wins over the vault
At boot the vault hydrates settings **only for names that are unset**, so any
value already present in the environment takes precedence. If a vault secret
seems ignored, the same name is probably set in the environment too.
:::

### How to select a driver

```bash
AUTH_ENABLED=true         # opt in to multi-tenant auth (default false: local-first)
AUTH_DRIVER=default       # default | anonymous
VAULT_DRIVER=fernet       # fernet | env
```

Selection follows the standard precedence: an explicit name passed in code
(`app.manager(DriverKind.AUTH).driver("anonymous")`), then the setting, then the
default. `agentkit inspect` prints the resolved `auth` and `vault` values.

### Override it just for your app

`app.extend(...)` registers a driver scoped to this application only:

```python
from agentkit import DriverKind

app.extend(DriverKind.AUTH, "oidc", lambda app: OIDCStrategy(app.settings))
app.extend(DriverKind.VAULT, "aws", lambda app: AwsSecretsVault(app.settings))
```

Then select it with `AUTH_DRIVER=oidc` or `VAULT_DRIVER=aws`.

### Ship a reusable driver

Register it globally so any app can use it. An auth driver implements
`authenticate(...)` / `resolve_token(...)` and a `default_actor()`; a vault driver
implements `get` / `set` / `names` / `delete`:

```python
from agentkit import DriverKind, register_driver

@register_driver(DriverKind.AUTH, "oidc")
def _oidc(app):
    return OIDCStrategy(app.settings)
```

See [Contracts & Drivers](/guide/drivers) for the full contracts.

### Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Every request returns `401` after enabling auth | `AUTH_ENABLED=true` is fail-closed; the request presented no valid API key or JWT (check the `Authorization: Bearer <token>` header). |
| `VaultError: credentials_key is not set` | The vault is enabled but `AGENTKIT_CREDENTIALS_KEY` is missing; it refuses to store plaintext. |
| A secret set in the vault seems ignored | The same name is already set in the environment, which takes precedence over the vault. |
| A role-gated tool is denied with auth off | Role checks are fail-closed: with no actor, a tool requiring a role is denied by design. |
