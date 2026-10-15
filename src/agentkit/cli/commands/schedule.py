"""Durable scheduling commands."""

from __future__ import annotations

import asyncio

import typer

from agentkit.cli._app import app
from agentkit.foundation.commands import load_bootstrap


@app.command("schedule:list")
def schedule_list(
    bootstrap: str | None = typer.Option(None, "--bootstrap"),
) -> None:
    """List the booted app's durable scheduled jobs."""

    from agentkit import Schedule

    booted = load_bootstrap(bootstrap)
    booted.boot()
    jobs = asyncio.run(Schedule.list())
    if not jobs:
        typer.echo("(no scheduled jobs)")
        return
    for job in jobs:
        state = "on" if job["enabled"] else "off"
        typer.echo(f"  {job['name']:<20} {job['schedule']:<16} -> {job['task']} [{state}]")


@app.command("schedule:run")
def schedule_run(
    bootstrap: str | None = typer.Option(None, "--bootstrap"),
) -> None:
    """Run any due scheduled jobs right now (catch-up)."""

    from agentkit import Schedule

    booted = load_bootstrap(bootstrap)
    booted.boot()
    ran = asyncio.run(Schedule.run_due())
    typer.echo(f"ran {len(ran)} job(s)" + (f": {', '.join(ran)}" if ran else ""))
