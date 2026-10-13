# Artisan-style CLI

`agentkit` is the console entry point. It runs your app, scaffolds code, inspects
what you built, and manages the workspace — in the spirit of `artisan`.

```bash
agentkit --help
```

## Create a project

```bash
agentkit new my-agent          # write the default skeleton into ./my-agent
agentkit new my-agent --path ~/code --no-git
```

See [Installation](/guide/installation) for the skeleton layout and what to
customise.

## Runtime commands

```bash
agentkit serve            # boot bootstrap:app and run channels + web UI
agentkit up               # alias for serve
agentkit tinker           # an interactive REPL against the booted app
agentkit inspect          # agents, tools, channels, commands, config
agentkit schedule:list    # durable jobs
agentkit schedule:run     # run due jobs now (catch-up)
agentkit queue:work       # process queued jobs (requires QUEUE_ENABLED=true)
agentkit queue:failed     # list failed jobs
agentkit queue:retry ID   # requeue a failed job
agentkit queue:flush      # delete failed jobs
agentkit about            # version, agent home, model
```

### `serve`

```bash
agentkit serve --bootstrap nudge.bootstrap:app --no-scheduler --no-webui
```

Boots the app, optionally starts the scheduler worker and the web UI, and blocks
until shutdown. If no app can be found it exits with a clear message:

```
could not load app (No module named 'bootstrap'); set AGENTKIT_BOOTSTRAP or create a 'bootstrap.py' exposing `app`.
```

### `tinker`

```bash
agentkit tinker --conversation-id cli:play
```

A read-eval-print loop: type a message, get the agent's reply, with history,
memory, tools, and events all live.

### `inspect`

```bash
agentkit inspect --json
```

Machine-readable app introspection — handy in CI.

## Generators

```bash
agentkit make:agent notes
agentkit make:provider notes
agentkit make:tool   summarize
agentkit make:channel slack
agentkit make:command sync
agentkit make:model   note
```

Each writes a file under a conventional directory and **refuses to overwrite**
unless you pass `--force`:

```bash
agentkit make:tool summarize --path ./src --force
```

Emitted modules are import-clean and use the current agentkit API.

## Knowledge

```bash
agentkit knowledge add ./docs
agentkit knowledge add-text "Refunds take 5 days" --source policy
agentkit knowledge search "refund policy"
agentkit knowledge list
```

## Skills

```bash
agentkit skills list
agentkit skills show pdf-tools
```

## Evaluations

```bash
agentkit eval evals/smoke.yaml --bootstrap bootstrap:app
```

Runs a suite against the booted app and exits non-zero on failure — ideal in CI.

## Workspace

```bash
agentkit workspace list
agentkit workspace migrate nudge           # move legacy ~/.local/share data
```

## Commands contributed by providers

A provider can contribute commands; they are collected at boot and can be
installed onto a Typer app:

```python
from agentkit import Command

class SyncCommand(Command):
    name = "sync"
    help = "Sync the knowledge base."
    def run(self, app) -> None:
        ...

app.commands([SyncCommand()])
app.install_commands(typer_app)   # register them
```

Continue to [Evaluations →](/guide/evaluations)
