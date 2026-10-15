# The Full Stack

## Introduction

agentkit ships a complete single-user assistant stack. `Agent.full()` turns a
builder into the whole thing in one call, and `FullStackProvider` wires the
application layers (config sections, schedules, channels) from settings — only
for the layers you have actually configured.

## `Agent.full()`

```python
from agentkit import Agent

agent = (
    Agent.make("assistant")
    .instructions("You are a concise, helpful assistant.")
    .tool(current_time)
    .full()                     # persona + memory + skills + HITL + safety
    .output(str)
    .build()
)
```

`full(...)` is a toggleable, idempotent expansion:

| Argument | Layer | Skipped when |
| --- | --- | --- |
| `persona=True` | `SOUL.md` persona | — |
| `memory=True` | typed memory tools + digest | `MEMORY_ENABLED=false` |
| `skills=True` | `SKILL.md` discovery | `SKILLS_ENABLED=false` |
| `knowledge=<path>` | `search_knowledge` (RAG) | argument omitted |
| `hitl=True` | approvals + `ask_user` | `APPROVALS_ENABLED=false` |
| `safety=True` | `default_policy()` | — |
| `workspace=<dir>` | file tools | argument omitted |
| `subagents=<registry\|mapping>` | peer tools + `handoff_to` | argument omitted |
| `native=True` | native toolkits ([Native Tools](/guide/native-tools)) | each `*_TOOLS_ENABLED` flag |
| `models`/`tasks`/`jobs` | native allow-lists | argument omitted |
| `learning=True` | self-learning ([Self-Learning](/guide/self-learning)) | `LEARNING_ENABLED=false` |

Calling `full()` twice is safe: each layer is applied once and tools are never
double-registered.

## `FullStackProvider`

```python
from agentkit import App, FullStackProvider

app = App(name="assistant").fullstack()   # or .providers([FullStackProvider])
app.boot()
```

- **`register`** declares the config sections `memory`, `learning`, `channels`,
  `interop` and `queue` (`defaults < config/<name>.py < env`).
- **`boot`** performs effects **only for configured layers** and logs + skips
  anything unconfigured:
  - registers and schedules the daily durable task `memory:consolidate`;
  - registers and schedules the daily durable task `learning:reflect`
    (see [Self-Learning](/guide/self-learning));
  - registers a `Gateway` channel (Telegram/Slack/Email/Discord) for each channel
    whose token/env is present;
  - registers notifier senders for those channels;
  - configures A2A peers when `PEERS_FILE` is set.

Nothing raises when the stack is empty.

## Scaffold

`agentkit new <name>` writes the **full-stack** project by default:
`bootstrap.py` registers `FullStackProvider`, `app/Agents/assistant.py` builds
with `.full()`, `app/Channels/` shows a channel factory, and `config/memory.py`
+ `config/channels.py` layer the sections.

```bash
agentkit new my-agent          # full stack (default)
agentkit new my-agent --minimal
```

Programmatically: `scaffold_project("my-agent", ".", full=True)`.

## Seeing what is on

```bash
agentkit inspect        # providers, tools, channels, and the enabled stack
```

`GET /api/info` returns the same `stack` view (providers, memory, skills,
approvals, sub-agents, channels, interop, queue), so the web UI can show which
layers are active.
