"""CLI command modules. Importing this package registers every command."""

from __future__ import annotations

from agentkit.cli.commands import (
    auth,
    core,
    credentials,
    data,
    evals,
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
    webhooks,
    workspace,
)

__all__ = [
    "auth",
    "core",
    "credentials",
    "data",
    "evals",
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
    "webhooks",
    "workspace",
]
