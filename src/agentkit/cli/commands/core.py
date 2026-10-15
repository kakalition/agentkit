"""Core commands: version, about, and the operator web UI."""

from __future__ import annotations

import typer

from agentkit import __version__
from agentkit.cli._app import app
from agentkit.config import get_settings


@app.command()
def version() -> None:
    """Print the agentkit version."""
    typer.echo(f"agentkit {__version__}")


@app.command()
def about() -> None:
    """Show the agentkit version and the resolved agent home/model."""
    settings = get_settings()
    typer.echo(f"agentkit {__version__}")
    typer.echo(f"agent home: {settings.home}")
    typer.echo(f"model: {settings.model_name}")


@app.command()
def webui(
    host: str | None = typer.Option(None, help="Bind host (default: settings)."),
    port: int | None = typer.Option(None, help="Bind port (default: settings)."),
) -> None:
    """Serve the operator web UI for the agent in the current environment."""
    from agentkit.webui.server import serve_webui

    settings = get_settings()
    typer.echo(f"agentkit webui at http://{host or settings.webui_host}:{port or settings.webui_port}")
    serve_webui(settings=settings, host=host, port=port)


@app.command()
def api(
    host: str | None = typer.Option(None, help="Bind host (default: settings)."),
    port: int | None = typer.Option(None, help="Bind port (default: settings)."),
) -> None:
    """Alias for ``webui`` (serve the API + SPA)."""
    webui(host=host, port=port)
