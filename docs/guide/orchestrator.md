# Orchestrator & Sub-Agents

A single agent with twenty tools becomes hard to reason about. The antidote is
**delegation**: a top-level *orchestrator* that routes a request to a focused
**specialist** (a sub-agent), then synthesises the answer. agentkit gives you three
ways to do this, all built on one primitive.

::: tip The primitive underneath
PydanticAI v2 removed `Agent.as_tool`. The supported pattern is a **tool** that
calls `specialist.run(...)` and forwards `deps`, `usage`, and `model`.
`agentkit.orchestrator` builds those tools for you, so token accounting and
dependency injection keep working across the hand-off.
:::

## The delegation pattern

`delegate(ctx, specialist, request)` runs a specialist inside a tool. It forwards
`usage` (so the specialist draws from the same budget) and `model`:

```python
# agentkit/orchestrator.py — the whole idea
async def delegate(ctx, specialist, request: str) -> str:
    result = await specialist.run(request, deps=ctx.deps, usage=ctx.usage, model=ctx.deps.model)
    return result.output
```

## The `Orchestrator` class

`Orchestrator` assembles an agent and registers specialists as delegation tools:

```python
from agentkit import Orchestrator

orchestrator = (
    Orchestrator(
        name="nudge",
        instructions="Route each request to the right specialist, then summarise.",
    )
    .add_specialist(reminder_agent, tool_name="handle_reminders", description="Set timed reminders.")
    .add_specialist(notes_agent,    tool_name="handle_notes",    description="Manage the owner's notes.")
    .add_specialist(writer_agent,   tool_name="handle_writing",  description="Draft and edit text.")
)

agent = orchestrator.agent        # the underlying pydantic_ai.Agent
```

- **`.add_specialist(agent, *, tool_name, description)`** — register a delegation tool (chainable).
- **`.tool(fn)`** — register a plain tool on the orchestrator.
- **`.agent`** — the built `pydantic_ai.Agent`.

## With the fluent builder

The builder exposes the same primitive as `.specialist(...)` and `.orchestrate(...)`:

```python
from agentkit import Agent

agent = (
    Agent.make("nudge")
    .instructions("Route each request to the right specialist, then summarise.")
    .specialist(reminder_agent, name="handle_reminders", description="Set timed reminders.")
    .orchestrate({                                   # several at once (mapping form)
        "handle_notes": (notes_agent, "Manage the owner's notes."),
        "handle_writing": (writer_agent, "Draft and edit text."),
    })
    .output(str)
    .build()
)
```

`.orchestrate(...)` also accepts an iterable of `(agent, tool_name, description)`.

## `make_delegate` and `delegate`

When you want a *custom* delegation tool — with its own guards, logging, or
argument shaping — build it from `delegate`:

```python
from agentkit import make_delegate, delegate

# the turnkey version: sets __name__/__doc__ so the tool schema is correct
agent.tool(make_delegate(reminder_agent, tool_name="handle_reminders", description="Set reminders."))
```

`make_delegate` exists because PydanticAI derives the tool name and description
from the function's `__name__` and `__doc__`, and the tool must be annotated with
`RunContext[Deps]`.

## Guarding a specialist

A specialist is itself a full agent loop, so bound it. Wrap `delegate` to add a
request limit and a graceful reply, and share the parent's usage budget with
`usage=ctx.usage`:

```python
from pydantic_ai import RunContext
from pydantic_ai.usage import UsageLimits
from agentkit.deps import Deps
from myapp.agents.reminder import reminder_agent   # your specialist

async def handle_reminders(ctx: RunContext[Deps], request: str) -> str:
    """Delegate a reminder request to the reminder specialist."""
    try:
        result = await reminder_agent.run(
            request,
            deps=ctx.deps,
            usage=ctx.usage,                        # share the token budget
            model=ctx.deps.model,
            usage_limits=UsageLimits(request_limit=6),
        )
        return result.output
    except Exception:
        return "I couldn't finish that request — try rephrasing it."

orchestrator.tool(handle_reminders)
```

This is the pattern used by the Nudge reference app
(`nudge/src/nudge/agents/orchestrator.py`).

## Sub-agents: spawning and teams

Delegation above is **model-chosen** (the top model decides when to call a
specialist). For explicit sub-tasks you run yourself, use `teams`:

### `spawn_tool`

Gives the model a `spawn(agent, task)` tool that runs a named sub-agent and
returns its output (forwarding `usage`/`model`):

```python
from agentkit import spawn_tool

agent = (
    Agent.make("lead")
    .instructions("Spin up specialists as needed.")
    .tool(spawn_tool({"researcher": researcher_agent}))
    .output(str)
    .build()
)
```

### `Supervisor`

Builds an agent whose job is to route to a named roster, then synthesise:

```python
from agentkit import Supervisor

lead = Supervisor(
    {"writer": writer_agent, "researcher": researcher_agent},
    name="lead",
    instructions="Delegate to the best specialist, then summarise.",
).build()
```

### `run_all_agents`

Deterministic fan-out from your own code:

```python
from agentkit.teams import run_all_agents

results = await run_all_agents({"a": agent_a, "b": agent_b}, "Summarise the incident.")
```

See [Multi-Agent Teams](/guide/teams) for the full teams surface.

## Choosing a pattern

| Pattern | Coordinator | Use for |
| --- | --- | --- |
| `.specialist()` / `Orchestrator.add_specialist()` | the main model | a handful of well-defined capabilities |
| `make_delegate` / `delegate` | your code | custom guards, logging, argument shaping |
| `Supervisor` | a dedicated router agent | many specialists with clear routing |
| `spawn_tool` | the model, explicitly | dynamic fan-out and parallel sub-tasks |
| `run_all_agents` | your code | batch comparisons |

## Testing delegation

Specialists are ordinary agents, and the tools are ordinary functions:

```python
def test_orchestrator_has_delegation_tools():
    agent = orchestrator.agent
    assert {"handle_reminders", "handle_notes"} <= set(agent._function_toolset.tools)
```

Because `make_delegate` forwards `deps`, you can run an orchestrator turn against a
`FunctionModel` and assert the specialist was invoked — see
[Testing](/guide/testing).

## Related

- [The Agent Builder](/guide/agents) — `.specialist()` and `.orchestrate()`.
- [Multi-Agent Teams](/guide/teams) — `Supervisor`, `spawn_tool`, `run_all_agents`.
- [Human-in-the-Loop](/guide/hitl) — approve or clarify before a tool runs.
