"""The built-in CLI: a class-based Click group over the built-in commands."""

from __future__ import annotations

import click

from agentkit.cli.commands import BUILTIN_COMMANDS
from agentkit.foundation.console import Kernel

_HELP = "agentkit — build and operate production PydanticAI assistant agents."


def build_cli() -> click.Group:
    """Build the built-in Click group from the class-based built-in commands."""
    kernel = Kernel()
    return kernel.build_group(
        "agentkit",
        commands=[command() for command in BUILTIN_COMMANDS],
        help=_HELP,
    )


app = build_cli()
