# The Full Stack

## Introduction

agentkit ships a complete single-user assistant stack. The primary (class-based)
way to enable it is `full = True` on an `AgentDefinition`; the fluent
`Agent.full()` call is the equivalent builder form. `FullStackProvider` wires the
application layers (config sections, schedules, channels) from settings — only for
the layers you have actually configured.

## The class form (primary)

Declare the stack on the agent class. Any `AgentDefinition` under `app/Agents/` is
discovered and built automatically — no `app.agent(...)` call is needed — and
`full = True` expands the whole stack, with each layer toggleable by its own field:

```python
from agentkit import AgentDefinition

from app.Tools.notes import add_note, current_time, list_notes


class Assistant(AgentDefinition):
    name = "assistant"
    posture = "hybrid"           # specialized | hybrid | free
    instructions = "You are a concise, helpful assistant."
    tools = [current_time, add_note, list_notes]
    full = True                  # persona + memory + skills + HITL + safety + todos
    persona = True               # read <AGENT_HOME>/SOUL.md
    memory = True                # typed memory tools + digest
    skills = True                # discover skills/*/SKILL.md
    learning = True              # reflect -> learn -> apply (review-gated)
    # knowledge = "./knowledge"  # or: knowledge = True (the app knowledge base)
    # approvals = True           # HITL approvals + ask_user
    # safety = True              # default tool policy
    # workspace = "./work"       # file tools
    # subagents = registry       # peer tools + handoff_to
    # code = True                # approval-gated run_code (off by default)
    output = str
```

`full = True` is what expands the stack; the per-layer fields toggle it. A field set
without `full` still attaches just that layer. Use `configure(self, agent)` for
anything not covered by a field — for example the native toolkits' allow-lists
(`agent.database({...})`, `agent.scheduler([...])`, `agent.queue({...})`).

| Field | Layer | Skipped when |
| --- | --- | --- |
| `persona=True` | `SOUL.md` persona | — |
| `memory=True` | typed memory tools + digest | `MEMORY_ENABLED=false` |
| `skills=True` | `SKILL.md` discovery | `SKILLS_ENABLED=false` |
| `knowledge=<path\|True>` | `search_knowledge` (RAG) | field unset |
| `approvals=True` | approvals + `ask_user` | `APPROVALS_ENABLED=false` |
| `safety=True` | `default_policy()` | — |
| `workspace=<dir>` | file tools | field unset |
| `subagents=<registry\|mapping>` | peer tools + `handoff_to` | field unset |
| `learning=True` | self-learning ([Self-Learning](/guide/self-learning)) | `LEARNING_ENABLED=false` |
| `todos=True` | in-loop todo tools ([Tasks & Todos](/guide/tasks)) | — |
| `code=True` | approval-gated `run_code` ([Code Execution](/guide/code-execution)) | off by default |
| `guardrails=True` | injection-scanning hooks ([Safety](/guide/safety)) | — |
| `working_memory=True` | thread-scoped working memory | — |
| `agent_middleware=[...]` | middleware hooks | — |

Native toolkits ([Native Tools](/guide/native-tools)) are enabled by `full = True`
according to the posture and `*_TOOLS_ENABLED` settings; their allow-lists
(`models`/`tasks`/`jobs`) are set in `configure` or with the fluent form below.

Applying the same agent twice is safe: each layer is applied once and tools are
never double-registered.

## The fluent form

The same stack is one call on the builder:

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

`full(...)` is the toggleable, idempotent expansion (the same layers as the class
fields above, plus the native allow-lists `models`/`tasks`/`jobs`):

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
| `todos=True` | in-loop todo tools ([Tasks & Todos](/guide/tasks)) | — |
| `code=False` | approval-gated `run_code` ([Code Execution](/guide/code-execution)) | off by default |

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
`bootstrap.py` registers `FullStackProvider` (and `DriverServiceProvider`, which
reports/overrides drivers), `app/Agents/assistant.py` is an `AgentDefinition` with
`full = True`, `app/Channels/` shows a channel factory, and `config/memory.py` +
`config/channels.py` layer the sections.

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
