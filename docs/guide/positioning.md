# Positioning

agentkit is one runtime that runs **both camps** of agent framework:

- **Freeform general-purpose frameworks** — Strands, LangChain DeepAgents, Mastra.
- **Lean, hackable harnesses** — nanobot, Hermes-style.

The claim is not "a bit of each". It is that a single runtime, with no forked code
path, spans *closed specialist → hybrid → autonomous generalist* on the agent side,
and *class → fluent → raw PydanticAI* on the authoring side. This page is the one
home for that claim.

## The two camps, one runtime

| Capability | agentkit | Strands | DeepAgents | Mastra | nanobot / Hermes |
| --- | --- | --- | --- | --- | --- |
| Runtimes supported | PydanticAI (fixed) | Bedrock/OpenAI/… | LangGraph | **bring-your-own** | varies |
| Rigid vs freeform on one runtime | [posture](/guide/posture) (`specialized`/`hybrid`/`free`) | config | prompt-driven | config | n/a (free by default) |
| Authoring: class **and** closure | [class + fluent + raw](/guide/duality) | class/closure | class | class | closure-first |
| Sub-agents / delegation | yes (`specialists`, teams) | yes | yes (subagents) | yes | minimal |
| Context strategies | yes (compaction, processors) | yes | yes (summaries) | yes | manual |
| Planning / todos | yes (`planning`, `todos`) | yes | yes (todo) | limited | manual |
| Skills | yes (`SKILL.md`) | yes | limited | limited | minimal |
| Workspace file tools | yes (`edit_file`/`glob`/`grep`) | partial | yes (filesystem) | yes | shell-native |
| Mid-run steer | yes (`App.steer`) | yes (steerability) | limited | yes | n/a |
| Durable execution | DBOS / Temporal | no | LangGraph checkpoints | limited | no |
| Channels (Telegram, Slack, …) | built-in | no | no | partial | n/a |
| Multi-provider | [wide](/guide/multi-provider) | yes | via LangChain | via AI SDK | provider-agnostic |
| Dependency weight | batteries-included | mid | mid | mid | **tiny** |

The row that matters most is the first: agentkit is **not** a bring-your-own-runtime
framework. Its supported runtime is **PydanticAI**, over **SQLite/DBOS** (or Temporal)
for durability. If you need to swap the execution engine itself — Mastra's model — that
is the one real divergence, and it is a deliberate choice: a fixed runtime is what lets
posture, duality, durability, and channels share a single implementation.

## Same runtime, three postures

Rigid and freeform are **defaults**, not different frameworks. A [posture](/guide/posture)
sets the default layer set for `.full()`; an explicit argument or settings flag always
wins, and no code path forks. See [Postures](/guide/posture) for the full matrix.

```python
from agentkit import AgentDefinition

class Support(AgentDefinition):
    posture = "specialized"      # closed specialist
    full = True

class Scout(AgentDefinition):
    posture = "free"             # autonomous generalist
    full = True
```

## Same runtime, three ways to author

The [class/functional duality](/guide/duality) means you never pick a lane to stay in:

```python
from agentkit import Agent, AgentDefinition

# 1. class — reusable, discovered, declarative
class Assistant(AgentDefinition):
    name = "assistant"
    instructions = "Be concise."
    tools = [current_time]
    full = True

# 2. fluent — one-off, code-built
agent = Agent.make("assistant").instructions("Be concise.").full()

# 3. raw PydanticAI escape hatch — anything not covered
def configure(self, agent):
    return agent.web_search().caching()
```

All three produce the same `pydantic_ai.Agent`.

## The lean path

The freeform/hackable camp is the same runtime with nothing bolted on. `build()` an
`AgentDefinition` and skip the application shell entirely — no `App`, no DBOS, no
channels:

```python
from agentkit import AgentDefinition

class Assistant(AgentDefinition):
    instructions = "You are a concise, helpful assistant."

agent = Assistant.build()        # → pydantic_ai.Agent
result = agent.run_sync("hello")
```

Add the [full stack](/guide/fullstack) only when you want persistence, memory,
skills, channels, durability, or the CLI/API surfaces. Everything above the lean
path is opt-in.

## Related

- [Postures](/guide/posture) — `specialized` / `hybrid` / `free`, defaults-only.
- [Class & Functional Duality](/guide/duality) — one normalization layer, every seam.
- [Multiple Model Providers](/guide/multi-provider) — `provider:model` and the extras.
- [Philosophy](/guide/philosophy) — batteries-included, not dependency-light.
