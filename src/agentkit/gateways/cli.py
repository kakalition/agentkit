"""CLI helpers: async runner + a Typer app factory with observability wiring."""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from agentkit.observability import setup_logfire


def asyncio_run(coro: Any) -> Any:
    return asyncio.run(coro)


def build_cli(*, help: str = "agentkit app", no_args_is_help: bool = True) -> typer.Typer:
    """Create a Typer app. Wire `setup_logfire` yourself in the entry point."""
    return typer.Typer(add_completion=False, help=help, no_args_is_help=no_args_is_help)


def entrypoint(app: typer.Typer) -> None:
    """Console-script entry: enable observability, then run the app."""
    setup_logfire()
    app()
