"""Run evaluation suites."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import typer

from agentkit.cli._app import app
from agentkit.foundation.commands import load_bootstrap


@contextlib.asynccontextmanager
async def _eval_scope():
    from agentkit.runtime import build_runtime, repositories

    runtime = build_runtime()
    async with repositories(runtime) as repos:
        yield repos


@app.command("eval")
def eval_command(
    path: Path = typer.Argument(..., help="Eval suite file (.json/.yaml)."),
    bootstrap: str | None = typer.Option(None, "--bootstrap", help="module:attr of the app."),
) -> None:
    """Run an evaluation suite against the booted app."""

    from agentkit import EvalSuite

    suite = EvalSuite.from_file(path)
    booted = load_bootstrap(bootstrap)
    booted.boot()
    report = asyncio.run(suite.run(booted))
    typer.echo(report.summary())
    if not report.passed:
        raise typer.Exit(code=1)


@app.command("eval:capture")
def eval_capture(
    conversation: str | None = typer.Option(None, "--conversation", help="Conversation id."),
    limit: int = typer.Option(50, "--limit", help="Maximum pairs to capture."),
) -> None:
    """Capture eval cases from a conversation's real turns (input → reply)."""
    from agentkit.evals import capture_turns

    async def _run() -> list[dict]:
        async with _eval_scope() as repos:
            return await capture_turns(repos, conversation_id=conversation, limit=limit)

    captured = asyncio.run(_run())
    if not captured:
        typer.echo("nothing to capture")
        return
    typer.echo(f"captured {len(captured)} case(s)")


@app.command("eval:gate")
def eval_gate(
    conversation: str | None = typer.Option(None, "--conversation", help="Conversation id."),
    bootstrap: str | None = typer.Option(None, "--bootstrap", help="module:attr of the app."),
) -> None:
    """Run captured cases against the booted app; non-zero exit on failure."""
    from agentkit.evals import load_captured

    async def _load():
        async with _eval_scope() as repos:
            return await load_captured(repos, conversation_id=conversation, name="captured")

    suite = asyncio.run(_load())
    if not suite.cases:
        typer.echo("no captured cases")
        return
    booted = load_bootstrap(bootstrap)
    booted.boot()
    report = asyncio.run(suite.run(booted))
    typer.echo(report.summary())
    if not report.passed:
        raise typer.Exit(code=1)
