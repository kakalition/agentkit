"""Queue commands: work, failed, retry, flush."""

from __future__ import annotations

import typer

from agentkit.cli._app import app
from agentkit.foundation.commands import load_bootstrap


@app.command("queue:work")
def queue_work(
    bootstrap: str | None = typer.Option(None, "--bootstrap"),
    queue: str | None = typer.Option(None, "--queue", help="Queue name (default: settings)."),
    once: bool = typer.Option(False, "--once", help="Process what's available, then exit."),
    sleep: float = typer.Option(2.0, "--sleep", help="Seconds to wait when the queue is empty."),
    max_jobs: int = typer.Option(0, "--max-jobs", help="Stop after N jobs (0 = unlimited)."),
) -> None:
    """Process queued jobs (requires ``QUEUE_ENABLED=true``)."""
    import asyncio

    booted = load_bootstrap(bootstrap)
    booted.boot()
    if not getattr(booted.settings, "queue_enabled", False):
        typer.echo("queue is disabled; set QUEUE_ENABLED=true to enable it", err=True)
        raise typer.Exit(code=1)

    async def drain() -> int:
        processed = 0
        while True:
            ran = await booted.queue.run_once(queue)
            if ran:
                processed += 1
                if max_jobs and processed >= max_jobs:
                    return processed
            elif once:
                return processed
            else:
                await asyncio.sleep(sleep)

    processed = asyncio.run(drain())
    typer.echo(f"processed {processed} job(s)")


@app.command("queue:failed")
def queue_failed(
    bootstrap: str | None = typer.Option(None, "--bootstrap"),
) -> None:
    """List failed jobs."""
    import asyncio

    booted = load_bootstrap(bootstrap)
    booted.boot()
    rows = asyncio.run(booted.queue.failed())
    if not rows:
        typer.echo("(no failed jobs)")
        return
    for row in rows:
        typer.echo(f"  #{row.id} {row.queue} {row.job} (attempts {row.attempts}): {row.error}")


@app.command("queue:retry")
def queue_retry(
    job_id: int = typer.Argument(..., help="The failed job id."),
    bootstrap: str | None = typer.Option(None, "--bootstrap"),
) -> None:
    """Requeue a failed job."""
    import asyncio

    booted = load_bootstrap(bootstrap)
    booted.boot()
    if asyncio.run(booted.queue.retry(job_id)):
        typer.echo(f"requeued job #{job_id}")
    else:
        typer.echo(f"no failed job #{job_id}", err=True)
        raise typer.Exit(code=1)


@app.command("queue:flush")
def queue_flush(
    bootstrap: str | None = typer.Option(None, "--bootstrap"),
) -> None:
    """Delete all failed jobs."""
    import asyncio

    booted = load_bootstrap(bootstrap)
    booted.boot()
    typer.echo(f"flushed {asyncio.run(booted.queue.flush())} failed job(s)")
