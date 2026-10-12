"""Artisan-style scaffolding generators (``make:*``).

Each generator writes one file under a conventional subdirectory and refuses to
overwrite unless ``force=True``. The emitted modules are import-clean and boot
against the current agentkit API.
"""

from __future__ import annotations

from pathlib import Path

AGENT_TEMPLATE = '''"""The {name} agent."""

from __future__ import annotations

from agentkit import Agent


def build() -> Agent:
    return (
        Agent.make("{name}")
        .persona()
        .instructions("Describe what the {name} agent does.")
        .memory()
        .output(str)
    )
'''

PROVIDER_TEMPLATE = '''"""The {pascal} provider."""

from __future__ import annotations

from agentkit import Agent, App, Provider


class {pascal}Provider(Provider):
    def register(self, app: App) -> None:
        app.agent(
            Agent.make("{name}")
            .persona()
            .instructions("Describe what the {name} agent does.")
            .memory()
            .output(str)
        )

    def boot(self, app: App) -> None:
        app.on("turn.end", lambda event: None)
'''

TOOL_TEMPLATE = '''"""The {name} tool."""

from __future__ import annotations

from pydantic_ai import RunContext

from agentkit.deps import Deps


async def {name}(ctx: RunContext[Deps]) -> str:
    """Describe what {name} does."""
    return "not implemented"
'''

CHANNEL_TEMPLATE = '''"""The {name} channel."""

from __future__ import annotations

from typing import Any

from agentkit import Service


def {name}_channel(app: Any) -> Service:
    def run() -> None:
        raise NotImplementedError("wire up the {name} channel")

    return Service("{name}", run)
'''

COMMAND_TEMPLATE = '''"""The {name} command."""

from __future__ import annotations

from typing import Any

from agentkit import Command


class {pascal}Command(Command):
    name = "{name}"
    help = "Describe the {name} command."

    def run(self, app: Any) -> None:
        raise NotImplementedError
'''

MODEL_TEMPLATE = '''"""The {pascal} model."""

from __future__ import annotations

from sqlmodel import Field

from agentkit import Model


class {pascal}(Model, table=True):
    __tablename__ = "{table}"

    id: int | None = Field(default=None, primary_key=True)
'''

_GENERATORS: dict[str, tuple[str, str]] = {
    "agent": ("agents/{name}.py", AGENT_TEMPLATE),
    "provider": ("providers/{name}.py", PROVIDER_TEMPLATE),
    "tool": ("tools/{name}.py", TOOL_TEMPLATE),
    "channel": ("channels/{name}.py", CHANNEL_TEMPLATE),
    "command": ("commands/{name}.py", COMMAND_TEMPLATE),
    "model": ("models/{name}.py", MODEL_TEMPLATE),
}

KINDS = tuple(_GENERATORS)


def _pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.replace("-", "_").split("_") if part)


def _snake(name: str) -> str:
    return name.replace("-", "_").strip("_")


def target_path(kind: str, name: str, directory: str | Path = ".") -> Path:
    """Where a given generator would write (without writing)."""
    if kind not in _GENERATORS:
        raise KeyError(kind)
    relative, _ = _GENERATORS[kind]
    return Path(directory) / relative.format(name=_snake(name))


def generate(kind: str, name: str, *, directory: str | Path = ".", force: bool = False) -> Path:
    """Render ``kind`` for ``name`` into ``directory``; return the written path."""
    if kind not in _GENERATORS:
        raise KeyError(f"unknown generator: {kind}")
    relative, template = _GENERATORS[kind]
    snake = _snake(name)
    path = Path(directory) / relative.format(name=snake)
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists (pass force=True to overwrite)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        template.format(name=snake, pascal=_pascal(name), table=snake),
        encoding="utf-8",
    )
    return path


__all__ = ["KINDS", "generate", "target_path"]
