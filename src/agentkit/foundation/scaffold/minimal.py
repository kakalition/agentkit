"""The minimal project skeleton (``agentkit new --minimal``).

The generated project ships the whole tree — providers, console kernel, models,
repositories, services, tools, agents, events, listeners, jobs, notifications,
policies, rules, middleware — wired and runnable, so you can read what is under the
hood and delete what you don't need.
"""

from __future__ import annotations

import re

__all__ = ["MINIMAL_FILES", "PROJECT_FILES", "package_name", "pascal"]


def package_name(name: str) -> str:
    """Turn a project name into a valid Python package name (snake_case)."""
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()
    if not slug:
        slug = "app"
    if slug[0].isdigit():
        slug = f"app_{slug}"
    return slug


def pascal(name: str) -> str:
    return "".join(part.capitalize() for part in package_name(name).split("_") if part) or "App"


def _files() -> dict[str, str]:
    """The skeleton, as ``relative path -> template`` (with placeholders)."""
    return {
        ".gitignore": """\
.venv/
__pycache__/
*.py[cod]
.env
*.db
*.db-*
.agentkit/
storage/*
!storage/.gitignore
dist/
.pytest_cache/
.ruff_cache/
.mypy_cache/
""",
        ".env.example": """\
# Copy to .env and fill in. The only required value is your provider key.
OPENAI_API_KEY=
AGENT_NAME={{project}}
OWNER_ID=owner
OWNER_NAME=Owner
# Enable the durable queue (agentkit queue:work) instead of running jobs inline.
QUEUE_ENABLED=false
QUEUE_DEFAULT=default
# Optional:
# AGENTKIT_HOME=~/.agentkit
# MODEL_NAME=openai:gpt-4o-mini
# OBSERVABILITY=off
""",
        "README.md": """\
# {{project}}

An [agentkit](https://github.com/kakalition/agentkit) agent. This project ships the
whole tree — read it, then delete what you don't need.

## Quickstart

```bash
cp .env.example .env      # then set OPENAI_API_KEY
uv sync                   # or: pip install -e .
agentkit tinker           # chat with your agent
agentkit serve            # web UI + scheduler on http://127.0.0.1:8787
```

## Layout

```
bootstrap.py                     # App(...) — the boot target
app/
  config.py                      # Settings + a layered config Section
  Agents/assistant.py            # the agent builder (persona, tools, policy)
  Console/Kernel.py              # schedule() + commands()
  Console/Commands/PinNote.py    # a CLI command
  Events/NoteSaved.py            # an event payload
  Listeners/LogNoteSaved.py      # a listener (Listener base)
  Jobs/SyncNotes.py              # a queued/durable job
  Middleware/Timing.py           # a turn middleware (Middleware base)
  Models/Note.py                 # a Model (table)
  Notifications/NoteSaved.py     # a Notification
  Policies/AssistantPolicy.py    # a ToolPolicy
  Providers/AppServiceProvider.py    # the application provider (mandatory)
  Providers/EventServiceProvider.py  # registers listeners
  Repositories/                  # Repository classes + AppRepositories
  Rules/NonEmpty.py              # a validation rule
  Services/NoteService.py        # a domain service (Service base)
  Tools/notes.py                 # tool functions
config/app.py                    # config/<section>.py overrides
skills/hello/SKILL.md            # a discoverable skill
prompts/system.md                # a versioned prompt
evals/smoke.yaml                 # an evaluation suite
database/README.md               # notes on schema/migrations
storage/                         # local artifacts (Storage facade)
tests/
SOUL.md                          # the persona
```

## What to explore

- **Providers** — `app/Providers/AppServiceProvider.py` binds everything; `EventServiceProvider` wires listeners.
  Providers may declare `bindings`/`singletons` maps, and a `DeferrableProvider` (`provides()`) loads on first use.
- **Scheduling** — `app/Console/Kernel.py` uses the fluent scheduler.
- **Queue** — `app/Jobs/SyncNotes.py`; set `QUEUE_ENABLED=true` and run `agentkit queue:work`.
- **Notifications** — `app/Notifications/NoteSaved.py`; send with `app.notify(...)`.
- **Data** — `app/Models`, `app/Repositories` (CRUD for free from `Repository`).
- **Safety** — `app/Policies`, `app/Rules`.
- **Helpers** — `from agentkit import app, config, env, dispatch, event, storage, cache, queue`.

## Test & evaluate

```bash
pytest
agentkit eval evals/smoke.yaml
```
""",
        "pyproject.toml": """\
[project]
name = "{{project}}"
version = "0.1.0"
description = "An agentkit agent."
requires-python = ">=3.11"
dependencies = ["agentkit"]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "ruff>=0.5", "mypy>=1.10"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
""",
        "conftest.py": '''"""Pytest root.

Adds the project to ``sys.path`` and keeps tests hermetic: a temporary agent home
and the offline ``hash`` embedder, so nothing touches your real data or the network.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

os.environ.setdefault("AGENT_HOME", tempfile.mkdtemp(prefix="app-test-"))
os.environ.setdefault("MEMORY_EMBEDDING_BACKEND", "hash")
os.environ.setdefault("OBSERVABILITY", "off")
os.environ.setdefault("WEBUI_ENABLED", "false")
''',
        "SOUL.md": """\
# {{Project}}

You are {{project}}, a helpful personal assistant. You are warm, concise, and
practical. Remember durable facts about the owner, use your tools when they help,
and load a skill when it is relevant.
""",
        "bootstrap.py": '''"""The application entry point.

``agentkit serve`` boots ``bootstrap:app``, so this is the single place your app is
assembled: settings, the repository container, and the service providers.
"""

from __future__ import annotations

from agentkit import App

from app.config import Settings
from app.Providers.AppServiceProvider import AppServiceProvider
from app.Providers.EventServiceProvider import EventServiceProvider
from app.Repositories import AppRepositories

app = App(name="{{project}}", settings=Settings, repos_factory=AppRepositories)
app.providers([EventServiceProvider, AppServiceProvider])
''',
        "app/__init__.py": '''"""The application: agents, tools, providers, models, and everything else."""
''',
        "app/config.py": '''"""Application settings and a layered config section."""

from __future__ import annotations

from agentkit import AgentSettings, Section


class Settings(AgentSettings):
    """Runtime settings (environment-driven). Extend as your app grows."""

    agent_name: str = "{{project}}"


class AppSection(Section):
    """App-specific configuration.

    Precedence: ``defaults < config/app.py < environment``. Register it with
    ``app.config("app", AppSection)`` and read it with ``app.config("app")``.
    """

    env_prefix = "{{PREFIX}}_"
    greeting: str = "Hello!"
''',
        # -- Providers ---------------------------------------------------------
        "app/Providers/__init__.py": '''"""Service providers — where the app is assembled."""
''',
        "app/Providers/AppServiceProvider.py": '''"""The application service provider (mandatory).

Bind the agent, config, middleware, commands, and schedule here. ``register`` is
for declarations (no side effects); ``boot`` is for effects.
"""

from __future__ import annotations

from typing import Any

from agentkit import Provider

from app.Agents.assistant import build_assistant
from app.config import AppSection
from app.Console.Kernel import Kernel
from app.Middleware.Timing import Timing


class AppServiceProvider(Provider):
    def register(self, app: Any) -> None:
        app.config("app", AppSection)
        app.agent(build_assistant())
        app.middleware(Timing())
        app.commands(Kernel().commands())
        Kernel().schedule(app)

    def boot(self, app: Any) -> None:
        # Register durable tasks before any init_scheduler() runs.
        from app.Jobs.SyncNotes import register as register_sync_notes

        register_sync_notes()
''',
        "app/Providers/EventServiceProvider.py": '''"""Registers events and their listeners."""

from __future__ import annotations

from typing import Any

from agentkit import Provider

from app.Listeners.LogNoteSaved import LogNoteSaved

LISTENERS = [LogNoteSaved]


class EventServiceProvider(Provider):
    def register(self, app: Any) -> None:
        for listener_class in LISTENERS:
            listener = listener_class()
            for name in type(listener).events():
                app.on(name, listener)
''',
        # -- Console -----------------------------------------------------------
        "app/Console/__init__.py": '''"""Console kernel and commands."""
''',
        "app/Console/Kernel.py": '''"""The console kernel: the schedule and the command list.

``app.schedule(...)`` is the fluent scheduler (Laravel's ``$schedule``).
"""

from __future__ import annotations

from typing import Any

from app.Console.Commands.PinNote import PinNoteCommand


class Kernel:
    def schedule(self, app: Any) -> None:
        # A durable heartbeat (survives restarts; see `agentkit schedule:list`).
        app.schedule("sync_notes").name("sync-notes").every_fifteen_minutes().without_overlapping().description("Sync notes into the knowledge base.")

    def commands(self) -> list[Any]:
        return [PinNoteCommand()]
''',
        "app/Console/Commands/__init__.py": '''"""Your CLI commands."""
''',
        "app/Console/Commands/PinNote.py": '''"""A console command: pin the most recent note and announce it."""

from __future__ import annotations

from typing import Any

import typer

from agentkit import Command

from app.Notifications.NoteSaved import NoteSaved
from app.Services.NoteService import NoteService


class PinNoteCommand(Command):
    name = "note:pin"
    help = "Pin the most recent note."

    def run(self, app: Any) -> None:
        note = NoteService(app).pin_latest()
        if note is None:
            typer.echo("no notes to pin")
            return
        app.notify(NoteSaved(note.text), to="log")
        typer.echo(f"pinned note #{note.id}")
''',
        # -- Models & repositories --------------------------------------------
        "app/Models/__init__.py": '''"""Models (tables)."""
''',
        "app/Models/Note.py": '''"""A note table."""

from __future__ import annotations

from sqlmodel import Field

from agentkit import Model


class Note(Model, table=True):
    __tablename__ = "notes"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: str = Field(index=True)
    text: str
    pinned: bool = False
''',
        "app/Repositories/__init__.py": '''"""Repositories and the container that holds them."""

from __future__ import annotations

from agentkit.db.repositories import Repositories

from app.Repositories.NoteRepository import NoteRepository


class AppRepositories(Repositories):
    """Extra repositories are declared here and attached automatically."""

    repositories = {"notes": NoteRepository}


__all__ = ["AppRepositories", "NoteRepository"]
''',
        "app/Repositories/NoteRepository.py": '''"""Note persistence — CRUD is inherited from ``Repository``."""

from __future__ import annotations

from agentkit import Repository

from app.Models.Note import Note


class NoteRepository(Repository[Note]):
    model = Note

    async def latest(self) -> Note | None:
        return await self.where().latest("id").first()

    async def pinned(self) -> list[Note]:
        return await self.where(pinned=True).all()
''',
        # -- Services ----------------------------------------------------------
        "app/Services/__init__.py": '''"""Domain services."""
''',
        "app/Services/NoteService.py": '''"""A domain service — the app wires itself in via the ``Service`` base."""

from __future__ import annotations

from agentkit.foundation.service import Service


class NoteService(Service):
    async def add(self, text: str):  # noqa: ANN201
        async with self.repositories as repos:
            return await repos.notes.create(text=text)

    async def all(self) -> list:  # noqa: ANN401
        async with self.repositories as repos:
            return await repos.notes.all(order_by="id")

    async def pin_latest(self):  # noqa: ANN201
        async with self.repositories as repos:
            note = await repos.notes.where().latest("id").first()
            if note is not None:
                await repos.notes.update(note.id, pinned=True)
            return note
''',
        # -- Agents & tools ----------------------------------------------------
        "app/Agents/__init__.py": '''"""Agent builders."""
''',
        "app/Agents/assistant.py": '''"""The agent, built declaratively with ``Agent.make(...)``."""

from __future__ import annotations

from agentkit import Agent

from app.Policies.AssistantPolicy import assistant_policy
from app.Tools.notes import add_note, current_time, list_notes

INSTRUCTIONS = (
    "You are {{project}}, a concise and helpful assistant. Use your tools when "
    "they help, remember durable facts about the owner, and load a skill when it "
    "is relevant."
)


def build_assistant() -> Agent:
    return (
        Agent.make("{{project}}")
        .persona()                       # reads <AGENT_HOME>/SOUL.md
        .instructions(INSTRUCTIONS)
        .memory()                        # remember / recall / forget tools
        .skills()                        # discover skills/*/SKILL.md
        .tool(current_time)
        .tool(add_note)
        .tool(list_notes)
        .policy(assistant_policy())      # safety policy
        .output(str)
    )
''',
        "app/Tools/__init__.py": '''"""Tool functions — how your agent acts."""
''',
        "app/Tools/notes.py": '''"""Tools. The first argument is a RunContext[Deps]; the docstring is the schema."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic_ai import RunContext

from agentkit import emit, validate
from agentkit.deps import Deps

from app.Rules.NonEmpty import NonEmpty


async def current_time(ctx: RunContext[Deps]) -> str:
    """Return the current UTC time in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


async def add_note(ctx: RunContext[Deps], text: str) -> str:
    """Save a short note for the owner.

    Args:
        text: The note body.
    """
    validate({"text": text}, {"text": ["required", "string", NonEmpty, "max:500"]})
    note = await ctx.deps.repos.notes.create(text=text)
    await emit("note.saved", note_id=note.id, text=note.text, conversation_id=ctx.deps.conversation_id)
    return f"saved note #{note.id}: {note.text}"


async def list_notes(ctx: RunContext[Deps]) -> str:
    """List the owner's saved notes."""
    notes = await ctx.deps.repos.notes.all(order_by="id")
    if not notes:
        return "No notes yet."
    return "\\n".join(f"#{note.id} {note.text}" for note in notes)
''',
        # -- Events & listeners ------------------------------------------------
        "app/Events/__init__.py": '''"""Event payloads (see ``agentkit.emit``)."""
''',
        "app/Events/NoteSaved.py": '''"""The payload shape for the ``note.saved`` event."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NoteSaved:
    note_id: int
    text: str
''',
        "app/Listeners/__init__.py": '''"""Event listeners."""
''',
        "app/Listeners/LogNoteSaved.py": '''"""Logs every saved note (a ``Listener``)."""

from __future__ import annotations

from agentkit import Listener
from agentkit.logging import get_logger


class LogNoteSaved(Listener):
    event = "note.saved"

    def handle(self, event) -> None:  # noqa: ANN001
        get_logger("app").info("note saved #%s: %s", event.get("note_id"), event.get("text"))
''',
        # -- Jobs --------------------------------------------------------------
        "app/Jobs/__init__.py": '''"""Jobs — work you can dispatch (inline or queued)."""
''',
        "app/Jobs/SyncNotes.py": '''"""A durable job: summarize the notes. Runs on the scheduler or the queue."""

from __future__ import annotations

from typing import Any

from agentkit import Job
from agentkit.logging import get_logger


class SyncNotes(Job):
    queue = "default"
    max_retries = 3

    async def handle(self, app: Any) -> None:
        async with app.repositories() as repos:
            count = await repos.notes.count()
        get_logger("app").info("sync notes: %s note(s)", count)


async def run() -> None:
    """Scheduler task entry point (runs in a worker; resolves its own runtime)."""
    from agentkit import scheduler
    from agentkit.runtime import repositories

    async with repositories(scheduler.ensure_configured()) as repos:
        get_logger("app").info("sync notes: %s note(s)", await repos.notes.count())


def register() -> None:
    from agentkit import scheduler

    scheduler.task("sync_notes")(run)
''',
        # -- Notifications -----------------------------------------------------
        "app/Notifications/__init__.py": '''"""Notifications delivered over channels."""
''',
        "app/Notifications/NoteSaved.py": '''"""A notification sent when a note is pinned."""

from __future__ import annotations

from agentkit import Notification


class NoteSaved(Notification):
    channels = ("log",)

    def __init__(self, text: str) -> None:
        self.message = text

    def content(self) -> str:
        return f"📝 Note saved: {self.message}"
''',
        # -- Policies & rules --------------------------------------------------
        "app/Policies/__init__.py": '''"""Tool policies (safety)."""
''',
        "app/Policies/AssistantPolicy.py": '''"""The agent's tool policy. Add tool names to ``deny`` to block them."""

from __future__ import annotations

from agentkit import ToolPolicy


def assistant_policy() -> ToolPolicy:
    return ToolPolicy(deny=set())
''',
        "app/Rules/__init__.py": '''"""Validation rules (see ``agentkit.validate``)."""
''',
        "app/Rules/NonEmpty.py": '''"""A custom validation rule: the value must contain non-whitespace."""

from __future__ import annotations

from typing import Any


def NonEmpty(value: Any) -> str | None:  # noqa: N802 - reads like a rule
    return None if str(value).strip() else "must not be blank"
''',
        # -- Middleware --------------------------------------------------------
        "app/Middleware/__init__.py": '''"""Turn middleware."""
''',
        "app/Middleware/Timing.py": '''"""Logs each turn's duration (a ``Middleware``)."""

from __future__ import annotations

import time

from agentkit import Middleware
from agentkit.logging import get_logger


class Timing(Middleware):
    async def handle(self, turn, call_next):  # noqa: ANN001, ANN201
        start = time.perf_counter()
        result = await call_next()
        get_logger("app").info(
            "turn %s took %.3fs", turn.conversation_id, time.perf_counter() - start
        )
        return result
''',
        # -- Config / prompts / skills / evals / misc --------------------------
        "config/app.py": """\
# Overrides for the "app" config section (defaults < this file < environment).
config = {"greeting": "Hello from config/app.py!"}
""",
        "skills/hello/SKILL.md": """\
---
name: hello
description: How to greet the owner well.
---

# Greeting

Greet the owner by name when you know it; otherwise greet them warmly and offer
to help. Keep greetings to one or two sentences.
""",
        "prompts/system.md": """\
---
name: system
version: 1
description: The base system prompt.
---

You are {{project}}, a concise and helpful assistant.
""",
        "evals/smoke.yaml": """\
name: smoke

cases:
  - name: stays in persona
    input: "hello"
    not_contains:
      - "As an AI language model"
  - name: saves a note
    input: "note: buy milk"
    calls: add_note
""",
        "database/README.md": """\
# Database

agentkit persists everything in a single local database (libSQL/SQLite) via
SQLModel. Tables are created from model metadata at startup.

- Add models under `app/Models/` and repositories under `app/Repositories/`.
- `agentkit` repairs drifted columns automatically (`sync_missing_columns`).
- For complex schema evolution, see `agentkit.db.migrations` (Alembic helper).
""",
        "storage/.gitignore": """\
# Local artifacts written through the Storage facade.
*
!.gitignore
""",
        "tests/test_smoke.py": '''"""A first test — run with ``pytest``."""

from __future__ import annotations


def test_app_boots() -> None:
    from bootstrap import app

    app.boot()
    assert app.name == "{{project}}"

    tools = set(app.agent()._function_toolset.tools)
    assert {"current_time", "add_note", "list_notes", "remember", "recall"} <= tools
''',
        "tests/test_note_service.py": '''"""The repository, service, and schedule are wired and usable."""

from __future__ import annotations

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_HOME", str(tmp_path))
    monkeypatch.setenv("MEMORY_EMBEDDING_BACKEND", "hash")
    from agentkit.config import get_settings

    get_settings.cache_clear()
    from bootstrap import app as application

    application.boot()
    return application


async def test_service_and_repository(app):
    from app.Services.NoteService import NoteService

    service = NoteService(app)
    await service.add("buy milk")
    await service.add("walk the dog")
    assert len(await service.all()) == 2


async def test_schedule_registered(app):
    async with app.repositories() as repos:
        names = {job.name for job in await repos.schedules.list()}
    assert "sync-notes" in names
''',
    }


MINIMAL_FILES: dict[str, str] = _files()
PROJECT_FILES: dict[str, str] = MINIMAL_FILES
