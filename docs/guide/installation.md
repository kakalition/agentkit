# Installation

agentkit ships a bare, sane starting skeleton — the equivalent of `laravel new`.
You create a project, open it up, and customise it. Nothing is hidden behind a
generator you can't read: every file the framework writes is plain Python you own.

## Meet the requirements

- **Python 3.11+**
- A model provider key (OpenAI by default; any PydanticAI provider works)
- That's it — persistence, scheduling, and the web UI run in-process

## Install the CLI

Install agentkit once, globally, to get the `agentkit` command:

::: code-group

```bash [uv]
uv tool install agentkit
```

```bash [pipx]
pipx install agentkit
```

```bash [pip]
pip install --user agentkit
```

:::

Verify it:

```bash
agentkit about
```

## Create a project

```bash
agentkit new my-agent
cd my-agent
```

You get a full, runnable, **explorable** project in one command:

```
my-agent/
├── bootstrap.py                # App(...) — the boot target
├── SOUL.md                     # the persona
├── pyproject.toml
├── .env.example
├── conftest.py
├── app/
│   ├── config.py               # Settings + a layered config Section
│   ├── Agents/assistant.py     # the agent builder (persona, tools, policy)
│   ├── Console/Kernel.py       # schedule() + commands()
│   ├── Console/Commands/       # CLI commands
│   ├── Events/                 # event payloads
│   ├── Listeners/              # event listeners
│   ├── Jobs/                   # queued / durable jobs
│   ├── Middleware/             # turn middleware
│   ├── Models/                 # models (tables)
│   ├── Notifications/          # notifications
│   ├── Policies/               # tool policies
│   ├── Providers/              # AppServiceProvider (mandatory), EventServiceProvider
│   ├── Repositories/           # Repository classes + AppRepositories
│   ├── Rules/                  # validation rules
│   ├── Services/               # domain services
│   └── Tools/                  # tool functions
├── config/app.py               # config/<section>.py overrides
├── database/README.md          # schema/migration notes
├── skills/hello/SKILL.md       # a discoverable skill
├── prompts/system.md           # a versioned prompt
├── evals/smoke.yaml            # an evaluation suite
├── storage/                    # local artifacts (Storage facade)
└── tests/
```

The tree mirrors Laravel: `app/Providers/AppServiceProvider.py` is where everything
is wired, `app/Console/Kernel.py` holds the schedule and commands, and each layer has
a working example you can read, extend, or delete.

Useful flags:

| Flag | Effect |
| --- | --- |
| `--path DIR` | create the project under `DIR` instead of the current directory |
| `--no-git` | skip initialising a git repository |
| `--force` | write into a directory that already has files |

## Configure

```bash
cp .env.example .env
# then edit .env and set OPENAI_API_KEY
```

Then install dependencies:

```bash
uv sync            # or: pip install -e .
```

## Start it

Chat with your new agent in a REPL:

```bash
agentkit tinker
```

```
agentkit tinker — type 'exit' to quit.
agentkit> what time is it?
agentkit> remember that my timezone is Europe/Lisbon
```

Or run everything — the web UI, the scheduler, and any channels — in one process:

```bash
agentkit serve            # http://127.0.0.1:8787
```

## Test and evaluate

```bash
pytest
agentkit eval evals/smoke.yaml --bootstrap bootstrap:app
```

## What you can customise

The skeleton is deliberately small, and every seam is meant to be edited:

| Want to change… | Edit |
| --- | --- |
| The persona / voice | `SOUL.md` |
| The agent's instructions | `my_agent/providers.py` (`INSTRUCTIONS`) |
| The agent's tools | `my_agent/tools.py`, then register in `providers.py` |
| What the agent *knows* | add `skills/<name>/SKILL.md`, or `.knowledge(path=…)` |
| Reusable prompt text | `prompts/<name>.md` + `.prompt(...)` |
| App settings & config | `my_agent/config.py`, override in `config/app.py` or the environment |
| Events, schedules, channels | `AppProvider.boot`, `app.schedules`, `app.channel` |
| The model or routing | `MODEL_NAME`, or `app.model_resolver(...)` |
| Safety & budgets | `app.middleware(...)`, `app.budget(...)` |

## Adding to an existing project

Already have a project? Add agentkit as a dependency and drop in a `bootstrap.py`
exposing `app`:

```bash
uv add agentkit
agentkit make:provider my_app     # scaffold pieces instead of a whole project
```

`agentkit serve` boots `bootstrap:app` by default; override with
`AGENTKIT_BOOTSTRAP=myapp.bootstrap:app`.

## Next steps

- [Getting Started](/guide/getting-started) — the 60-second tour.
- [The Application](/guide/application) — the container and its lifecycle.
- [Service Providers](/guide/providers) — how to organise a growing app.
