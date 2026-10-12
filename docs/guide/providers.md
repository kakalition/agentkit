# Service Providers

Service providers are the organising unit of a growing agentkit application. They
bind concerns onto the app in one place and keep your `bootstrap.py` tiny.

```python
from agentkit import Provider

class NudgeProvider(Provider):
    def register(self, app):
        ...   # bindings; no side effects

    def boot(self, app):
        ...   # side effects
```

## The two phases

### `register(app)` — bind

`register` is for *declarations*: bind services into the container, register config
sections, commands, and schedules, and set the primary agent. It must be free of
side effects so the app can be booted safely in tests.

```python
class NotesProvider(Provider):
    def register(self, app):
        from notes.config import Settings

        app.config("notes", TextSection)
        app.agent(build_notes_agent())
        app.commands([ExportNotes()])
```

### `boot(app)` — act

`boot` is for *effects*: subscribe to events, import a module that registers a
durable task, or warm a cache. By the time it runs, every provider has registered.

```python
class NotesProvider(Provider):
    def boot(self, app):
        from notes.services import notes as svc  # registers @scheduler.task("notes")

        def audit(event):
            with app.repositories() as repos:
                repos.audit.append("turn.end", target=event.conversation_id)

        app.on("turn.end", audit)
```

## Contributing commands and schedules

Rather than call `app.commands` yourself, a provider can declare them:

```python
class NotesProvider(Provider):
    def commands(self):
        return [ExportNotes(), ImportNotes()]

    def schedules(self):
        return [{"name": "notes-digest", "cron": "0 9 * * *", "task": "digest"}]
```

`App.boot()` collects these automatically.

## Providing binds into the container

```python
class NotesProvider(Provider):
    def register(self, app):
        app.bind("notes.exports", lambda c: ExportService(c.make("app")))
        app.bind("notes.index", build_index, singleton=True)
```

Anything bound is resolvable from facades and dependencies:

```python
exporter = app.make("notes.exports")
```

## Discovery via entry points

You never have to register a provider explicitly if it is published. Add it to the
`agentkit.providers` entry-point group and any app with discovery enabled (the
default) will pick it up:

```toml
[project.entry-points."agentkit.providers"]
notes = "notes.providers:NotesProvider"
```

A provider that fails to import is logged and skipped, so one bad package never
stops the app from booting.

## A complete provider

```python
from agentkit import Agent, Provider

ORCHESTRATOR = "You keep notes and answer questions about them."

class NotesProvider(Provider):
    def register(self, app):
        from notes.config import Settings

        app.agent(
            Agent.make("notes")
            .persona()
            .instructions(ORCHESTRATOR)
            .memory()
            .knowledge(path="./docs")
            .output(str)
        )
        app.config("notes", Settings)

    def boot(self, app):
        from notes.services import notes as svc  # noqa: F401 — registers the task
        app.on("turn.end", lambda event: None)

    def commands(self):
        return []
```

::: tip Small providers compose
Prefer several focused providers (`PersonaProvider`, `TelegramProvider`,
`SchedulerProvider`) over one giant class. Discovery makes adding them free.
:::

Continue to [The Agent Builder →](/guide/agents)
