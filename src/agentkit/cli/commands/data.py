"""Owner data lifecycle commands: export a bundle and (opt-in) forget data."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import typer

from agentkit.cli._app import app


@contextlib.asynccontextmanager
async def _data_scope(owner_id: str | None):
    from agentkit.runtime import build_runtime, repositories

    runtime = build_runtime()
    async with repositories(runtime, owner_id) as repos:
        yield repos


@app.command("data:export")
def data_export(
    owner: str | None = typer.Option(None, "--owner", help="Owner id (default: settings owner)."),
    out: Path | None = typer.Option(None, "--out", help="Write the JSON bundle to a file."),
) -> None:
    """Export an owner's data as a JSON bundle."""
    import asyncio

    from agentkit.data import export_owner

    async def _run() -> dict:
        async with _data_scope(owner) as repos:
            return await export_owner(repos)

    bundle = asyncio.run(_run())
    text = json.dumps(bundle, indent=2, default=str)
    if out is not None:
        out.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {out}")
    else:
        typer.echo(text)


@app.command("data:forget")
def data_forget(
    owner: str | None = typer.Option(None, "--owner", help="Owner id (default: settings owner)."),
    yes: bool = typer.Option(False, "--yes", help="Actually erase (default: dry run)."),
) -> None:
    """Erase an owner's data (audit entries are kept as tombstones)."""
    import asyncio

    from agentkit.data import forget_owner

    async def _run() -> dict:
        async with _data_scope(owner) as repos:
            return await forget_owner(repos, dry_run=not yes)

    result = asyncio.run(_run())
    key = "would_delete" if result.get("dry_run") else "deleted"
    typer.echo(f"{'would delete' if result.get('dry_run') else 'deleted'}: {json.dumps(result[key])}")
    if result.get("dry_run"):
        typer.echo("re-run with --yes to erase")
