"""Captured eval cases distilled from real conversation turns."""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import EvalCapture


class EvalCaptureRepo:
    """Owner-scoped storage for eval cases captured from live turns."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def add(self, conversation_id: str, case: str) -> EvalCapture:
        row = EvalCapture(owner_id=self.owner_id, conversation_id=conversation_id, case=case)
        self.session.add(row)
        await self.session.flush()
        return row

    async def list(self, *, conversation_id: str | None = None, limit: int = 200) -> list[EvalCapture]:
        stmt = select(EvalCapture).where(EvalCapture.owner_id == self.owner_id)
        if conversation_id is not None:
            stmt = stmt.where(EvalCapture.conversation_id == conversation_id)
        stmt = stmt.order_by(EvalCapture.id).limit(limit)
        return list((await self.session.exec(stmt)).all())

    async def clear(self, *, conversation_id: str | None = None) -> int:
        rows = await self.list(conversation_id=conversation_id, limit=100_000)
        for row in rows:
            await self.session.delete(row)
        if rows:
            await self.session.flush()
        return len(rows)


__all__ = ["EvalCaptureRepo"]
