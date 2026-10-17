"""agentkit console entry point: workspace management, web UI, and the CLI.

Commands are class-based :class:`~agentkit.foundation.commands.Command`
subclasses collected into a Click group (see :mod:`agentkit.cli._app`).
"""

from __future__ import annotations

from agentkit.cli import commands  # noqa: F401  (aggregates the built-in commands)
from agentkit.cli._app import app  # noqa: F401
from agentkit.cli.commands.memory import _memory_scope  # noqa: F401
from agentkit.cli.commands.workspace import _legacy_agent_names  # noqa: F401
from agentkit.config import get_settings


def main() -> None:
    from agentkit.logging import setup_logging

    setup_logging(get_settings())
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
