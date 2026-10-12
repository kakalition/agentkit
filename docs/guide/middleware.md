# Middleware

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

Capabilities are provided by PydanticAI's `Hooks`; agentkit ships helpers:

```python
from agentkit.foundation.middleware import lifecycle_hooks, policy_hooks, guardrails_hooks

agent = Agent.make("x").capability(guardrails_hooks()).build()
```

- `lifecycle_hooks()` — emits `tool.start` / `tool.end`
- `policy_hooks(policy)` — enforces a `ToolPolicy`
- `guardrails_hooks()` — scans tool results for prompt injection

## A realistic example

Combine authentication middleware with a capability that audits tools:

```python
async def authenticate(turn, call_next):
    if turn.conversation_id not in allowed_conversations():
        raise PermissionDenied("not allowed in this conversation")
    return await call_next()

app.middleware(authenticate)
agent.capability(lifecycle_hooks())     # emits tool.start / tool.end events
```

Continue to [Models & Database →](/guide/database)
