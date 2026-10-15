"""Memory commands: list, forget, profile, consolidate."""

from __future__ import annotations

import contextlib
import json

import typer

from agentkit.cli._app import app


@contextlib.asynccontextmanager
async def _memory_scope():
    from agentkit.runtime import build_runtime, repositories

    runtime = build_runtime()
    async with repositories(runtime) as repos:
        yield repos


@app.command("memory:list")
def memory_list(
    kind: str | None = typer.Option(None, "--kind", help="Filter by memory kind."),
    limit: int = typer.Option(50, "--limit", help="Maximum rows to show."),
) -> None:
    """List remembered facts (and the owner profile)."""
    import asyncio

    async def _run() -> None:
        async with _memory_scope() as repos:
            profile = await repos.profile.get()
            if profile is not None:
                typer.echo(
                    f"profile: name={profile.name!r} timezone={profile.timezone!r} "
                    f"locale={profile.locale!r} notes={profile.notes!r}"
                )
            rows = await repos.memories.list(limit=limit, kind=kind)
            if not rows:
                typer.echo("(no memories)")
                return
            for row in rows:
                typer.echo(
                    f"  #{row.id} [{row.kind}] {row.content} "
                    f"(importance {row.importance:.2f}, used {row.access_count}x)"
                )

    asyncio.run(_run())


@app.command("memory:forget")
def memory_forget(
    memory_id: int = typer.Argument(..., help="The memory id to delete."),
) -> None:
    """Delete a remembered fact by id."""
    import asyncio

    async def _run() -> bool:
        async with _memory_scope() as repos:
            return await repos.memories.forget(memory_id)

    if asyncio.run(_run()):
        typer.echo(f"forgotten #{memory_id}")
    else:
        typer.echo(f"no memory #{memory_id}", err=True)
        raise typer.Exit(code=1)


@app.command("memory:profile")
def memory_profile() -> None:
    """Show the owner's stored profile."""
    import asyncio

    async def _run() -> str:
        async with _memory_scope() as repos:
            profile = await repos.profile.get()
            if profile is None:
                return "(no profile yet)"
            return json.dumps(
                {
                    "name": profile.name,
                    "timezone": profile.timezone,
                    "locale": profile.locale,
                    "preferences": profile.preferences,
                    "notes": profile.notes,
                },
                indent=2,
            )

    typer.echo(asyncio.run(_run()))


@app.command("memory:consolidate")
def memory_consolidate(
    dry_run: bool = typer.Option(False, "--dry-run", help="Report without changing anything."),
) -> None:
    """Dedupe, summarize, and prune memories (the daily durable task)."""
    import asyncio

    from agentkit.consolidation import consolidate_memories

    async def _run() -> dict[str, int]:
        async with _memory_scope() as repos:
            return await consolidate_memories(repos, dry_run=dry_run)

    summary = asyncio.run(_run())
    prefix = "would " if dry_run else ""
    typer.echo(
        f"{prefix}merge {summary['merged']}, {prefix}summarize {summary['summarized']}, "
        f"{prefix}prune {summary['pruned']}"
    )
