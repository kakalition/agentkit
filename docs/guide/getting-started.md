# Getting Started

## Introduction

This page walks you from an empty directory to a running agent you can chat with,
inspect, and extend. It should take about five minutes.

::: tip The fastest way: scaffold a project
```bash
agentkit new my-agent && cd my-agent
cp .env.example .env      # set OPENAI_API_KEY
uv sync
agentkit tinker
```
`agentkit new` writes a bare, sane skeleton you own and edit — see
[Installation](/guide/installation) for what you get and what to customise.
:::

## Install

agentkit is a Python package. Install it with your tool of choice:

::: code-group

```bash [uv]
uv add agentkit
```

```bash [pip]
pip install agentkit
```

```bash [poetry]
poetry add agentkit
```

:::

Some capabilities live behind extras so the core stays small:

| Extra | Adds |
| --- | --- |
| `agentkit[memory]` | CPU embeddings (`sentence-transformers` / `fastembed`) for memory & RAG |
| `agentkit[observability]` | Phoenix / OpenTelemetry span export |
| `agentkit[a2a]` | the A2A server/client (`a2a-sdk`) |
| `agentkit[mcp]` | the MCP client/server (`fastmcp`) |

## Configure

agentkit reads configuration from the environment and an optional `.env` at your
project root. The only thing you *must* provide is a model provider key:

```bash
# .env
OPENAI_API_KEY=sk-...
AGENT_NAME=nudge
OWNER_ID=me
```

See the full [Configuration reference](/reference/configuration) for everything
else. Sensible defaults mean you can start with just the key.

## Your first agent

Create `bootstrap.py`. This is the conventional entry point — `agentkit serve`
boots `bootstrap:app` by default.

```python
# bootstrap.py
from agentkit import AgentDefinition, App, AgentSettings

def add_note(ctx, text: str) -> str:
    """Save a note for later."""
    ctx.deps.extras.setdefault("notes", []).append(text)
    return f"saved: {text}"

class Nudge(AgentDefinition):
    name = "nudge"
    instructions = "You keep short notes and remind the owner about them."
    tools = [add_note]
    memory = True            # remember/recall/forget tools, backed by the DB
    output = str

agent = Nudge.build()

app = App(name="nudge", settings=AgentSettings(owner_id="me"))
app.agent(agent)
```

Fluent equivalent: `Agent.make("nudge").instructions(…).tool(add_note).memory().output(str).build()`.

That is a complete, runnable agent. Run a single turn:

```bash
python -c "import asyncio, bootstrap; print(asyncio.run(bootstrap.app.run('note: buy milk')).output)"
```

## Chat interactively

Boot the app and drop into a REPL with history, tools, and memory all wired up:

```bash
agentkit tinker
```

```
agentkit tinker — type 'exit' to quit.
agentkit> remember that I'm allergic to peanuts
agentkit> what am I allergic to?
```

## Run everything

The same app can serve its channels — the operator web UI, the scheduler, and any
provider-registered channels — in one process:

```bash
agentkit serve
```

Open the web UI (default `http://127.0.0.1:8787`) to browse conversations, inspect
usage, manage schedules, and edit your persona.

## Inspect what you built

```bash
agentkit inspect
```

```
app: nudge
agent: nudge
tools: add_note, remember, recall, forget_memory
channels: webui
commands: (none)
config: (none)
```

## Scaffold with generators

Rather than hand-write boilerplate, generate it:

```bash
agentkit make:provider notes   # providers/notes.py
agentkit make:tool  summarize  # tools/summarize.py
agentkit make:channel slack    # channels/slack.py
```

Generators never overwrite existing files unless you pass `--force`.

## Project layout

A typical agentkit project looks like this:

```
my-agent/
├── bootstrap.py            # App(...) — the boot target
├── .env
├── providers/              # service providers
├── tools/                  # tool functions
├── channels/               # channel factories
├── commands/               # provider commands
├── models/                 # SQLModel tables
├── skills/                 # SKILL.md folders
├── prompts/                # versioned prompt files
└── config/                 # per-concern config files
```

Only `bootstrap.py` is required; the rest are conventions that agentkit's
generators and discovery understand.

## Where to go next

- [The Application](/guide/application) — the container and its lifecycle.
- [Service Providers](/guide/providers) — how to organise a growing app.
- [The Agent Builder](/guide/agents) — everything you can compose onto an agent.
- [Tools](/guide/tools) — arguments, approval, caching, toolsets.
- [Skills](/guide/skills) and [Knowledge](/guide/knowledge) — give your agent
  expertise and documents.
