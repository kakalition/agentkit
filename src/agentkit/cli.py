"""agentkit console entry point: workspace management + standalone web UI."""

from __future__ import annotations

from pathlib import Path

import typer

from agentkit import __version__
from agentkit.config import get_settings
from agentkit.workspace import default_workspace_root, detect_legacy, migrate, workspace_dir

app = typer.Typer(
    add_completion=False,
    help="agentkit — workspace management and the operator web UI.",
    no_args_is_help=True,
)
workspace_app = typer.Typer(no_args_is_help=True, help="Inspect and migrate agent workspaces.")
app.add_typer(workspace_app, name="workspace")


@app.command()
def version() -> None:
    """Print the agentkit version."""
    typer.echo(f"agentkit {__version__}")


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


@workspace_app.command("list")
def workspace_list(
    root: Path | None = typer.Option(None, help="Workspace root (default: ~/.agentkit)."),
) -> None:
    """List agent homes under the workspace root (and any legacy data)."""
    base = root.expanduser() if root else default_workspace_root()
    typer.echo(f"workspace root: {base}")
    names: list[str] = []
    if base.is_dir():
        names = sorted(p.name for p in base.iterdir() if p.is_dir())
    if not names:
        typer.echo("  (no agent homes yet)")
    for name in names:
        home = workspace_dir(name, root=base)
        has_db = any(home.glob("*.db"))
        typer.echo(f"  {name}: {home}{'' if has_db else ' (no database)'}")
    legacy_names = _legacy_agent_names()
    for name in legacy_names:
        where = detect_legacy(name)
        if where is not None and not (base / name).exists():
            typer.echo(f"  {name}: legacy data at {where} (run: agentkit workspace migrate {name})")


@workspace_app.command("migrate")
def workspace_migrate(
    name: str = typer.Argument(..., help="Agent name, e.g. calliope."),
    root: Path | None = typer.Option(None, help="Workspace root (default: ~/.agentkit)."),
    copy: bool = typer.Option(False, "--copy", help="Copy instead of move."),
) -> None:
    """Move legacy ``~/.local/share/...`` data under the workspace root."""
    from agentkit.errors import Conflict

    try:
        summary = migrate(name, root=root, move=not copy)
    except Conflict as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if not summary["migrated"]:
        typer.echo(f"nothing to migrate for {name} ({summary['reason']})")
        return
    verb = "copied" if summary["mode"] == "copy" else "moved"
    typer.echo(f"{verb} {summary['items']} from {summary['source']} -> {summary['target']}")


def _legacy_agent_names() -> list[str]:
    """Agents still stored in the legacy *shared* home (``~/.local/share/agentkit``).

    Agent-specific legacy homes (``~/.local/share/<name>``) are not enumerated —
    too many unrelated apps live there; migrate those explicitly by name.
    """
    base = Path("~/.local/share/agentkit").expanduser()
    if not base.is_dir():
        return []
    names = {path.stem for path in base.glob("*.db")}
    names.discard("agentkit")
    return sorted(names)


def main() -> None:
    from agentkit.logging import setup_logging

    setup_logging(get_settings())
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
