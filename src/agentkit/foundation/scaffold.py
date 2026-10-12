"""Project scaffolding — a bare, sane starting point (``agentkit new``).

Generates a runnable project from a small, opinionated skeleton: an `App` with a
service provider, an assistant agent (persona, a tool, memory, skills), a skill, a
prompt, a config section, an eval suite, and a test. You then explore and
customise it — nothing is hidden behind a black box.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["PROJECT_FILES", "package_name", "scaffold_project"]

_PLACEHOLDERS = ("{{project}}", "{{package}}", "{{Project}}", "{{PREFIX}}")


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
# Optional overrides:
# AGENTKIT_HOME=~/.agentkit
# MODEL_NAME=openai:gpt-4o-mini
# OBSERVABILITY=off
""",
        "README.md": """\
# {{project}}

A minimal [agentkit](https://github.com/kakalition/agentkit) agent.

## Quickstart

```bash
cp .env.example .env      # then set OPENAI_API_KEY
uv sync                   # or: pip install -e .
agentkit tinker           # chat with your agent
```

Serve every channel (web UI, scheduler) in one process:

```bash
agentkit serve            # http://127.0.0.1:8787
```

## Layout

```
bootstrap.py            # App(...) — the boot target
app/
  config.py             # Settings + a layered config Section
  models.py             # Model + Repository (CRUD for free) + AppRepositories
  providers.py          # the service provider (agent, tools, listeners)
  tools.py              # tool functions
config/app.py           # config/<section>.py overrides
skills/hello/SKILL.md   # a discoverable skill
prompts/system.md       # a versioned prompt
evals/smoke.yaml        # an evaluation suite
tests/test_smoke.py     # a first test
SOUL.md                 # the persona
```

## Customise

- **Persona** — edit `SOUL.md`.
- **Instructions & tools** — edit `app/providers.py` and `app/tools.py`.
- **Models & repositories** — add a `Model` and a `Repository` in `app/models.py`.
- **Skills** — add `skills/<name>/SKILL.md` folders.
- **Prompts** — add `prompts/<name>.md` and load with `.prompt(...)`.
- **Config** — extend `AppSection` in `app/config.py`; override in `config/app.py` or env.
- **Schedules, notifications, jobs** — see `app.schedule(...)`, `Notification`, `Job`.
- **Scaffold more** — `agentkit make:provider`, `make:tool`, `make:channel`, `make:model`.

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
dependencies = [
    "agentkit",
]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.5", "mypy>=1.10"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["{{package}}"]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
""",
        "conftest.py": '''"""Pytest root — makes the project importable from tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
''',
        "SOUL.md": """\
# {{Project}}

You are {{project}}, a helpful personal assistant. You are warm, concise, and
practical. Ask a clarifying question when a request is ambiguous, and remember
durable facts about the owner when you learn them.
""",
        "bootstrap.py": '''"""The application entry point.

``agentkit serve`` boots ``bootstrap:app`` by default, so this module is the
single place your app is assembled.
"""

from __future__ import annotations

from agentkit import App

from app.config import Settings
from app.models import AppRepositories
from app.providers import AppProvider

app = App(name="{{project}}", settings=Settings, repos_factory=AppRepositories)
app.providers([AppProvider])
''',
        "{{package}}/__init__.py": '''"""The application package — your agents, tools, providers, and models."""

__all__ = ["config", "models", "providers", "tools"]
''',
        "{{package}}/config.py": '''"""Application settings and a layered config section."""

from __future__ import annotations

from agentkit import AgentSettings, Section


class Settings(AgentSettings):
    """Runtime settings (environment-driven). Extend as your app grows."""

    agent_name: str = "{{project}}"


class AppSection(Section):
    """App-specific configuration.

    Layer values with precedence ``defaults < config/app.py < environment``.
    """

    env_prefix = "{{PREFIX}}_"
    greeting: str = "Hello!"
''',
        "{{package}}/models.py": '''"""Models and repositories.

``Model`` gives you a table; ``Repository`` gives you CRUD for free — declare the
model and inherit the whole surface. Attach repositories to the container with the
``repositories`` map.
"""

from __future__ import annotations

from sqlmodel import Field

from agentkit import Model, Repository
from agentkit.db.repositories import Repositories


class Note(Model, table=True):
    __tablename__ = "notes"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: str = Field(index=True)
    text: str
    pinned: bool = False


class NoteRepo(Repository[Note]):
    """Create, list, update, delete notes — inherited from ``Repository``."""

    model = Note

    def pinned(self) -> list[Note]:
        return self.where(pinned=True).all()


class AppRepositories(Repositories):
    """The app's repository container. Extra repos are declared here."""

    repositories = {"notes": NoteRepo}
''',
        "{{package}}/tools.py": '''"""Tool functions — how your agent acts.

Tools are ordinary functions. The first argument is a PydanticAI ``RunContext``
(typed with ``Deps``); the docstring becomes the description the model sees.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic_ai import RunContext

from agentkit.deps import Deps


async def current_time(ctx: RunContext[Deps]) -> str:
    """Return the current UTC time in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


async def add_note(ctx: RunContext[Deps], text: str) -> str:
    """Save a short note for the owner.

    Args:
        text: The note body.
    """
    note = ctx.deps.repos.notes.create(text=text)
    return f"saved note #{note.id}: {text}"


async def list_notes(ctx: RunContext[Deps]) -> str:
    """List the owner's saved notes."""
    notes = ctx.deps.repos.notes.all(order_by="id")
    if not notes:
        return "No notes yet."
    return "\\n".join(f"#{note.id} {note.text}" for note in notes)
''',
        "{{package}}/providers.py": '''"""The service provider — where the app is assembled.

``register`` binds concerns (agent, config). ``boot`` performs side effects
(event listeners, task registration). Importing this module must be side-effect
free.
"""

from __future__ import annotations

from typing import Any

from agentkit import Agent, Provider

from {{package}}.config import AppSection
from {{package}}.tools import add_note, current_time, list_notes

INSTRUCTIONS = (
    "You are {{project}}, a concise and helpful assistant. Use your tools when "
    "they help, remember durable facts about the owner, and load a skill when it "
    "is relevant."
)


class AppProvider(Provider):
    """Binds {{project}}'s agent and configuration."""

    def register(self, app: Any) -> None:
        app.config("app", AppSection)
        app.agent(
            Agent.make("{{project}}")
            .persona()                 # reads <AGENT_HOME>/SOUL.md
            .instructions(INSTRUCTIONS)
            .memory()                  # remember / recall / forget tools
            .skills()                  # discover skills/*/SKILL.md
            .tool(current_time)
            .tool(add_note)
            .tool(list_notes)
            .output(str)
        )

    def boot(self, app: Any) -> None:
        # Observe the lifecycle without affecting it.
        app.on("turn.end", lambda event: None)
''',
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
        "config/app.py": """\
# Overrides for the "app" config section (defaults < this file < environment).
config = {"greeting": "Hello from config/app.py!"}
""",
        "evals/smoke.yaml": """\
name: smoke

cases:
  - name: stays in persona
    input: "hello"
    not_contains:
      - "As an AI language model"
  - name: answers briefly
    input: "say hi in three words or fewer"
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
    }


PROJECT_FILES = _files()


def scaffold_project(
    name: str, directory: str | Path = ".", *, force: bool = False
) -> Path:
    """Write the skeleton for ``name`` into ``directory/name`` and return the path.

    Refuses to write into a non-empty target unless ``force=True``.
    """
    package = package_name(name)
    package_dir = "app"  # Laravel-style flat `app/` package
    target = Path(directory).expanduser() / name
    if target.exists() and any(target.iterdir()) and not force:
        raise FileExistsError(f"{target} already exists and is not empty (pass force=True)")

    replacements = {
        "{{project}}": name,
        "{{package}}": package_dir,
        "{{Project}}": pascal(name),
        "{{PREFIX}}": package.upper(),
    }
    for relative, template in PROJECT_FILES.items():
        content = template
        for key, value in replacements.items():
            content = content.replace(key, value)
        destination = target / relative.replace("{{package}}", package_dir)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    return target
