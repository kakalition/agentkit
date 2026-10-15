# Jobs, Cache & Utilities

## Introduction

Small building blocks every agent eventually needs: dispatched work, a cache, file
storage, validation, and base classes for services and listeners.

## Jobs

A **job** is a unit of work you can dispatch — inline or onto the durable queue.

```python
from agentkit import Job

class SyncKnowledge(Job):
    queue = "default"
    max_retries = 3

    def __init__(self, source: str) -> None:
        self.source = source

    async def handle(self, app) -> None:
        from agentkit import KnowledgeBase

        await KnowledgeBase(app).add_directory(self.source)

await app.dispatch(SyncKnowledge("./docs"))
```

`handle` may be sync or async. Jobs store their constructor arguments on `self` so
they can be serialized when queued.

### Inline vs. queued

By default (`QUEUE_ENABLED=false`) `app.dispatch(job)` runs the job **inline** (a
durable workflow when durability is initialised). Set `QUEUE_ENABLED=true` and the
job is persisted to the `queued_jobs` table and processed by a worker:

```bash
QUEUE_ENABLED=true agentkit queue:work            # long-running worker
agentkit queue:work --once                        # process what's available, exit
agentkit queue:work --queue=default --max-jobs 10
agentkit queue:failed                             # list failed jobs
```

```python
from agentkit import Queue

await Queue.push(SyncKnowledge("./docs"), delay=60)   # enqueue with a delay
await Queue.size()                                    # pending count
await Queue.run_once()                                # process one (in-process)
```

Failed jobs retry up to `max_retries`, then are marked failed with their error and
listed by `queue:failed`. Jobs are identified by their import path, so keep job
classes at module scope.

### Enqueuing from the agent

The native [queue toolkit](/guide/native-tools#queue) lets the model enqueue work
directly. `enqueue_job` dispatches an allow-listed `Job` class; `enqueue_task` wraps
a registered scheduler task in a `RunRegisteredTask` job, so one allow-list covers
both the scheduler and the queue:

```python
from agentkit.toolkits import RunRegisteredTask

agent.queue({"sync": SyncKnowledge}).scheduler(["sync_notes"])
```

Both tools are approval-gated and respect `QUEUE_ENABLED`.

## Cache

```python
from agentkit import Cache

Cache.put("rates", rates, ttl=300)
Cache.get("rates")                       # None once expired
Cache.remember("rates", fetch_rates, ttl=300)
Cache.has("rates"); Cache.forget("rates"); Cache.flush()
```

The default store is a small in-process TTL cache (`CacheStore`). Swap it by
binding a different one in the container.

## Storage

A root-confined filesystem under `<agent_home>/storage`, for artifacts and
exports:

```python
from agentkit import Storage

Storage.put("reports/q4.md", "…")
Storage.get("reports/q4.md")
Storage.list("reports")
Storage.exists("reports/q4.md"); Storage.delete("reports/q4.md")
Storage.metadata("reports/q4.md")
```

Paths are confined to the store; escapes raise. For untrusted code execution, use a
[workspace](/guide/multimodal#sandbox) instead.

## Validation

Validate tool/job input with rules (strings or callables):

```python
from agentkit import Rule, validate

data = validate(
    {"text": "stretch", "when": "in 5 minutes"},
    {
        "text": ["required", "string", "max:200"],
        "when": ["required", "regex:^(in |at |tomorrow|tonight|next )"],
    },
)
```

Built-in rules: `required`, `string`, `integer`, `number`, `boolean`, `email`,
`min:n`, `max:n`, `between:a,b`, `in:a,b,c`, `regex:pattern`, plus any callable
`fn(value) -> str | None`. Failures raise `ValidationError` with a per-field map in
`exc.detail["errors"]`.

## Service base class

A `Service` wires the app in and hands you settings, repositories, the container,
notifications, and scheduling:

```python
from agentkit.foundation.service import Service

class ReminderService(Service):
    def upcoming(self, conversation_id: str) -> list:
        async with self.repositories as repos:
            return await repos.reminders.pending()

service = ReminderService(app)
```

::: tip Why `agentkit.foundation.service`
It is separate from `agentkit.Service` (the long-running *channel* service used by
`run_all`). Import the domain base from `agentkit.foundation.service`.
:::

## Listener & Middleware base classes

```python
from agentkit import Listener, Middleware

class AuditTurns(Listener):
    event = "turn.end"
    def handle(self, event) -> None:
        audit(event.conversation_id, event.output)

app.on("turn.end", AuditTurns())

class Timing(Middleware):
    async def handle(self, turn, call_next):
        start = time.perf_counter()
        result = await call_next()
        log.info("%s took %.3fs", turn.conversation_id, time.perf_counter() - start)
        return result

app.middleware(Timing())
```

Both instances are callable, so they plug into `app.on(...)` / `app.middleware(...)`
directly. See [Events](/guide/events) and [Middleware](/guide/middleware).

## Drivers

### What this is, in plain English

A **job** is a small package of work you want done: "re-index these documents",
"send this email". The **queue** is the holding area that keeps those packages
until a worker runs them.

- With the `database` queue, a job is written as a row in the database and a
  worker picks it up later. This is **durable**: if your program crashes between
  dispatch and completion, the job is still there afterward and can be retried.
- With the `sync` queue, there is no holding area at all — the job runs
  immediately, in the same call, and nothing is persisted.

A **cache** is the opposite kind of tool: a tiny, throwaway key/value store for
answers you do not want to recompute. "Remember this exchange rate for five
minutes." The default keeps those values in memory for the life of the process.

::: tip The restaurant analogy
The queue is the ticket rail in a kitchen: the waiter clips an order onto it, and
cooks work through the tickets one at a time — a ticket survives even while the
kitchen is busy. The `sync` queue is calling the order out and cooking it on the
spot. The cache is the tray of prepped ingredients: cheap to grab again, and
thrown out when it goes off (its TTL, "time to live").
:::

### A runnable example

```python
import asyncio
from agentkit import App, DriverKind, Job

class SyncNotes(Job):                 # jobs store their arguments on self so they
    queue = "default"                 # can be serialized when queued
    max_retries = 3

    def __init__(self, source: str) -> None:
        self.source = source

    async def handle(self, app) -> None:
        from agentkit import KnowledgeBase

        await KnowledgeBase(app).add_directory(self.source)

async def main():
    app = App()                       # QUEUE_DRIVER=database, CACHE_DRIVER=array
    print(app.manager(DriverKind.QUEUE).available())   # ['database', 'sync']
    print(app.manager(DriverKind.CACHE).available())   # ['array', 'null']

    await app.dispatch(SyncNotes("./docs"))   # queued, or inline when QUEUE_ENABLED=false

    app.cache.put("rates", {"usd": 1.0}, ttl=300)      # cached for 5 minutes
    print(app.cache.get("rates"))

asyncio.run(main())
```

Switch the whole application by changing the environment variables:

```bash
QUEUE_ENABLED=true           # persist to the queue and let a worker run jobs
QUEUE_DRIVER=sync            # skip the queue: run every job immediately, inline
CACHE_DRIVER=null            # disable caching entirely (remember() still resolves)
```

::: warning `QUEUE_ENABLED` vs `QUEUE_DRIVER`
They do different things. `QUEUE_ENABLED` decides *whether* dispatching is
deferred to background processing; `QUEUE_DRIVER` decides *how* the queue is
implemented. With `QUEUE_ENABLED=false` (the default) `app.dispatch(job)` runs the
job inline regardless of the queue driver.
:::

### Built-in drivers

**Queues — setting `QUEUE_DRIVER`**

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `database` | Persists jobs to the `queued_jobs` table; a worker runs them and retries failures | Default. Work must survive restarts |
| `sync` | Runs each job inline immediately, persisting nothing | Tests and simple apps with no background worker |

**Caches — setting `CACHE_DRIVER`**

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `array` | In-process TTL key/value store with a bounded size | Default; short-lived, per-process caching |
| `null` | Stores nothing; `remember` still calls its factory each time | Disabling caching, or in tests |

The contracts: a queue driver provides `push`, `run_once`, `size`, and `failed`;
a cache driver provides `get`, `put`, `remember`, `has`, `forget`, and `flush`.

### How to select it

Selection follows the same precedence everywhere in agentkit:

1. **An explicit name in code** — `app.manager(DriverKind.QUEUE).driver("sync")`.
2. **The setting** — `QUEUE_DRIVER` or `CACHE_DRIVER`, read from the environment
   or a `.env` file.
3. **The default** — `database` and `array`, listed first in the tables above.

**Accessors:** `app.queue` returns the configured queue and `app.cache` the
configured cache; the managers are `DriverKind.QUEUE` and `DriverKind.CACHE`.

Override a driver for one app only (this never leaks into other apps or the global
registry):

```python
from agentkit import DriverKind

app.extend(DriverKind.CACHE, "redis", lambda app: RedisCache(app.settings.redis_url))
# then select it: CACHE_DRIVER=redis
```

Ship a reusable driver to every app that imports your package with
`@register_driver`:

```python
from agentkit import DriverKind, register_driver

@register_driver(DriverKind.CACHE, "redis")
def _redis(app):
    return RedisCache(app.settings.redis_url)
```

A driver needs no base class — only the contract's methods. See
[Contracts & Drivers](/guide/drivers) for the full catalog, precedence, and the
conformance tests every driver must pass.

### Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| A dispatched job never runs | `QUEUE_ENABLED=false` so it ran inline, or no worker (`agentkit queue:work`) is running |
| Jobs are lost after a restart | You selected the `sync` queue, which persists nothing |
| A cached value is `None` | The key expired (TTL) or `CACHE_DRIVER=null` |
| Jobs fail repeatedly | The job raised an error; inspect `agentkit queue:failed`, and keep job classes at module scope |
| `ValidationError` when settings load | A `*_DRIVER` value is not a valid driver name |
