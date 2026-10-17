# Working Memory

Memory (`agentkit.memory`) stores durable facts about the owner. **Working
memory** is different: it is *thread-scoped scratch state* the agent keeps for
the current conversation — intermediate notes, plans, fetched values.

## Enabling it

```python
from agentkit import AgentDefinition

class Planner(AgentDefinition):
    name = "planner"
    instructions = "Think step by step."
    working_memory = True

agent = Planner.build()
```

Fluent equivalent:

```python
agent = Agent.make("planner").instructions("Think step by step.").working_memory().build()
```

This adds four tools:

| Tool | Purpose |
| --- | --- |
| `memory_set(key, value)` | store a value for this conversation |
| `memory_get(key)` | read a value back |
| `memory_list()` | list everything stored |
| `memory_forget(key)` | delete a key |

Values are namespaced by conversation id, so two conversations never share state.
It is scratch space, not a place for durable facts (use the `memory` field for that).

## Drivers

`working_memory_driver` selects the store:

- `memory` (default) — in-process; ideal for a single process.
- `repository` — persisted to the `working_memory` table, so it survives restarts
  and is visible to the web UI.

The setting `working_memory_enabled` turns it on for every agent built under that
configuration, without setting `working_memory` on each definition.
