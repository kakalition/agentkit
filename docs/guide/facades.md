# Facades

## Introduction

Facades give you a terse, expressive syntax for reaching into the application
container. Instead of resolving a service by hand, you call a static method on a
facade class, and it resolves against the **current app**.

```python
from agentkit import Memory, Schedule, DB, Events, Log, Feedback

await Memory.remember("The owner prefers dark mode")
await Schedule.cron("weekly", "0 8 * * 1", "digest")
```

## The facades

| Facade | Binding | Backed by |
| --- | --- | --- |
| `Memory` | `memory` | `repos.memories` |
| `Schedule` | `schedule` | the durable scheduler |
| `DB` | `db` | repository sessions/transactions |
| `Events` | `events` | the app event dispatcher |
| `Log` | `log` | structured logging |
| `Feedback` | `feedback` | user feedback repo |

### Memory

```python
await Memory.remember("My name is Ada", kind="person")
await Memory.search("name")           # list of matching facts
await Memory.all(limit=20)
await Memory.forget(memory_id)
await Memory.digest()                 # a text digest for the instructions
```

### Schedule

```python
@Schedule.task("digest")
def digest(period: str = "week") -> None: ...

await Schedule.cron("weekly", "0 8 * * 1", "digest", args={"period": "week"})
await Schedule.once("welcome", "2030-01-01T09:00", "digest")
await Schedule.list()
await Schedule.enable("weekly"); await Schedule.disable("weekly"); await Schedule.remove("weekly")
```

### DB

```python
with DB.transaction() as repos:
    await repos.notes.add(text="hello")   # Model.create calls join this session

with DB.session() as session:
    ...
```

A `DB.transaction()` block makes its repositories **ambient**, so
[models](/guide/database) created inside it join the same session and commit
together.

### Events

```python
Events.listen("turn.end", my_listener)
await Events.dispatch_async("custom", detail="…")
```

### Feedback

```python
await Feedback.add(1, conversation_id="cli:1", comment="helpful")
await Feedback.average(conversation_id="cli:1")
await Feedback.list(limit=20)
```

### Learning & native tools

Native toolkits and self-learning are **agent-callable tools**, not facades, so they
are attached on the builder rather than resolved from the container. The library
exports the underlying functions when you need them directly:

```python
from agentkit import (
    attach_learning, reflect, lessons_digest, register_reflect_task, LearningSignals,
    attach_toolkits, enabled_toolkits, TOOLKITS,
)
```

```python
async with app.repositories() as repos:
    await reflect(repos)                 # distil lessons now
    print(await lessons_digest(repos))   # the instructions digest

enabled_toolkits(app.settings)           # the settings-enabled toolkit names
```

See [Native Tools](/guide/native-tools) and [Self-Learning](/guide/self-learning).

## How resolution works

A facade resolves `current_app().make("<binding>")` at call time. The current app
is tracked in **both** a `contextvars` variable (for async code) and a
thread-local, and `run_all` seeds the app into its worker threads. That means a
facade works inside a channel thread, where a contextvar alone would not
propagate.

```python
from agentkit import current_app, using

current_app()          # the current App (raises if none)

with using(app):       # scope explicitly
    await Memory.all()
```

You can scope a facade too:

```python
with Memory.using(app):
    await Memory.remember("scoped")
```

## Building your own facade

Subclass `Facade` and return a binding name:

```python
from agentkit import Facade

class Notes(Facade):
    @classmethod
    def binding(cls) -> str:
        return "notes"

# then, after app.bind("notes", ...):
await Notes.create(text="hello")
```

::: warning When to use facades
Facades are convenient in tools, listeners, and request handlers. In code that
already has `ctx.deps` or an `app` reference, prefer passing it explicitly —
explicit dependencies are easier to test and read.
:::

Continue to [Events & Lifecycle →](/guide/events)
