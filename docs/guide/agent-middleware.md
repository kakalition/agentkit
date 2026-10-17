# Agent Middleware

Turn middleware (`Middleware`) wraps a whole turn. **Agent middleware** wraps each
*model request* and *tool execution* inside a turn — the right seam for retries,
redaction, caching, or per-call observability.

## Registering middleware

Pass one or more middleware to the builder:

```python
from agentkit import Agent, AgentMiddlewareCapability, BaseAgentMiddleware


class RetryOnce(BaseAgentMiddleware):
    async def wrap_model_call(self, ctx, call_next):
        try:
            return await call_next()
        except Exception:
            return await call_next()


agent = (
    Agent.make("writer")
    .instructions("Be concise.")
    .agent_middleware(RetryOnce())
    .output(str)
    .build()
)
```

`BaseAgentMiddleware` implements every hook as a pass-through, so subclass only
what you need. Hooks run in list order: `before_*` forwards, `after_*` in reverse,
and `wrap_*_call` nest with the first middleware outermost.

## Hooks

| Hook | Purpose |
| --- | --- |
| `before_model(ctx)` | observe/enrich before a model request |
| `after_model(ctx, response)` | inspect or replace the response |
| `wrap_model_call(ctx, call_next)` | fully control the model call |
| `before_tool(ctx, name, args)` | inspect or replace tool args (raise to deny) |
| `after_tool(ctx, name, result)` | inspect or replace the tool result |
| `wrap_tool_call(ctx, name, call_next)` | short-circuit or wrap a tool call |

`ctx` is an `AgentCallContext`: it exposes `run` (the PydanticAI `RunContext`),
`request`/`tool`, `name`, and a shared `state` dict so a `wrap_*` hook can enrich
what a later `after_*` hook observes.

## The default driver

When you do not pass middleware explicitly, the app's configured driver is used
(`agent_middleware_driver`, default `noop` — a pass-through with no cost). Set it
to `logging` for a structured record of every model/tool call:

```python
# kilo.json / environment
agent_middleware_driver=logging
```

Middleware also runs on `app.stream(...)` and `app.resume(...)`, and those paths
pass the `Turn` context to `model_resolver` exactly like `app.run(...)`.
