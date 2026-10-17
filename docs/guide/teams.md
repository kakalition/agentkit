# Multi-Agent Teams

## Introduction

Complex work is easier to reason about when split across specialists. agentkit
gives you two ways to coordinate them: a **Supervisor** that routes requests, and
explicit **sub-agent spawning**.

::: tip Start with the delegation primitive
Most multi-agent needs are met by delegation — see
[Orchestrator & Sub-Agents](/guide/orchestrator) for `Orchestrator`,
`.specialist()`, `make_delegate`, and `spawn_tool`. This page covers the
`Supervisor` and batch helpers built on top.
:::

## Specialists (delegation)

The simplest multi-agent pattern is delegation: expose one agent as a tool of
another. Usage and model are forwarded, so accounting stays correct.

```python
from agentkit import AgentDefinition

class Nudge(AgentDefinition):
    name = "nudge"
    instructions = "Route requests to the right specialist."
    specialists = {
        "handle_reminders": (reminder_agent, "Set reminders."),
        "handle_notes": (notes_agent, "Manage notes."),
    }
    output = str

orchestrator = Nudge.build()
```

Fluent equivalent:

```python
orchestrator = (
    Agent.make("nudge")
    .instructions("Route requests to the right specialist.")
    .specialist(reminder_agent, name="handle_reminders", description="Set reminders.")
    .specialist(notes_agent,   name="handle_notes",   description="Manage notes.")
    .output(str)
    .build()
)
```

See [The Agent Builder](/guide/agents#specialists) for
`specialists` / `.specialist()` and `.orchestrate()`.

## The `Supervisor`

A `Supervisor` builds an agent whose job is to route to a named roster, then
synthesise a final answer from the specialists' output.

```python
from agentkit import Supervisor

supervisor = Supervisor(
    {"writer": writer_agent, "researcher": researcher_agent},
    name="lead",
    instructions="Delegate to the best specialist, then summarise.",
)
lead = supervisor.build()
```

Each roster member becomes a delegation tool named after its key (non-alphanumeric
characters become underscores).

## Spawning sub-agents

For explicit, awaitable sub-tasks — rather than model-chosen delegation — use
`spawn_tool`. The model gets a `spawn(agent, task)` tool that runs a named
sub-agent and returns its output.

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

`team_tools(agents)` is a convenience returning `[spawn_tool(agents)]`.

## Running a roster directly

For batch work outside the model loop, `run_all_agents` runs every agent on the
same task and collects the outputs:

```python
from agentkit.teams import run_all_agents

results = await run_all_agents(
    {"a": agent_a, "b": agent_b}, "Summarise the incident.", deps=deps, model=model
)
# {"a": "...", "b": "..."}
```

## Choosing a pattern

| Pattern | Coordinator | Use for |
| --- | --- | --- |
| `.specialist()` / `.orchestrate()` | the main model | a handful of well-defined capabilities |
| `Supervisor` | a dedicated router agent | many specialists, clear routing |
| `spawn_tool` | the model, explicitly | dynamic fan-out, parallel tasks |
| `run_all_agents` | your code | deterministic batch comparisons |

::: tip Keep delegation shallow
Two levels of delegation (orchestrator → specialist) is usually plenty. Deep
nesting multiplies latency and token cost without improving quality.
:::

Continue to [Model Routing & Cost →](/guide/routing)

## Subagent context in a team

### What this is

Every team member you delegate to is a **subagent** — a helper agent — and every
way of delegating eventually asks the same question: **what can that helper
see?**

The helper's **context** is the parent's dependencies (`deps`: the shared objects
such as the database and settings), its conversation so far, and its model. In
this page, spawning is the delegated `task(subagent, prompt)` tool: `spawn_tool`
and `Supervisor` expose each roster member as a tool, `run_all_agents` runs them
directly from your code, and all of them run the child through the **context
driver** (built on `agentkit.agents.subagent.subagent_tool`).

Think of emailing a team. You can cc everyone on the entire thread (**shared**),
send each person only the paragraph relevant to their job (**isolated**, the
default), or forward a short recap (**summarized**).

### End-to-end example

```python
from agentkit import AgentDefinition, App, DriverKind, spawn_tool, team_tools
from agentkit.agents.registry import AgentRegistry
from agentkit.agents.subagent import SharedContext, subagent_tool

app = App(name="lead")
roster = {"writer": writer_agent, "researcher": researcher_agent}

# Default: CONTEXT_DRIVER unset -> "isolated"; spawn_tool gives the model a
# spawn(agent, task) tool and each child sees only the task string.
class Lead(AgentDefinition):
    name = "lead"
    tools = [spawn_tool(roster)]

lead = Lead.build()
tools = team_tools(roster)          # convenience: [spawn_tool(roster)]

# The same thing at a lower level: a registry plus an explicit strategy.
registry = AgentRegistry()
for name, agent in roster.items():
    registry.register_local(agent, name=name)
strategy = app.manager(DriverKind.CONTEXT).driver()   # isolated by default
task_tool = subagent_tool(registry, strategy=strategy)

# A Supervisor and run_all_agents delegate through the same driver:
#   Supervisor(roster, name="lead").build()
#   await run_all_agents(roster, "Summarise the incident.")

# Switch driver: CONTEXT_DRIVER=shared in .env, or override it just for this app:
app.extend(DriverKind.CONTEXT, "shared", lambda app: SharedContext())
```

### Drivers

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `isolated` | Each helper starts blank: it inherits none of the parent's dependencies, conversation, or history, so the task string must be self-contained. | Default. Use it for clean, independent sub-tasks and when one helper must not see another team's data. |
| `shared` | Each helper reuses the parent's context: the same dependencies and the same conversation as the parent run. | Use it when helpers need the ongoing conversation or the parent's resources, and sharing that data is fine. |
| `summarized` | Like `isolated`, but the tool wraps the prompt as a summary of prior context. | Use it when a helper needs the gist of the parent's context without receiving it verbatim. |

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
| A helper misses context the parent had | context is `isolated` (the default); pass the detail in the task or switch to `shared`. |
| One helper sees another team's conversation | context is `shared`; switch to `isolated` or `summarized`. |
| `unknown agent` in the `spawn` tool | the name is not in the roster you passed to `spawn_tool`/`team_tools`. |
| `unknown context driver` | the `CONTEXT_DRIVER` value is misspelled or not registered; fix the name or `app.extend(...)` it. |
| Changing `CONTEXT_DRIVER` had no effect | the strategy is resolved once per app; call `app.manager(DriverKind.CONTEXT).forget()` or rebuild the app. |
