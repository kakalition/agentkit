"""Project scaffolding and ``make:*`` generators."""

from __future__ import annotations

import contextlib
import subprocess
from pathlib import Path

import typer

from agentkit.cli._app import app
from agentkit.foundation.generators import generate


@app.command("new")
def new_project(
    name: str = typer.Argument(..., help="Project name, e.g. my-agent."),
    path: Path = typer.Option(
        Path("."), "--path", help="Parent directory to create the project in."
    ),
    force: bool = typer.Option(False, "--force", help="Write into a non-empty directory."),
    git: bool = typer.Option(True, "--git/--no-git", help="Initialise a git repository."),
    full: bool = typer.Option(
        True, "--full/--minimal", help="Full-stack project (default) or the minimal skeleton."
    ),
) -> None:
    """Create a new agentkit project from the default skeleton."""
    from agentkit.foundation.scaffold import scaffold_project

    try:
        target = scaffold_project(name, path, force=force, full=full)
    except FileExistsError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if git:
        with contextlib.suppress(Exception):
            subprocess.run(["git", "init"], cwd=target, capture_output=True, check=False)
            subprocess.run(["git", "add", "-A"], cwd=target, capture_output=True, check=False)

    typer.echo(f"Created {target}")
    typer.echo("Next steps:")
    typer.echo(f"  cd {target}")
    typer.echo("  cp .env.example .env   # then set OPENAI_API_KEY")
    typer.echo("  uv sync                # or: pip install -e .")
    typer.echo("  agentkit tinker        # chat with your agent")


def _run_generate(kind: str, name: str, path: Path, force: bool) -> None:
    try:
        written = generate(kind, name, directory=path, force=force)
    except FileExistsError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"created {written}")


@app.command("make:agent")
def make_agent(
    name: str = typer.Argument(..., help="Agent name, e.g. notes."),
    path: Path = typer.Option(Path("."), "--path", help="Project directory to write into."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file."),
) -> None:
    """Scaffold an agent builder module."""
    _run_generate("agent", name, path, force)


@app.command("make:provider")
def make_provider(
    name: str = typer.Argument(..., help="Provider name, e.g. notes."),
    path: Path = typer.Option(Path("."), "--path"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Scaffold a service provider."""
    _run_generate("provider", name, path, force)


@app.command("make:tool")
def make_tool(
    name: str = typer.Argument(..., help="Tool name, e.g. add_note."),
    path: Path = typer.Option(Path("."), "--path"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Scaffold a tool function."""
    _run_generate("tool", name, path, force)


@app.command("make:channel")
def make_channel(
    name: str = typer.Argument(..., help="Channel name, e.g. slack."),
    path: Path = typer.Option(Path("."), "--path"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Scaffold a channel factory."""
    _run_generate("channel", name, path, force)


@app.command("make:command")
def make_command(
    name: str = typer.Argument(..., help="Command name, e.g. sync."),
    path: Path = typer.Option(Path("."), "--path"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Scaffold a provider command."""
    _run_generate("command", name, path, force)


@app.command("make:model")
def make_model(
    name: str = typer.Argument(..., help="Model name, e.g. note."),
    path: Path = typer.Option(Path("."), "--path"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Scaffold a ``Model`` table."""
    _run_generate("model", name, path, force)
