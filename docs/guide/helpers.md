# Helpers

## Introduction

Small global functions that resolve against the *current* app — the convenient,
Laravel-style way to reach common services without threading the app through every
call.

```python
from agentkit import app, config, env, dispatch, event, storage, cache, queue, notify
```

| Helper | Returns |
| --- | --- |
| `app(name=None)` | the current `App`, or a resolved binding |
| `resolve(name)` | a binding from the container |
| `config("app.greeting", default)` | dotted config (sections first, then settings) |
| `env("KEY", default)` | an environment variable |
| `dispatch(job)` | dispatch a job (`await dispatch(job)`) |
| `event("name", **payload)` | dispatch an event |
| `notify(notification)` | send a notification |
| `cache()` | the cache store |
| `storage(disk=None)` | the file store (or a named disk) |
| `queue()` | the job queue |
| `logger(name="agentkit")` | a structured logger |
| `report(exc)` | log an exception |

## Examples

```python
config("app.greeting", "Hello")          # registered Section, else a setting
config("model_name")                     # falls back to AgentSettings

env("OPENAI_API_KEY")

await dispatch(SyncNotes())              # inline, or queued when QUEUE_ENABLED
event("note.saved", note_id=1)           # fire an event (see Listeners)

storage().put("exports/notes.json", data)
storage("public").get("logo.svg")        # a named disk

cache().remember("rates", fetch_rates, ttl=300)
```

## `config` resolution

`config("a.b.c", default)`:

1. If `a` is a registered [Section](/guide/configuration#layered-config-sections),
   read field `b.c` from the resolved section.
2. Otherwise walk `settings.a.b.c` (the `AgentSettings` object).
3. Fall back to `default`.

## When to prefer explicit dependencies

Helpers shine in tools, listeners, and commands — anywhere you don't already have
the app. Inside a `Service` or a tool that receives `ctx.deps`, prefer the explicit
dependency (`self.app`, `ctx.deps.repos`): it is easier to test and read.

::: warning Naming
Because these are Python-level globals, `config`/`app`/`cache` shadow the same-named
*submodules* when imported from `agentkit`. They are the helpers here; import
submodules by path (e.g. `from agentkit.config import AgentSettings`).
:::

See also: [Facades](/guide/facades) for the class-method equivalent.
