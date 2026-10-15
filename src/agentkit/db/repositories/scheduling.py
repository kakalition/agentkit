"""Durable scheduled-job records (cron + one-off)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import ScheduledJob


class ScheduledJobRepo:
    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def upsert(
        self,
        name: str,
        *,
        kind: str,
        schedule: str,
        task: str,
        args: str = "{}",
        enabled: bool = True,
    ) -> ScheduledJob:
        job = await self.session.get(ScheduledJob, name)
        if job is None:
            job = ScheduledJob(name=name, owner_id=self.owner_id)
        job.kind = kind
        job.schedule = schedule
        job.task = task
        job.args = args
        job.enabled = enabled
        job.updated_at = datetime.now(UTC)
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, name: str) -> ScheduledJob | None:
        return await self.session.get(ScheduledJob, name)

    async def list(self, *, enabled_only: bool = False) -> list[ScheduledJob]:
        stmt = select(ScheduledJob)
        if enabled_only:
            stmt = stmt.where(ScheduledJob.enabled == True)  # noqa: E712
        return list((await self.session.exec(stmt.order_by(ScheduledJob.name))).all())

    async def remove(self, name: str) -> bool:
        job = await self.session.get(ScheduledJob, name)
        if job is None:
            return False
        await self.session.delete(job)
        await self.session.flush()
        return True

    async def set_enabled(self, name: str, enabled: bool) -> bool:
        job = await self.session.get(ScheduledJob, name)
        if job is None:
            return False
        job.enabled = enabled
        job.updated_at = datetime.now(UTC)
        self.session.add(job)
        await self.session.flush()
        return True

    async def record_run(self, name: str) -> None:
        job = await self.session.get(ScheduledJob, name)
        if job is None:
            return
        job.last_run = datetime.now(UTC)
        job.run_count += 1
        if job.kind == "once":
            job.enabled = False
        self.session.add(job)
        await self.session.flush()


