"""Inspect registered extensions (``agentkit extensions list``)."""

from __future__ import annotations

import typer

from agentkit.cli._app import app

__all__ = ["extensions_app"]

extensions_app = typer.Typer(
    no_args_is_help=True, help="Inspect registered agentkit extensions."
)
app.add_typer(extensions_app, name="extensions")


@extensions_app.command("list")
def extensions_list(
    bootstrap: str | None = typer.Option(None, "--bootstrap", help="module:attr of the app."),
) -> None:
    """List discovered extensions and what they contribute."""
    from agentkit.extensions import EXTENSIONS
    from agentkit.extensions.discovery import discover_manifests

    for manifest in discover_manifests():
        EXTENSIONS.register_manifest(manifest)
    manifests = EXTENSIONS.manifests()
    if not manifests:
        typer.echo("no extensions found")
        return
    for manifest in manifests:
        info = manifest.to_dict()
        typer.echo(f"{info['name']} {info['version']}")
        for key in ("specs", "panels", "actions", "drivers", "catalogs", "codegen"):
            values = info[key]
            if values:
                typer.echo(f"  {key}: {', '.join(map(str, values))}")
