# Multi-Agent Teams

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
orchestrator = (
    Agent.make("nudge")
    .instructions("Route requests to the right specialist.")
    .specialist(reminder_agent, name="handle_reminders", description="Set reminders.")
    .specialist(notes_agent,   name="handle_notes",   description="Manage notes.")
    .output(str)
    .build()
)
```

See [The Agent Builder](/guide/agents#specialist-agent-name-description) for
`.specialist()` and `.orchestrate()`.

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
from agentkit import spawn_tool

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
