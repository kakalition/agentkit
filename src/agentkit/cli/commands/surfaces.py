"""Surface commands: the terminal UI and MCP serving."""

from __future__ import annotations

import typer

from agentkit.cli._app import app


@app.command()
def tui(bootstrap: str | None = typer.Option(None, "--bootstrap")) -> None:
    """Open the interactive terminal UI (needs the 'tui' extra)."""
    from agentkit.tui import run_tui

    run_tui(bootstrap=bootstrap)


@app.command("mcp:serve")
def mcp_serve(
    bootstrap: str | None = typer.Option(None, "--bootstrap"),
    transport: str = typer.Option("stdio", "--transport", help="stdio | http | sse"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
) -> None:
    """Serve the booted agent over MCP (an ``ask`` tool)."""
    from agentkit.foundation.commands import load_bootstrap
    from agentkit.mcp.server import serve_agent

    booted = load_bootstrap(bootstrap)
    booted.boot()
    serve_agent(
        booted,
        transport=transport,
        host=host,
        port=port,
        authenticator=getattr(booted, "authenticator", None),
    )
