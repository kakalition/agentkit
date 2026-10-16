"""Owner-scoped run-trace events (``run_events``)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import RunEventRecord


class RunEventRepo:
    """Append + read run-trace events keyed by ``run_id``."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def add_many(self, run_id: str, events: list[dict[str, Any]]) -> None:
        for event in events:
            self.session.add(
                RunEventRecord(
                    owner_id=self.owner_id,
                    run_id=run_id or str(event.get("run_id", "")),
                    seq=int(event.get("seq", 0) or 0),
                    kind=str(event.get("kind", "")),
                    data=json.dumps(event, default=str),
                )
            )
        await self.session.flush()

    async def events(self, run_id: str, *, limit: int | None = None) -> list[RunEventRecord]:
        stmt = (
            select(RunEventRecord)
            .where(RunEventRecord.owner_id == self.owner_id, RunEventRecord.run_id == run_id)
            .order_by(RunEventRecord.seq)  # type: ignore[attr-defined]
        )
        if limit:
            stmt = stmt.limit(limit)
        return list((await self.session.exec(stmt)).all())

    async def list_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        newest = func.max(RunEventRecord.created_at)
        stmt = (
            select(
                RunEventRecord.run_id,
                func.count(RunEventRecord.id),
                func.min(RunEventRecord.created_at),
                newest,
            )
            .where(RunEventRecord.owner_id == self.owner_id)
            .group_by(RunEventRecord.run_id)
            .order_by(newest.desc())  # type: ignore[attr-defined]
            .limit(limit)
        )
        rows = (await self.session.exec(stmt)).all()
        return [
            {
                "run_id": row[0],
                "events": int(row[1] or 0),
                "started_at": _iso(row[2]),
                "updated_at": _iso(row[3]),
            }
            for row in rows
        ]

    async def remove(self, run_id: str) -> int:
        rows = await self.events(run_id)
        for record in rows:
            await self.session.delete(record)
        await self.session.flush()
        return len(rows)


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None
