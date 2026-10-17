"""Artisan-style scaffolding generators (``make:*``).

Each generator writes one file under a conventional subdirectory and refuses to
overwrite unless ``force=True``. The emitted modules are import-clean and boot
against the current agentkit API.
"""

from __future__ import annotations

from pathlib import Path

AGENT_TEMPLATE = '''"""The {pascal} agent (a discoverable ``AgentDefinition``)."""

from __future__ import annotations

from agentkit import AgentDefinition


class {pascal}(AgentDefinition):
    name = "{name}"
    instructions = "Describe what the {name} agent does."
    memory = True
    output = str
'''

PROVIDER_TEMPLATE = '''"""The {pascal} service provider."""

from __future__ import annotations

from typing import Any

from agentkit import Provider


class {pascal}Provider(Provider):
    def register(self, app: Any) -> None:
        # Declare bindings, config sections, middleware, or schedules here.
        return None

    def boot(self, app: Any) -> None:
        return None
'''

POLICY_TEMPLATE = '''"""The {pascal} tool policy."""

from __future__ import annotations

from agentkit import ToolPolicy


def {name}_policy() -> ToolPolicy:
    return ToolPolicy(deny=set())
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

from agentkit import Channel, Service


class {pascal}Channel(Channel):
    name = "{name}"

    def handle(self) -> Any:
        def run() -> None:
            raise NotImplementedError("wire up the {name} channel")

        return Service("{name}", run)
'''

COMMAND_TEMPLATE = '''"""The {name} command."""

from __future__ import annotations

from agentkit import Command


class {pascal}Command(Command):
    signature = "{name}"
    description = "Describe the {name} command."

    def handle(self) -> None:
        raise NotImplementedError
'''

EVENT_TEMPLATE = '''"""The {pascal} event."""

from __future__ import annotations


class {pascal}:
    """An application event."""

    name = "{name}"
'''

LISTENER_TEMPLATE = '''"""The {pascal} listener."""

from __future__ import annotations

from agentkit import Event, Listener


class {pascal}Listener(Listener):
    event = "{name}"

    def handle(self, event: Event) -> None:
        return None
'''

MIGRATION_TEMPLATE = '''"""The {snake} migration."""

from __future__ import annotations

from agentkit import Migration, Schema


class {pascal}(Migration):
    name = "{snake}"

    def up(self, schema: Schema) -> None:
        schema.create("{table}", lambda t: (t.id(), t.timestamps()))

    def down(self, schema: Schema) -> None:
        schema.drop("{table}")
'''

FACTORY_TEMPLATE = '''"""The {pascal} factory."""

from __future__ import annotations

from typing import Any

from agentkit import Factory


class {pascal}Factory(Factory):
    model = None  # set to your model class

    def definition(self) -> dict[str, Any]:
        return {{}}
'''

SEEDER_TEMPLATE = '''"""The {pascal} seeder."""

from __future__ import annotations

from agentkit import Seeder


class {pascal}Seeder(Seeder):
    async def run(self) -> None:
        return None
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
    "agent": ("app/Agents/{pascal}.py", AGENT_TEMPLATE),
    "provider": ("app/Providers/{pascal}Provider.py", PROVIDER_TEMPLATE),
    "tool": ("app/Tools/{name}.py", TOOL_TEMPLATE),
    "policy": ("app/Policies/{pascal}Policy.py", POLICY_TEMPLATE),
    "channel": ("app/Channels/{pascal}Channel.py", CHANNEL_TEMPLATE),
    "command": ("app/Console/Commands/{pascal}Command.py", COMMAND_TEMPLATE),
    "model": ("app/Models/{pascal}.py", MODEL_TEMPLATE),
    "event": ("app/Events/{pascal}.py", EVENT_TEMPLATE),
    "listener": ("app/Listeners/{pascal}Listener.py", LISTENER_TEMPLATE),
    "migration": ("database/migrations/{snake}.py", MIGRATION_TEMPLATE),
    "factory": ("database/factories/{pascal}Factory.py", FACTORY_TEMPLATE),
    "seeder": ("database/seeders/{pascal}Seeder.py", SEEDER_TEMPLATE),
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
    snake = _snake(name)
    return Path(directory) / relative.format(name=snake, pascal=_pascal(name), snake=snake)


def generate(kind: str, name: str, *, directory: str | Path = ".", force: bool = False) -> Path:
    """Render ``kind`` for ``name`` into ``directory``; return the written path."""
    if kind not in _GENERATORS:
        raise KeyError(f"unknown generator: {kind}")
    relative, template = _GENERATORS[kind]
    snake = _snake(name)
    path = Path(directory) / relative.format(name=snake, pascal=_pascal(name), snake=snake)
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists (pass force=True to overwrite)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        template.format(name=snake, pascal=_pascal(name), table=snake, snake=snake),
        encoding="utf-8",
    )
    return path


__all__ = ["KINDS", "generate", "target_path"]
