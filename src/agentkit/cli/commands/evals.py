"""Run evaluation suites."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from agentkit.cli._app import app
from agentkit.foundation.commands import load_bootstrap


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
