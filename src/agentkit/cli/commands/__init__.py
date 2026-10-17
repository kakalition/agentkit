"""CLI command modules, aggregated into the built-in command registry.

Each module defines class-based :class:`~agentkit.foundation.commands.Command`
subclasses and exposes a ``COMMANDS`` list. This package concatenates them into
``BUILTIN_COMMANDS`` for the class-based Click kernel.
"""

from __future__ import annotations

from agentkit.cli.commands import (
    auth,
    catalog,
    core,
    credentials,
    data,
    evals,
    extensions,
    generators,
    inspect,
    knowledge,
    learning,
    memory,
    ops,
    queue,
    runtime,
    schedule,
    skills,
    spec,
    surfaces,
    training,
    webhooks,
    workspace,
)
from agentkit.foundation.commands import Command

_MODULES = [
    core,
    generators,
    memory,
    queue,
    schedule,
    skills,
    credentials,
    learning,
    auth,
    webhooks,
    knowledge,
    workspace,
    surfaces,
    inspect,
    runtime,
    data,
    ops,
    catalog,
    extensions,
    spec,
    training,
    evals,
]

BUILTIN_COMMANDS: list[type[Command]] = [
    command for module in _MODULES for command in getattr(module, "COMMANDS", [])
]

__all__ = [
    "BUILTIN_COMMANDS",
    "auth",
    "catalog",
    "core",
    "credentials",
    "data",
    "evals",
    "extensions",
    "generators",
    "inspect",
    "knowledge",
    "learning",
    "memory",
    "ops",
    "queue",
    "runtime",
    "schedule",
    "skills",
    "spec",
    "surfaces",
    "training",
    "webhooks",
    "workspace",
]
