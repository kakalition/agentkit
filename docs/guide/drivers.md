# Contracts & Drivers

## Who this page is for

If you have never built an AI agent before, welcome — you do not need any
background to read this page. We will explain every term as we go. By the end you
will understand one idea that runs through all of agentkit: **the framework never
locks you into a single implementation of anything.**

If you just want to build an agent, you can skim this page. Come back when you
want to change how something works (use a different cache, a different database,
a different place to store files, …).

## A 30-second primer: what is an "agent"?

An **agent** is a program that talks to a large language model (LLM — the same
kind of technology behind ChatGPT) and can *do things*: it can call functions
(called **tools**), remember facts, search documents, and so on. You give it an
instruction ("You are a helpful assistant") and it decides what to do next.

Building a real agent means making many *libraries* work together:

- where conversations are **stored** (a database),
- where **cached** results live,
- how **files** are saved,
- how **background jobs** run,
- which **embedding model** turns text into numbers for search,
- how **traces** (records of what the agent did) are exported,
- and so on.

Each of those is a place where agentkit had to pick *some* implementation. This
page is about how it lets you pick a **different** one — without rewriting your
code.

## The problem this solves

Imagine a framework that hard-codes "the cache is an in-memory dictionary". That
is fine until you run two copies of your agent and each copy has its own,
disconnected cache. Now you want Redis instead. In a hard-coded framework, your
options are: fork the framework, or patch it. Neither is good.

agentkit takes a different approach. Every one of those choices is a **socket**
you can plug something else into.

::: tip The wall-socket analogy
Think of a power outlet in your home. The outlet is a **contract**: "give me a
plug that provides 230 volts". A lamp, a charger, and a kettle all fit the same
outlet because they all *provide* what the outlet requires. You can swap the lamp
for the kettle without rewiring your house.

In agentkit, the outlet is a **contract**, each appliance is a **driver**, and
"swapping the appliance" is choosing a different driver.
:::

## The vocabulary (plain English)

| Term | What it means | Everyday analogy |
| --- | --- | --- |
| **Subsystem** | a job the framework needs done | "make toast" |
| **Contract** | the exact list of methods a thing must have to do that job | the shape of the plug |
| **Driver** | one concrete implementation of a contract | a specific toaster |
| **Kind** | the *name* of the subsystem, e.g. `cache`, `storage`, `comms` | the label on the outlet |
| **Registry** | the global list of drivers that exist | the appliance catalog |
| **Manager** | the object that picks and builds the driver you asked for | the person who fetches the appliance |
| **Default driver** | the one used if you don't choose | the toaster that came in the box |
| **Selection** | choosing a driver through a setting | telling the butler "use the kettle" |

In code, a **contract** is a Python `Protocol` — a description of methods, like
"any cache must have `get`, `put`, `has`, `forget`, `flush`". A driver does not
have to *inherit* from anything; it just has to *have* those methods. This is
called **structural typing**: if it walks like a duck and quacks like a duck, it's
a duck.

## How it works, step by step

```text
1. A subsystem needs a driver (e.g. "the cache").

        your code ──────────────► app.cache

2. A manager looks up which driver you selected.

        CACHE_DRIVER=null  (a setting)
                 │
                 ▼
        CacheManager  ──selection──►  "null"
                 │
                 ▼
3. The manager builds (once) and remembers the driver.

        NullCacheStore()   ◄── registered factory / create_null_driver

4. Your code uses it through the contract methods.

        app.cache.put("k", 1)     # works with ANY cache driver
```

You never write `if driver == "redis": ...`. You write against the **contract**,
and the manager gives you the right object.

## A worked example: changing the cache

The cache is a small key/value store. The default keeps things in memory for the
life of the process. Suppose you want a cache that remembers *nothing* (handy in
tests, or as a "switch it off" toggle). That driver already exists and is called
`null`.

```bash
# .env — one line changes the whole application
CACHE_DRIVER=null
```

That's it. Everywhere your code (or the framework) calls `app.cache`, it now gets
the no-op cache. The default is `array`, which is the real in-memory store.

You can also read the result in Python:

```python
from agentkit import App, DriverKind

app = App()
app.cache.put("greeting", "hi")
print(app.cache.get("greeting"))          # -> "hi"

print(app.manager(DriverKind.CACHE).driver())   # -> <CacheStore ...>
print(app.manager(DriverKind.CACHE).available()) # -> ["array", "null"]
```

## The driver catalog

Below is every subsystem, the setting that selects it, and the built-in drivers.
You almost never need to touch most of these — they exist so you *can* when you
need to.

| Kind | Setting | Built-in drivers (default first) |
| --- | --- | --- |
| `cache` | `CACHE_DRIVER` | `array` (in-memory), `null` (does nothing) |
| `prompts` | `PROMPTS_DRIVER` | `file` (reads `prompts/*.md`), `memory` |
| `embeddings` | `MEMORY_EMBEDDING_BACKEND` | `sentence-transformers`, `fastembed`, `hash`, `none` |
| `memory` | `MEMORY_DRIVER` | `repository` (the database), `in_memory` |
| `memory_recall` | `MEMORY_RECALL_DRIVER` | `hybrid` (similarity+recency+importance), `keyword`, `recency` |
| `chunker` | `CHUNKER_DRIVER` | `semantic` (split on meaning), `fixed` (split by length) |
| `retriever` | `RETRIEVER_DRIVER` | `repository`, `memory` |
| `reranker` | `RERANKER_DRIVER` | `identity` (keep order), `lexical` (reorder by keyword overlap) |
| `storage` | `STORAGE_DRIVER` | `local` (a folder), `memory` |
| `queue` | `QUEUE_DRIVER` | `database` (durable), `sync` (run immediately) |
| `scheduler` | `SCHEDULER_DRIVER` | `dbos` (durable cron), `memory` |
| `durability` | `DURABILITY_DRIVER` | `dbos`, `temporal` (needs an extra) |
| `database` | `DATABASE_DRIVER` | `sqlite`, `postgres` |
| `observability` | `OBSERVABILITY` | `phoenix`, `console`, `otlp`, `off` |
| `pricing` | `PRICING_DRIVER` | `genai` (online price table), `static` (your own table) |
| `ratelimit` | `RATE_LIMIT_DRIVER` | `database`, `memory` |
| `auth` | `AUTH_DRIVER` | `default` (API keys + JWT), `anonymous` |
| `vault` | `VAULT_DRIVER` | `fernet` (encrypted at rest), `env` (read-only) |
| `guardrails` | `GUARDRAILS_DRIVER` | `regex` (patterns), `moderation` (policy) |
| `ingest` | `INGEST_DRIVER` | `default` (PDF/DOCX/HTML/text), `text` |
| `audio` | `AUDIO_DRIVER` | `openai` |
| `learning_extractor` | `LEARNING_EXTRACTOR_DRIVER` | `model`, `heuristic` |
| `learning_strategy` | `LEARNING_STRATEGY_DRIVER` | `reflect_apply`, `none` |
| `learning_sink` | `LEARNING_SINK_DRIVER` | `memory` |
| `comms` | `COMMS_DRIVER` | `mailbox`, `broadcast`, `swarm`, `pipeline`, `hub`, `mesh`, `hierarchy`, `outbox`, `blackboard`, `pubsub`, `groupchat`, `handoff` |
| `context` | `CONTEXT_DRIVER` | `isolated`, `shared`, `summarized` |
| `tasks` | `TASKS_DRIVER` | `memory` |
| `planning` | `PLANNING_DRIVER` | `single`, `batched` |
| `agent_middleware` | `AGENT_MIDDLEWARE_DRIVER` | `noop`, `logging` |
| `graph` | `GRAPH_DRIVER` | `sequential`, `parallel`, `checkpointed` |
| `codeexec` | `CODE_EXECUTOR_DRIVER` | `local`, `docker`, `jupyter`, `e2b` |
| `evals_reporter` | `EVALS_REPORTER_DRIVER` | `text`, `json`, `pydantic` |
| `channel` | `CHANNEL_DRIVER` | `log`, `telegram`, `slack`, `email`, `discord` |
| `notification_channel` | `NOTIFICATION_CHANNEL_DRIVER` | `log`, `conversation`, `telegram` |

::: tip Modern conveniences
Some of these run the *newer* agent features: `tasks` (a to-do list),
`codeexec` (running code), `graph` (multi-step workflows), `comms` (agents talking
to each other), `evals_reporter` (test reports). Each has a friendly guide —
[Tasks & Todos](/guide/tasks), [Code Execution](/guide/code-execution),
[Planning & Graphs](/guide/planning), [Agent Communication](/guide/agent-communication),
[Evaluations](/guide/evaluations).
:::

## How a driver is chosen (precedence)

When you ask for a driver, the manager decides in this order:

1. **An explicit name** you pass in code — `app.manager("cache").driver("null")`.
2. **The setting** — e.g. `CACHE_DRIVER`, read from the environment or `.env`.
3. **The default driver** — the one listed first in the table above.

So in normal use, you set one environment variable and forget about it.

## Driver names are typed (no typos)

Every kind and built-in driver name is a `StrEnum`. That is a Python enum whose
members *are* strings, so both of these are the same thing:

```python
from agentkit.support.kinds import CacheDriver

CacheDriver.ARRAY == "array"      # True
```

Because the settings are typed too, a typo is caught the moment your settings
load, not later at runtime:

```python
from agentkit import AgentSettings

AgentSettings(cache_driver="aray")   # ✗ validation error: not a valid CacheDriver
AgentSettings(cache_driver="array")  # ✓ fine
```

## Adding your own driver

There are two audiences.

**Application code** — you want *your app* to use a custom driver. Use
`app.extend`, which is scoped to this app only (it never leaks into other apps or
the global registry):

```python
app.extend(DriverKind.CACHE, "redis", lambda app: RedisCache(app.settings.redis_url))
```

Then select it: `CACHE_DRIVER=redis`.

**A library** — you publish a reusable driver. Use the decorator, which adds it to
the global registry for everyone:

```python
from agentkit import DriverKind, register_driver

@register_driver(DriverKind.CACHE, "redis")
def _redis(app):
    return RedisCache(app.settings.redis_url)
```

A driver needs **no base class**. It just needs the contract's methods. For the
cache that is `get`, `put`, `remember`, `has`, `forget`, `flush`:

```python
class RedisCache:
    def __init__(self, url: str) -> None:
        self.url = url
    def get(self, key, default=None): ...
    def put(self, key, value, ttl=None): ...
    def remember(self, key, factory, ttl=None): ...
    def has(self, key) -> bool: ...
    def forget(self, key) -> None: ...
    def flush(self) -> None: ...
```

::: warning Optional dependencies
If your driver needs a heavy package (Redis, S3, Docker, …), do not import it at
the top of the file. Import it *inside* the driver and raise a `ConfigurationError`
that names the optional **extra** to install, so an unconfigured install still
starts. agentkit's own `groq`/`mistral`/`temporal`/`docker` drivers do exactly
this.
:::

## How we know a driver behaves

A contract says "these methods exist". It does not say "they behave sensibly". So
agentkit keeps **conformance tests**: one behavioral checklist per kind that every
driver must pass. For the cache it is roughly:

- `put` returns the value it stored;
- `has` agrees with `get`;
- `remember` calls your factory and returns its result;
- a key that was never written returns your default;
- after `forget`, the key is gone.

The tests live in `tests/contracts/`. When you add a driver, run them:

```bash
uv run pytest tests/contracts/test_cache_conformance.py
```

## Seeing what is switched on

```bash
agentkit inspect
```

```
drivers: cache=array, embeddings=hash, storage=local, queue=database, ...
```

The web UI and `GET /api/info` show the same `stack.drivers` view, so you can see
at a glance which implementation each subsystem is using.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `ValidationError` when settings load | the `<X>_DRIVER` value is not a valid driver name |
| `ConfigurationError: unknown cache driver 'x'` | you selected a driver that is not registered — check spelling, or `app.extend(...)` it first |
| `ConfigurationError` naming an extra | the driver's optional package is not installed (`pip install agentkit[<extra>]`) |
| A change had no effect | the manager caches drivers per app; call `app.manager(kind).forget()` or rebuild the app |

## Where to go next

- [The Full Stack](/guide/fullstack) — what `.full()` and `fullstack()` turn on.
- [Configuration](/guide/configuration) — settings and layered sections.
- [Tasks & Todos](/guide/tasks) and [Code Execution](/guide/code-execution) —
  two of the newer capabilities.
