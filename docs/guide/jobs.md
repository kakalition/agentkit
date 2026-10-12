# Jobs, Cache & Utilities

Small building blocks every agent eventually needs: dispatched work, a cache, file
storage, validation, and base classes for services and listeners.

## Jobs

A **job** is a unit of work you can dispatch. When durability is initialised
(`durability.init(...)`) it runs as a durable, retryable workflow; otherwise it
runs inline.

```python
from agentkit import Job

class SyncKnowledge(Job):
    queue = "default"
    max_retries = 2

    def __init__(self, source: str) -> None:
        self.source = source

    def handle(self, app) -> None:
        kb = app.make("knowledge")
        kb.add_directory(self.source)

await app.dispatch(SyncKnowledge("./docs"))
```

`handle` may be sync or async. Use jobs for work that shouldn't run inline in a
turn — imports, exports, embeds, long tool calls.

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
        with self.repositories() as repos:
            return repos.reminders.pending()

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
