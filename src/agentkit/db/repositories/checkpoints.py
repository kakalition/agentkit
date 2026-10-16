"""Owner-scoped run checkpoints (``checkpoints``)."""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import CheckpointRecord


class CheckpointRepo:
    """CRUD over run checkpoints (one row per ``(run_id, seq)``)."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def add(
        self, run_id: str, seq: int, state: Any, *, label: str = ""
    ) -> CheckpointRecord:
        payload = state if isinstance(state, str) else json.dumps(state, default=str)
        record = CheckpointRecord(
            owner_id=self.owner_id,
            run_id=run_id,
            seq=int(seq),
            label=label,
            state=payload,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get(self, run_id: str, seq: int) -> CheckpointRecord | None:
        stmt = select(CheckpointRecord).where(
            CheckpointRecord.owner_id == self.owner_id,
            CheckpointRecord.run_id == run_id,
            CheckpointRecord.seq == seq,
        )
        return (await self.session.exec(stmt)).first()

    async def list(self, run_id: str) -> list[CheckpointRecord]:
        stmt = (
            select(CheckpointRecord)
            .where(CheckpointRecord.owner_id == self.owner_id, CheckpointRecord.run_id == run_id)
            .order_by(CheckpointRecord.seq)  # type: ignore[attr-defined]
        )
        return list((await self.session.exec(stmt)).all())

    async def latest(self, run_id: str) -> CheckpointRecord | None:
        rows = await self.list(run_id)
        return rows[-1] if rows else None

    async def prune(self, run_id: str, keep: int) -> int:
        rows = await self.list(run_id)
        excess = rows[: max(0, len(rows) - keep)]
        for record in excess:
            await self.session.delete(record)
        await self.session.flush()
        return len(excess)

    async def remove(self, run_id: str) -> int:
        rows = await self.list(run_id)
        for record in rows:
            await self.session.delete(record)
        await self.session.flush()
        return len(rows)
