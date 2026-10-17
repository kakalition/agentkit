# Tools

## Introduction

Tools are how an agent *acts*. A tool is an ordinary Python function; agentkit adds
conveniences for registration, approval, caching, and composition.

## Writing a tool

Tools receive a PydanticAI `RunContext` as their first argument (typed with your
`Deps`), followed by annotated parameters. The docstring becomes the tool
description the model sees.

```python
from pydantic_ai import RunContext
from agentkit.deps import Deps

async def add_note(ctx: RunContext[Deps], text: str, *, pinned: bool = False) -> str:
    """Save a note for the owner.

    Args:
        text: The note body.
        pinned: Keep it at the top of the list.
    """
    await ctx.deps.repos.notes.add(text=text, pinned=pinned)
    return f"saved: {text}"
```

Register it on the definition:

```python
from agentkit import AgentDefinition

class Assistant(AgentDefinition):
    name = "assistant"
    tools = [add_note]
```

Fluent equivalent: `agent.tool(add_note)`.

::: tip Describe your arguments
PydanticAI derives the JSON schema from the annotations and the docstring. Clear
param descriptions measurably improve tool-calling accuracy.
:::

## Reaching the dependencies

`ctx.deps` is your typed dependency object. By default it is `agentkit.Deps`,
which carries the settings, repositories, model, approvals handler, artifacts, and
an `extras` dict for anything else:

```python
settings = ctx.deps.settings
repos = ctx.deps.repos
ctx.deps.extras["trace_id"] = ...
ctx.deps.remember_artifact("chart", "/tmp/chart.png", "revenue by month")
```

## Common options

Per-tool options are applied in `configure(self, agent)`:

```python
from agentkit import AgentDefinition

class Assistant(AgentDefinition):
    name = "assistant"

    def configure(self, agent):
        agent.tool(
            delete_note,
            requires_approval=True,   # defer to a human before running
            retries=2,                # retry on failure
            timeout=10.0,             # seconds
            sequential=True,          # do not run concurrently with other tools
            defer_loading=True,       # only expose the schema when relevant
            cache_ttl=60,             # cache results for 60s
        )
        return agent
```

Fluent equivalent: `agent.tool(delete_note, requires_approval=True, retries=2, timeout=10.0, sequential=True, defer_loading=True, cache_ttl=60)`.

| Option | Meaning |
| --- | --- |
| `requires_approval` | The tool call is deferred until a human approves it |
| `retries` | Retry the tool on failure |
| `timeout` | Per-call timeout in seconds |
| `sequential` | Serialise this tool against concurrent calls |
| `defer_loading` | Hide the schema until the model asks (pairs with `.tool_search()`) |
| `cache_ttl` | Cache results by arguments for N seconds |

### Caching results

`cache_ttl` wraps the tool with `agentkit.cache.cached_tool` — a small TTL cache
keyed on the arguments (the `RunContext` is ignored). It is ideal for expensive,
pure lookups:

```python
from agentkit import AgentDefinition, cached_tool

class Assistant(AgentDefinition):
    name = "assistant"
    tools = [cached_tool(geocode, ttl=3600)]
```

Fluent equivalent: `agent.tool(cached_tool(geocode, ttl=3600))`.

## Toolsets

A **toolset** is a bundle of tools (a PydanticAI `FunctionToolset`, an MCP toolset,
and so on). Declare one with the `toolsets` field:

```python
from pydantic_ai import FunctionToolset
from agentkit import AgentDefinition

math_tools = FunctionToolset(tools=[add, multiply])

class Assistant(AgentDefinition):
    name = "assistant"
    toolsets = [math_tools]
```

Fluent equivalent: `agent.toolset(math_tools)`.

### MCP toolsets

The [MCP registry](/guide/protocols) exposes each server as a prefixed toolset —
`<server>_<tool>` — so servers that share tool names never collide:

```python
from agentkit import AgentDefinition
from agentkit.mcp import MCPRegistry, MCPServerSpec

registry = MCPRegistry([
    MCPServerSpec(name="chart", command="uvx", args=["mcp-server-chart"]),
])

# inside your async setup:
toolset = await registry.toolset("chart")   # tools appear as chart_*

class ChartAgent(AgentDefinition):
    name = "chart"
    toolsets = [toolset]
```

Fluent equivalent: `agent.toolset(toolset)`.

## Delegation tools

The most powerful "tool" is another agent. The `specialists` field turns an agent
into a delegation tool, forwarding usage and model so accounting stays correct:

```python
from agentkit import AgentDefinition

class Desk(AgentDefinition):
    name = "desk"
    specialists = {"handle_reminders": (reminder_agent, "Set reminders.")}
```

Fluent equivalent: `agent.specialist(reminder_agent, name="handle_reminders", description="Set reminders.")`.

For explicit, awaitable sub-tasks (rather than model-chosen delegation), use
`spawn_tool` from [Multi-Agent Teams](/guide/teams).

## Approval-gated tools

Mark risky tools with `requires_approval=True` and enable approvals on the agent:

```python
from agentkit import AgentDefinition

class Desk(AgentDefinition):
    name = "desk"
    instructions = "…"
    approvals = True

    def configure(self, agent):
        agent.tool(send_email, requires_approval=True)
        return agent

agent = Desk.build()
```

Fluent equivalent: `agent = Agent.make("desk").instructions("…").approvals().tool(send_email, requires_approval=True).build()`.

When the model calls `send_email`, the run is deferred. The app raises an
`approval.asked` event and your `app.on("approval.asked", ...)` listener (or the
web UI / Telegram broker) decides. See [Human-in-the-Loop](/guide/hitl).

## Errors and retries

Raise `ModelRetry` to ask the model to fix its call; raise any other exception to
fail the tool (and optionally retry):

```python
from pydantic_ai import ModelRetry

async def divide(ctx, a: float, b: float) -> float:
    """Divide a by b."""
    if b == 0:
        raise ModelRetry("b must be non-zero")
    return a / b
```

## Testing tools

Tools are plain functions — call them directly with a stub `RunContext`:

```python
class FakeCtx:
    deps = Deps(settings=settings, repos=repos)

assert await add_note(FakeCtx(), "hello") == "saved: hello"
```

## Tools from an OpenAPI spec

Turn any OpenAPI document into tools with `tools_from_openapi` (or attach them
directly to a built agent):

```python
from agentkit import AgentDefinition, register_openapi_tools, tools_from_openapi

class Api(AgentDefinition):
    name = "api"
    instructions = "…"
    output = str
    tools = tools_from_openapi("openapi.json", base_url="https://api.example.com")

agent = Api.build()
register_openapi_tools(agent, "openapi.json", base_url="https://api.example.com")
```

Fluent equivalent:

```python
from agentkit import Agent

tools = tools_from_openapi("openapi.json", base_url="https://api.example.com")
agent = Agent.make("api").instructions("…").output(str).build()
register_openapi_tools(agent, "openapi.json", base_url="https://api.example.com")
```

Each operation becomes a tool taking a single `params` mapping; path parameters
are substituted and the rest go to the query string (GET/DELETE) or JSON body.
Pass an `httpx.AsyncClient` via `client=` to reuse a pool or to test.

Continue to [Configuration →](/guide/configuration)
