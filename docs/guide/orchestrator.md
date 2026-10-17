# Orchestrator & Sub-Agents

## Introduction

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

## With the class form

Declare an `AgentDefinition` and register the specialists. A single specialist is
a `specialists` mapping entry; several at once use `configure` with
`.orchestrate(...)` (which has no class field):

```python
from agentkit import AgentDefinition

class Nudge(AgentDefinition):
    name = "nudge"
    instructions = "Route each request to the right specialist, then summarise."
    specialists = {"handle_reminders": (reminder_agent, "Set timed reminders.")}
    output = str

    def configure(self, agent):
        return agent.orchestrate({                 # several at once (mapping form)
            "handle_notes": (notes_agent, "Manage the owner's notes."),
            "handle_writing": (writer_agent, "Draft and edit text."),
        })

agent = Nudge.build()
```

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
from agentkit import AgentDefinition, spawn_tool

class Lead(AgentDefinition):
    name = "lead"
    instructions = "Spin up specialists as needed."
    tools = [spawn_tool({"researcher": researcher_agent})]
    output = str

agent = Lead.build()
```

Fluent equivalent:

```python
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

## Subagent context: what a helper agent can see

### What this is

A **subagent** is a helper agent you delegate work to. When the parent hands a
task to that helper, one question has to be answered first: **how much of the
parent's world does the helper get to see?** That world is called the **context**
— the parent's dependencies (its `deps`: the shared objects such as the database,
settings, and repositories), its conversation so far, and its model. A helper
that sees everything is convenient but leaks information and blurs
responsibility; a helper that sees nothing is safe but must be briefed fully.

Think of hiring a translator for a meeting. You can sit them in on every call and
hand them the whole transcript (**shared**); give them a one-paragraph brief
written just for this job and keep them out of the room (**isolated**, the
default); or hand them a short recap of what matters and let them work out of
earshot (**summarized**).

Which of the three happens is a **driver** — a swappable implementation chosen by
a setting, not hard-coded. The `task(subagent, prompt)` tool that performs the
delegation is built with `agentkit.agents.subagent.subagent_tool`.

### End-to-end example

```python
from agentkit import AgentDefinition, App, DriverKind
from agentkit.agents.registry import AgentRegistry
from agentkit.agents.subagent import SharedContext, subagent_tool

app = App(name="lead")
registry = AgentRegistry()
registry.register_local(researcher_agent, name="researcher")   # your own helper

# Default: no CONTEXT_DRIVER set -> "isolated"; the helper inherits nothing.
strategy = app.manager(DriverKind.CONTEXT).driver()

class Lead(AgentDefinition):
    name = "lead"
    tools = [subagent_tool(registry, strategy=strategy)]

lead = Lead.build()

# Switch driver three ways:
app.manager(DriverKind.CONTEXT).driver("shared")                       # explicit name
app.extend(DriverKind.CONTEXT, "shared", lambda app: SharedContext())  # per app
# CONTEXT_DRIVER=shared                                                # env / .env
```

### Drivers

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `isolated` | The helper starts blank: it inherits none of the parent's dependencies, conversation, or history. Everything it needs must be in the prompt you pass. | Default. Use it for self-contained jobs, for repeatable inputs, or when the parent's conversation must not leak. |
| `shared` | The helper reuses the parent's context: the same dependencies and the same conversation, so it remembers the task in progress. | Use it when the helper genuinely needs the ongoing conversation or the parent's resources, and sharing that data is acceptable. |
| `summarized` | Like `isolated`, but the tool frames the prompt as a summary of prior context, so the helper is told "this is the gist". | Use it when the helper needs the gist rather than the full transcript — a middle ground that keeps the child's input short. |

### Selecting a driver

- **Setting** — one line in the environment or `.env`: `CONTEXT_DRIVER=shared`.
- **Precedence** — an explicit name passed in code wins, then the setting, then
  the default (`isolated`).
- **Per app** — `app.extend(DriverKind.CONTEXT, "brief", lambda app: MyContextStrategy())`.
- **Reusable** — ship one for everyone with `@register_driver`:

```python
from agentkit import DriverKind, register_driver

@register_driver(DriverKind.CONTEXT, "brief")
def _brief_context(app):
    return MyContextStrategy()      # any object with .context(ctx, task)
```

Then select it with `CONTEXT_DRIVER=brief`. See
[Contracts & Drivers](/guide/drivers) for the full picture.

### Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| The helper does not know something the parent knew | context is `isolated` (the default); either put the detail in the prompt or switch to `shared`. |
| The helper leaks details from another task | context is `shared`; switch to `isolated` or `summarized`. |
| `unknown context driver` | the `CONTEXT_DRIVER` value is misspelled or not registered; fix the name or `app.extend(...)` it. |
| Changing `CONTEXT_DRIVER` had no effect | the strategy is resolved once per app; call `app.manager(DriverKind.CONTEXT).forget()` or rebuild the app. |
| There is no `task` tool | it only exists once you add it: `agent.tool(subagent_tool(registry, ...))`. |
