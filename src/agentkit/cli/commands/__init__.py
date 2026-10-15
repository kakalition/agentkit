"""CLI command modules. Importing this package registers every command."""

from __future__ import annotations

from agentkit.cli.commands import (
    core,
    evals,
    generators,
    inspect,
    knowledge,
    learning,
    memory,
    queue,
    runtime,
    schedule,
    skills,
    workspace,
)

__all__ = [
    "core",
    "evals",
    "generators",
    "inspect",
    "knowledge",
    "learning",
    "memory",
    "queue",
    "runtime",
    "schedule",
    "skills",
    "workspace",
]
