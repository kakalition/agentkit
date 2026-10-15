"""Learning-run records: idempotency + evidence for the reflect loop."""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import LearningRun


class LearningRunRepo:
    """Owner-scoped records of reflection runs (keyed by conversation + window)."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def latest(self, conversation_id: str) -> LearningRun | None:
        stmt = (
            select(LearningRun)
            .where(
                LearningRun.owner_id == self.owner_id,
                LearningRun.conversation_id == conversation_id,
            )
            .order_by(LearningRun.id.desc())  # type: ignore[arg-type]
            .limit(1)
        )
        return (await self.session.exec(stmt)).first()

    async def seen(self, conversation_id: str, signature: str) -> bool:
        stmt = (
            select(LearningRun)
            .where(
                LearningRun.owner_id == self.owner_id,
                LearningRun.conversation_id == conversation_id,
                LearningRun.signature == signature,
            )
            .limit(1)
        )
        return (await self.session.exec(stmt)).first() is not None

    async def record(
        self,
        conversation_id: str,
        *,
        signature: str,
        lessons: int = 0,
        preferences: int = 0,
        facts: int = 0,
        detail: str = "{}",
    ) -> LearningRun:
        run = LearningRun(
            owner_id=self.owner_id,
            conversation_id=conversation_id,
            signature=signature,
            lessons=lessons,
            preferences=preferences,
            facts=facts,
            detail=detail,
        )
        self.session.add(run)
        await self.session.flush()
        return run


__all__ = ["LearningRunRepo"]
