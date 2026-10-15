"""Self-learning commands: reflect, list lessons, forget a lesson."""

from __future__ import annotations

import contextlib
import json

import typer

from agentkit.cli._app import app


@contextlib.asynccontextmanager
async def _learning_scope():
    from agentkit.runtime import build_runtime, repositories

    runtime = build_runtime()
    async with repositories(runtime) as repos:
        yield repos


@app.command("learning:reflect")
def learning_reflect(
    conversation: str | None = typer.Option(None, "--conversation", help="Conversation id (default: most recent)."),
    window: int = typer.Option(20, "--window", help="How many recent messages to review."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report without changing anything."),
) -> None:
    """Distil lessons/preferences/facts from a conversation (the durable task)."""
    import asyncio

    from agentkit.learning import reflect

    async def _run() -> dict:
        async with _learning_scope() as repos:
            return await reflect(
                repos, conversation_id=conversation, window=window, dry_run=dry_run
            )

    summary = asyncio.run(_run())
    if summary.get("skipped"):
        typer.echo("nothing new to reflect on (already processed)")
        return
    prefix = "would learn " if dry_run else "learned "
    typer.echo(
        f"{prefix}{summary['lessons']} lesson(s), {summary['preferences']} preference(s), "
        f"{summary['facts']} fact(s); merged {summary['merged']}"
    )
    if summary.get("skill_candidates"):
        typer.echo(f"skill candidates: {json.dumps(summary['skill_candidates'], default=str)}")


@app.command("learning:lessons")
def learning_lessons(
    limit: int = typer.Option(50, "--limit", help="Maximum lessons to show."),
    status: str = typer.Option("active", "--status", help="active | proposed | rejected | all."),
) -> None:
    """List the lessons the agent has learned."""
    import asyncio

    wanted = None if status == "all" else status

    async def _run() -> list[str]:
        async with _learning_scope() as repos:
            rows = await repos.memories.list(limit=limit, kind="procedural", status=wanted)
            rows.sort(key=lambda row: float(row.importance or 0.0), reverse=True)
            return [f"#{row.id} [{row.status}] {row.content}" for row in rows]

    lines = asyncio.run(_run())
    if not lines:
        typer.echo("(no lessons)")
        return
    for line in lines:
        typer.echo(line)


@app.command("learning:review")
def learning_review(
    action: str = typer.Argument(..., help="approve | reject."),
    lesson_id: int = typer.Argument(..., help="The proposed lesson id."),
) -> None:
    """Approve or reject a proposed lesson (see ``learning:lessons --status proposed``)."""
    import asyncio

    from agentkit.learning import approve_lesson, reject_lesson

    normalised = action.strip().lower()
    if normalised not in {"approve", "reject"}:
        typer.echo("action must be 'approve' or 'reject'", err=True)
        raise typer.Exit(code=2)

    async def _run() -> bool:
        async with _learning_scope() as repos:
            if normalised == "approve":
                return await approve_lesson(repos, lesson_id)
            return await reject_lesson(repos, lesson_id)

    if asyncio.run(_run()):
        typer.echo(f"{normalised}d #{lesson_id}")
    else:
        typer.echo(f"no lesson #{lesson_id}", err=True)
        raise typer.Exit(code=1)


@app.command("learning:forget")
def learning_forget(
    lesson_id: int = typer.Argument(..., help="The lesson id to delete."),
) -> None:
    """Delete a learned lesson by id."""
    import asyncio

    async def _run() -> bool:
        async with _learning_scope() as repos:
            return await repos.memories.forget(lesson_id)

    if asyncio.run(_run()):
        typer.echo(f"forgotten #{lesson_id}")
    else:
        typer.echo(f"no lesson #{lesson_id}", err=True)
        raise typer.Exit(code=1)
