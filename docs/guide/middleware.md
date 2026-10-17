# Middleware

## Introduction

Middleware wraps a turn. Register it with `app.middleware(...)` and it runs once
around every `app.run` / `app.stream`, in the order you add it.

```python
app.middleware(timing_middleware)
```

## Writing middleware

Middleware is an async callable `(turn, call_next)`. Call `call_next()` to continue
the chain; read or rewrite `turn` before or after.

```python
import time, logging

log = logging.getLogger("app")

async def timing(turn, call_next):
    start = time.perf_counter()
    turn = await call_next()
    log.info("turn %s took %.3fs", turn.conversation_id, time.perf_counter() - start)
    return turn
```

The `turn` is a small object with `conversation_id`, `text`, `approve`, and
`result` (the `ChatResult`, set by the terminal handler):

```python
async def rewrite(turn, call_next):
    turn.text = turn.text.strip().lower()
    return await call_next()
```

## Ordering

Middleware is a stack: the first added is the outermost.

```python
app.middleware(auth)
app.middleware(rate_limit)
app.middleware(logging)

# auth → rate_limit → logging → turn
```

## Short-circuiting

Return without calling `call_next()` to stop the turn. Set `turn.result` yourself:

```python
from agentkit.session import ChatResult

async def cache(turn, call_next):
    hit = cache.get(turn.text)
    if hit is not None:
        turn.result = ChatResult(output=hit, history_length=0)
        return turn
    turn = await call_next()
    cache.set(turn.text, turn.result.output)
    return turn
```

## Built-in middleware

`agentkit.moderation.moderation_middleware` screens (and can redact) each input:

```python
from agentkit.moderation import moderation_middleware, ModerationPolicy

app.middleware(moderation_middleware(ModerationPolicy(banned=["…"], redact_pii=True)))
```

`agentkit.foundation.middleware.logging_middleware()` logs each turn's id and
duration.

## Middleware vs. capabilities

There are two seams, and they solve different problems:

| Seam | Scope | Use for |
| --- | --- | --- |
| Turn middleware (`app.middleware`) | the whole turn | auth, rate limiting, caching, moderation of inputs |
| Capability hooks (`.capability(...)`) | inside the agent | tool start/end, tool arguments, model output |

Capabilities are provided by PydanticAI's `Hooks`; agentkit ships helpers. Capability
hooks have no class field, so declare them in `configure(self, agent)`:

```python
from agentkit import AgentDefinition
from agentkit.foundation.middleware import lifecycle_hooks, policy_hooks, guardrails_hooks


class X(AgentDefinition):
    name = "x"

    def configure(self, agent):
        return agent.capability(guardrails_hooks())


agent = X.build()
```

Fluent equivalent:

```python
agent = Agent.make("x").capability(guardrails_hooks()).build()
```

- `lifecycle_hooks()` — emits `tool.start` / `tool.end`
- `policy_hooks(policy)` — enforces a `ToolPolicy`
- `guardrails_hooks()` — scans tool results for prompt injection

## A realistic example

Combine authentication middleware with a capability that audits tools. The turn
middleware is app-level and unchanged; the tool-auditing capability is declared on
the agent class (it has no class field, so use `configure`):

```python
from agentkit import AgentDefinition


async def authenticate(turn, call_next):
    if turn.conversation_id not in allowed_conversations():
        raise PermissionDenied("not allowed in this conversation")
    return await call_next()

app.middleware(authenticate)


class Assistant(AgentDefinition):
    name = "assistant"

    def configure(self, agent):
        return agent.capability(lifecycle_hooks())   # emits tool.start / tool.end events
```

Continue to [Models & Database →](/guide/database)

## Agent middleware

### What this is, in plain English

There are two different moments you might want to hook into, and agentkit keeps
them as two separate, clearly named seams.

- A **turn** is one whole round of conversation: the user sends a message, the
  agent thinks, calls *any number* of tools, and finally produces a reply. Turn
  middleware (the "Writing middleware" section above) wraps that entire round,
  once. It is the right place for authentication, rate limiting, caching, and
  input moderation.

- A **model call** is one single request to the language model. A **tool call** is
  one single execution of a tool the model asked for. A turn usually contains
  *several* of each: the model asks for a tool, sees the result, asks for another
  tool, then answers. **Agent middleware** wraps these individual calls, so you can
  see or change what happens *inside* a turn, call by call.

The everyday analogy: turn middleware is the **reception desk** of an office — it
sees each visitor once, on the way in and on the way out. Agent middleware is the
**hallway cameras and door sensors** inside — they record every time someone
enters a room (a model call) or uses a machine (a tool call). The desk controls
who gets into the building; the sensors describe what happens once inside.

Agent middleware offers six optional hooks. Subclass `BaseAgentMiddleware` and
override only the ones you need:

| Hook | Runs | Use it to |
| --- | --- | --- |
| `before_model(ctx)` | just before a model call | log, or start a timer |
| `after_model(ctx, response)` | just after a model call returns | inspect or replace the response |
| `before_tool(ctx, name, args)` | before a tool runs | validate or rewrite arguments |
| `after_tool(ctx, name, result)` | after a tool returns | cache or audit the result |
| `wrap_model_call(ctx, call_next)` | around a model call | short-circuit by not calling `call_next()` |
| `wrap_tool_call(ctx, name, call_next)` | around a tool call | wrap the call (for example, add a cache around it) |

::: tip All hooks are optional
`BaseAgentMiddleware` implements every hook as a pass-through, so a subclass can
override just one method. The `before_*`/`after_*` hooks are notifications; the
`wrap_*_call` hooks receive a `call_next` coroutine and may skip it to
short-circuit.
:::

### A runnable example

```python
from agentkit import App, DriverKind

app = App()   # default agent middleware: AGENT_MIDDLEWARE_DRIVER=noop

# Turn middleware wraps a WHOLE turn (async `(turn, call_next)`).
async def authenticate(turn, call_next):
    if turn.conversation_id not in allowed_conversations():
        raise PermissionDenied("not allowed in this conversation")
    return await call_next()

app.middleware(authenticate)

# 1. The default agent middleware does nothing at all.
print(type(app.agent_middleware).__name__)          # NoopMiddleware

# 2. Switch to the built-in `logging` driver to trace each model/tool call.
mw = app.manager(DriverKind.AGENT_MIDDLEWARE).driver("logging")
print(type(mw).__name__)                            # LoggingMiddleware
```

### Built-in drivers

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `noop` | Default. Every hook is a pass-through; nothing is changed or logged. | You do not need per-call hooks, or you are registering your own middleware. |
| `logging` | Logs each model call and each tool call and result at debug level. | You are debugging and want to see the model and tool calls inside a turn. |

### Selecting a driver

Precedence is the usual one: explicit name, then setting, then default.

```bash
# .env
AGENT_MIDDLEWARE_DRIVER=logging
```

**Per app only.** Register a scoped factory with `app.extend`:

```python
from agentkit import App, DriverKind
from agentkit.foundation.agent_middleware import BaseAgentMiddleware

class CacheMiddleware(BaseAgentMiddleware):
    async def wrap_tool_call(self, ctx, name, call_next):
        return await call_next()

app = App()
app.extend(DriverKind.AGENT_MIDDLEWARE, "cache", lambda app: CacheMiddleware())
```

**Reusable driver.** Ship it to the global registry with the decorator:

```python
from agentkit import DriverKind, register_driver

@register_driver(DriverKind.AGENT_MIDDLEWARE, "audit")
def _audit(app):
    return AuditMiddleware()   # a BaseAgentMiddleware subclass
```

Read more on [Contracts & Drivers](/guide/drivers).

### Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Your hooks never run | the middleware object is not the configured driver — select it with `AGENT_MIDDLEWARE_DRIVER` or resolve it by name |
| A hook fires far more often than expected | you are hooking a *model* or *tool* call, not a turn; one turn contains several of each |
| `ConfigurationError: unknown agent_middleware driver 'x'` | the name is misspelled or not registered / `extend`ed |
| A change had no effect | the manager caches drivers per app; rebuild the app or `forget()` the driver |
