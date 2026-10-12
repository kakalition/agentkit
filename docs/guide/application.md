# The Application

At the heart of every agentkit service is the **`App`** — a small, explicit
container that owns your settings, a service container, the lifecycle event bus, a
middleware pipeline, and the registries that providers contribute to.

```python
from agentkit import App, AgentSettings

app = App(name="nudge", settings=AgentSettings(owner_id="me"))
```

## The boot lifecycle

`App.boot()` is **idempotent** and ordered:

```
discover providers
      │
      ▼
all Provider.register()   ← pure: bind concerns
      │
      ▼
all Provider.boot()       ← effects: schedules, listeners
      │
      ▼
apply app.schedules([...])
      │
      ▼
mark booted, set current app, dispatch the "boot" event
```

Register-only work happens for *every* provider before *any* provider boots. This
guarantees that when a provider's `boot()` runs, every other provider's bindings
already exist.

```python
app.boot()   # safe to call any number of times
```

::: warning Importing is not booting
Importing a provider module must be side-effect free. Put all binding in
`register()` and all side effects in `boot()`.
:::

## The concerns

An `App` exposes a small, typed surface. Each method is chainable.

| Concern | Purpose |
| --- | --- |
| `app.agent(agent)` | get or set the primary agent (builder or built) |
| `app.tool(fn, ...)` | add a tool to the primary agent |
| `app.channel(name, factory)` | register a long-running channel service |
| `app.commands([...])` | register CLI commands (`Command` instances) |
| `app.schedules([...])` | register durable cron/one-off jobs |
| `app.migrations([...])` | register migrations |
| `app.config(name, Section)` | register a layered config section |
| `app.on(event, listener)` | subscribe to a lifecycle event |
| `app.middleware(mw)` | add turn middleware |
| `app.bind(name, factory)` | bind into the container |

### The agent

```python
from agentkit import Agent

app.agent(
    Agent.make("nudge").persona().instructions("Be concise.").output(str)
)
app.agent()          # → the built PydanticAI agent
```

You may pass either a fluent builder or an already-built PydanticAI agent. Passing
a builder defers construction until first use (and lets the app inject settings and
the event dispatcher).

### Channels

A channel is a long-running service (Telegram, Slack, an HTTP listener, a queue
consumer). Register a factory that receives the app and returns a `Service`:

```python
from agentkit import Service

def slack_channel(app) -> Service:
    def run() -> None:
        ...  # block until shutdown
    return Service("slack", run)

app.channel("slack", slack_channel)
```

`app.serve()` boots the app and runs every channel plus the web UI on its own
daemon thread. See [Deployment](/guide/deployment).

### Commands, schedules, migrations

```python
from agentkit import Command

class SyncCommand(Command):
    name = "sync"
    help = "Sync the knowledge base."
    def run(self, app) -> None:
        ...

app.commands([SyncCommand()])
app.schedules([
    {"name": "digest", "cron": "0 8 * * 1", "task": "digest", "args": {"period": "week"}},
    {"name": "welcome", "when": "2030-01-01T09:00", "task": "welcome"},
])
```

Schedules are persisted as durable jobs at boot.

### Config sections

Register a `Section` schema and read the merged result (defaults < file < env):

```python
from agentkit import Section

class MemorySection(Section):
    env_prefix = "AGENTKIT_MEMORY_"
    enabled: bool = True
    limit: int = 5

app.config("memory", MemorySection)
section = app.config("memory")      # MemorySection(enabled=..., limit=...)
```

See [Configuration](/guide/configuration).

### Events and middleware

```python
app.on("turn.end", lambda event: audit(event.conversation_id))
app.middleware(timing_middleware)
```

See [Events](/guide/events) and [Middleware](/guide/middleware).

## Running turns

### `run`

```python
result = await app.run("hello", conversation_id="cli:default")
print(result.output)
```

`run` opens a repository session, builds the typed dependencies, and executes the
turn through the middleware pipeline. It returns a
[`ChatResult`](/reference/api) with `output`, `artifacts`, `history_length`,
`usage`, and `tool_calls`.

### `stream`

```python
async for event in app.stream("hello"):
    if event.kind == "text":
        print(event.text, end="", flush=True)
    elif event.kind == "final":
        print("\n" + event.result.output)
```

See [Streaming](/guide/streaming).

### `answer`

The `answer` property is a `(conversation_id, text) -> ChatResult` callable — the
exact shape the web UI, A2A, and MCP surfaces expect:

```python
answer = app.answer
```

### `resume`

Continue a turn that deferred tool calls (approvals or clarification):

```python
result = await app.resume(deferred_tool_results, conversation_id="cli:default")
```

See [Human-in-the-Loop](/guide/hitl).

### `fork` and `replay`

Branch a conversation, or re-run its last user prompt (e.g. against a new model):

```python
app.fork("cli:main", "cli:experiment")          # copy messages
result = await app.replay("cli:main", target="cli:replay")
```

## Serving

```python
app.serve(webui=True)          # blocks; runs channels + web UI
```

Under the hood this boots the app and hands every channel service to
`agentkit.supervise.run_all`, which starts each on a daemon thread, installs
`SIGINT`/`SIGTERM` handlers, and seeds the current `App` into each worker thread —
so [facades](/guide/facades) resolve inside channels.

## Providers and discovery

Providers can be registered explicitly, or discovered from the
`agentkit.providers` entry-point group:

```python
app.providers([NudgeProvider, TelegramProvider])   # explicit
app = App(discover=False)                          # opt out of discovery
```

A package publishes a provider by adding one line to its `pyproject.toml`:

```toml
[project.entry-points."agentkit.providers"]
nudge = "nudge.providers:NudgeProvider"
```

## Settings

`app.settings` resolves an `AgentSettings` instance. You may pass an instance, a
settings *class*, or nothing (in which case the defaults + environment are used):

```python
App(name="nudge", settings=Settings)     # a subclass; instantiated on access
```
