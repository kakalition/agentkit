"""Queue commands: work, failed, retry, flush (class-based)."""

from __future__ import annotations

import asyncio

import typer

from agentkit.foundation import Command
from agentkit.foundation.commands import load_bootstrap


class QueueWorkCommand(Command):
    signature = "queue:work {--bootstrap=} {--queue=} {--once} {--sleep=2.0} {--max-jobs=0}"
    description = "Process queued jobs (requires ``QUEUE_ENABLED=true``)."

    async def handle(
        self,
        bootstrap: str | None = None,
        queue: str | None = None,
        once: bool = False,
        sleep: float = 2.0,
        max_jobs: int = 0,
    ) -> None:
        booted = load_bootstrap(bootstrap)
        booted.boot()
        if not getattr(booted.settings, "queue_enabled", False):
            self.error("queue is disabled; set QUEUE_ENABLED=true to enable it")
            raise typer.Exit(code=1)

        processed = 0
        while True:
            ran = await booted.queue.run_once(queue)
            if ran:
                processed += 1
                if max_jobs and processed >= max_jobs:
                    break
            elif once:
                break
            else:
                await asyncio.sleep(sleep)
        self.info(f"processed {processed} job(s)")


class QueueFailedCommand(Command):
    signature = "queue:failed {--bootstrap=}"
    description = "List failed jobs."

    async def handle(self, bootstrap: str | None = None) -> None:
        booted = load_bootstrap(bootstrap)
        booted.boot()
        rows = await booted.queue.failed()
        if not rows:
            self.info("(no failed jobs)")
            return
        for row in rows:
            self.info(f"  #{row.id} {row.queue} {row.job} (attempts {row.attempts}): {row.error}")


class QueueRetryCommand(Command):
    signature = "queue:retry {job_id} {--bootstrap=}"
    description = "Requeue a failed job."

    async def handle(self, job_id: int, bootstrap: str | None = None) -> None:
        booted = load_bootstrap(bootstrap)
        booted.boot()
        if await booted.queue.retry(job_id):
            self.info(f"requeued job #{job_id}")
        else:
            self.error(f"no failed job #{job_id}")
            raise typer.Exit(code=1)


class QueueFlushCommand(Command):
    signature = "queue:flush {--bootstrap=}"
    description = "Delete all failed jobs."

    async def handle(self, bootstrap: str | None = None) -> None:
        booted = load_bootstrap(bootstrap)
        booted.boot()
        self.info(f"flushed {await booted.queue.flush()} failed job(s)")


COMMANDS: list[type] = [
    QueueWorkCommand,
    QueueFailedCommand,
    QueueRetryCommand,
    QueueFlushCommand,
]
