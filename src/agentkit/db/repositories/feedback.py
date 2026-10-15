"""Owner-scoped user feedback (ratings / comments)."""

from __future__ import annotations

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import Feedback


class FeedbackRepo:
    """Owner-scoped user feedback (ratings / comments) on conversations."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def add(
        self,
        *,
        rating: int,
        conversation_id: str = "",
        message_id: int | None = None,
        comment: str = "",
    ) -> Feedback:
        entry = Feedback(
            owner_id=self.owner_id,
            conversation_id=conversation_id,
            message_id=message_id,
            rating=int(rating),
            comment=comment,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list(self, *, conversation_id: str | None = None, limit: int = 50) -> list[Feedback]:
        stmt = select(Feedback).where(Feedback.owner_id == self.owner_id)
        if conversation_id is not None:
            stmt = stmt.where(Feedback.conversation_id == conversation_id)
        stmt = stmt.order_by(Feedback.created_at.desc(), Feedback.id.desc()).limit(limit)
        return list((await self.session.exec(stmt)).all())

    async def count(self, *, conversation_id: str | None = None) -> int:
        stmt = select(func.count()).select_from(Feedback).where(Feedback.owner_id == self.owner_id)
        if conversation_id is not None:
            stmt = stmt.where(Feedback.conversation_id == conversation_id)
        return int((await self.session.exec(stmt)).one())

    async def average(self, *, conversation_id: str | None = None) -> float | None:
        stmt = select(func.avg(Feedback.rating)).where(Feedback.owner_id == self.owner_id)
        if conversation_id is not None:
            stmt = stmt.where(Feedback.conversation_id == conversation_id)
        value = (await self.session.exec(stmt)).one()
        return round(float(value), 4) if value is not None else None


