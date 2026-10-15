"""Runtime commands: serve, up, and the interactive tinker REPL."""

from __future__ import annotations

import contextlib

import typer

from agentkit.cli._app import app
from agentkit.foundation.commands import load_bootstrap


@app.command()
def serve(
    bootstrap: str | None = typer.Option(
        None, "--bootstrap", help="module:attr (default: $AGENTKIT_BOOTSTRAP or bootstrap:app)."
    ),
    scheduler: bool = typer.Option(
        True, "--scheduler/--no-scheduler", help="Also run the durable scheduler worker."
    ),
    webui: bool = typer.Option(True, "--webui/--no-webui", help="Also serve the operator web UI."),
) -> None:
    """Boot the app and run its channels (plus the web UI)."""
    try:
        booted = load_bootstrap(bootstrap)
    except (ImportError, AttributeError, TypeError) as exc:
        typer.echo(
            f"could not load app ({exc}); set AGENTKIT_BOOTSTRAP or create a "
            "'bootstrap.py' exposing `app`.",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    booted.boot()
    with contextlib.suppress(Exception):  # observability is optional
        from agentkit.observability import setup_observability

        setup_observability(booted.settings)
    if scheduler:
        from agentkit import scheduler as sched

        sched.init_scheduler(booted.settings, repos_factory=booted.repos_factory)
    booted.serve(webui=webui)


@app.command()
def up(
    bootstrap: str | None = typer.Option(None, "--bootstrap", help="Boot target (default: bootstrap:app)."),
) -> None:
    """Alias for ``serve``."""
    serve(bootstrap=bootstrap)


@app.command()
def tinker(
    bootstrap: str | None = typer.Option(None, "--bootstrap"),
    conversation_id: str = typer.Option("cli:tinker", help="Conversation id to keep history under."),
) -> None:
    """Interactive REPL: chat with the booted app."""
    import asyncio

    booted = load_bootstrap(bootstrap)
    booted.boot()
    typer.echo("agentkit tinker — type 'exit' to quit.")
    while True:
        try:
            line = input("agentkit> ")
        except (EOFError, KeyboardInterrupt):
            typer.echo("")
            break
        if not line.strip():
            continue
        if line.strip().lower() in {"exit", "quit", ":q"}:
            break
        result = asyncio.run(booted.run(line, conversation_id=conversation_id))
        typer.echo(result.output)
