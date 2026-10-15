"""Ops commands: migrate, database backup/restore, and health."""

from __future__ import annotations

import asyncio
import shutil
import sqlite3
from pathlib import Path

import typer

from agentkit.cli._app import app


def _runtime():
    from agentkit.runtime import build_runtime

    return build_runtime()


@app.command("migrate")
def migrate() -> None:
    """Create missing tables and reconcile schema drift (non-destructive)."""
    from agentkit.db.migrations import init_db

    runtime = _runtime()
    asyncio.run(init_db(runtime.engine))
    typer.echo(f"schema up to date: {runtime.settings.db_path}")


@app.command("db:backup")
def db_backup(
    out: Path | None = typer.Option(None, "--out", help="Destination (default: agent.db.bak)."),
) -> None:
    """Back up a local SQLite database (WAL-safe via ``VACUUM INTO``)."""
    runtime = _runtime()
    db_path = Path(runtime.settings.db_path)
    if not db_path.is_file():
        typer.echo(f"no database at {db_path}", err=True)
        raise typer.Exit(code=1)
    destination = out or db_path.with_suffix(".db.bak")
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("VACUUM INTO ?", (str(destination),))
    except sqlite3.OperationalError as exc:
        typer.echo(f"backup failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    finally:
        connection.close()
    typer.echo(f"backed up to {destination}")


@app.command("db:restore")
def db_restore(
    source: Path = typer.Argument(..., help="The backup file to restore from."),
    yes: bool = typer.Option(False, "--yes", help="Confirm overwriting the current database."),
) -> None:
    """Restore a SQLite database from a backup file (overwrites the current DB)."""
    runtime = _runtime()
    db_path = Path(runtime.settings.db_path)
    if not source.is_file():
        typer.echo(f"no backup at {source}", err=True)
        raise typer.Exit(code=1)
    if not yes:
        typer.echo(f"would overwrite {db_path} with {source}; re-run with --yes")
        raise typer.Exit(code=1)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, db_path)
    typer.echo(f"restored {db_path} from {source}")


@app.command("health")
def health_check() -> None:
    """Run the dependency readiness checks."""
    from agentkit.health import db_check, run_checks

    runtime = _runtime()
    ok, results = asyncio.run(run_checks([db_check(runtime)]))
    for name, passed in results.items():
        typer.echo(f"{name}: {'ok' if passed else 'FAILING'}")
    if not ok:
        raise typer.Exit(code=1)
