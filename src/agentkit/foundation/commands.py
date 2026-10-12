"""Application commands + boot-target resolution for the CLI.

A :class:`Command` is a small, app-facing unit (``name`` + ``run(app)``). Service
providers contribute them via :meth:`Provider.commands`; they are collected on
the app and can be installed onto the Typer app with :func:`install`.

``load_bootstrap`` resolves the app to boot (``AGENTKIT_BOOTSTRAP``, default
``bootstrap:app``).
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any

DEFAULT_BOOTSTRAP = "bootstrap:app"


class Command:
    """Base class for a provider-contributed command."""

    name: str = ""
    help: str = ""

    def run(self, app: Any) -> None:
        raise NotImplementedError


def _add_cwd_to_path() -> None:
    """Make the current project importable, so ``bootstrap:app`` resolves.

    Console scripts run with the script's directory on ``sys.path``, not the
    working directory, so ``agentkit serve`` from a project root would otherwise
    fail to import its own ``bootstrap.py``.
    """
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)


def load_bootstrap(target: str | None = None) -> Any:
    """Import and return the app named by ``target`` (``module:attr``)."""
    from agentkit.foundation.application import App

    reference = target or os.environ.get("AGENTKIT_BOOTSTRAP", DEFAULT_BOOTSTRAP)
    module_name, _, attr = reference.partition(":")
    _add_cwd_to_path()
    module = importlib.import_module(module_name)
    obj = getattr(module, attr) if attr else module
    if isinstance(obj, App):
        return obj
    app = obj() if callable(obj) else obj
    if not isinstance(app, App):
        raise TypeError(f"bootstrap {reference!r} did not yield an App")
    return app


def install(typer_app: Any, commands: list[Any]) -> None:
    """Register app commands as Typer subcommands (each boots the app)."""
    for command in commands:
        instance = command() if isinstance(command, type) else command
        _install_one(typer_app, instance)


def _install_one(typer_app: Any, command: Command) -> None:
    def callback() -> None:
        app = load_bootstrap()
        app.boot()
        command.run(app)

    callback.__name__ = command.name.replace(":", "_").replace("-", "_")
    callback.__doc__ = command.help or None
    typer_app.command(command.name)(callback)


__all__ = ["Command", "DEFAULT_BOOTSTRAP", "install", "load_bootstrap"]
