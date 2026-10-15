# Async Data Layer

## Introduction

agentkit's data layer is **async by default**. The engine, the repository
container, the `Model`/`Repository` helpers, conversations, memory, knowledge and
the web UI all speak `async`/`await`, so a single event loop serves concurrent
turns, sub-agents and channel handlers without serialising on a global lock.

Only synchronous seams that cannot be async — DBOS workflow/step bodies and
build-time bootstrapping — bridge into the async layer explicitly, and they do so
on a private event loop rather than the caller's. Everything application code
touches is a coroutine.

## The runtime

```python
from agentkit import build_runtime, repositories

runtime = build_runtime(settings)          # creates the async engine (no I/O)
async with repositories(runtime) as repos:  # opens a session, commits on exit
    await repos.conversations.get_or_create("cli:default")
```

`build_runtime` is still synchronous — it constructs an `AsyncEngine`, a session
factory, and configures the embedder, but does not connect. The schema is created
lazily, once, on the first `repositories(...)` scope.

::: tip Too many open sessions?
Prefer `app.repositories()`. The `App` owns one runtime and hands you a scope;
`DB.transaction()` makes that scope *ambient* so `await Note.create(...)` joins the
same session.
:::

## Local SQLite is the default

The local database URL (`sqlite+libsql`) is mapped to the async `sqlite+aiosqlite`
driver automatically. WAL and a busy timeout are enabled per connection, and the
engine uses `NullPool` so a connection is never reused across event loops.

## Concurrency

- **Writer serialisation.** SQLite is still single-writer; a bounded busy timeout
  makes concurrent writers wait rather than fail with `database is locked`.
- **Off-loop CPU work.** Embedding and chunking run via `asyncio.to_thread`, so
  the loop keeps serving requests.
- **Per-conversation state.** `Compactor` keeps rolling state per conversation;
  the mailbox and cache are guarded by async locks/queues.

## The synchronous seams

Two places cannot be async and are bridged with
`agentkit._sync.run_sync`, which runs the coroutine to completion on a private
loop (never nesting `asyncio.run` inside a running loop):

1. **DBOS workflows/steps.** The scheduler's module-level decorated functions stay
   sync and call `run_sync(...)` for their database work.
2. **Build-time bootstrapping.** Persisting schedules and indexing knowledge while
   a builder/app boots.

```python
from agentkit._sync import run_sync

def tick(scheduled_time=None, context=None) -> list[str]:
    due = _load_due_step(now_iso)   # a DBOS step; DB work runs off the loop
    ...
```

## Async low-level building blocks

`asyncio.shield` protects a turn's persistence from cancellation, `gather` fans out
to sub-agents in the orchestrator, and `asyncio.Lock`/`Semaphore` guard shared
state (cache, registry, mailbox).

## Upgrading from sync code

```python
# before
with runtime.repositories() as repos:
    repos.memories.add("...")

# after
async with runtime.repositories() as repos:
    await repos.memories.add("...")
```

`Model` and `Repository` terminals are coroutines now
(`await Reminder.where(done=False).first()`), and forced tool calls are awaited
(`await Checkpoint.force(...)`).

::: warning Breaking change
Every repository method, `Model`/`Repository` terminal, `DB.session()`,
`DB.transaction()`, `ChatRunner`, `KnowledgeBase`, and the `Memory`/`Feedback`/
`Queue`/`Schedule` facades are now coroutines. See the [CHANGELOG](https://github.com/)
for the full list.
:::
