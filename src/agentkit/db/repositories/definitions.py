"""Owner-scoped CRUD over unified definitions (the spec store backing table)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import DefinitionRecord


class DefinitionRepo:
    """CRUD over :class:`~agentkit.db.models.DefinitionRecord` by ``(kind, name)``."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def get(self, kind: str, name: str) -> DefinitionRecord | None:
        stmt = select(DefinitionRecord).where(
            DefinitionRecord.owner_id == self.owner_id,
            DefinitionRecord.kind == kind,
            DefinitionRecord.name == name,
        )
        return (await self.session.exec(stmt)).first()

    async def upsert(
        self, kind: str, name: str, *, spec: str = "{}", version: int = 1
    ) -> DefinitionRecord:
        record = await self.get(kind, name)
        if record is None:
            record = DefinitionRecord(owner_id=self.owner_id, kind=kind, name=name)
        record.spec = spec
        record.version = version
        record.updated_at = datetime.now(UTC)
        self.session.add(record)
        await self.session.flush()
        return record

    async def list(self, kind: str | None = None) -> list[DefinitionRecord]:
        stmt = select(DefinitionRecord).where(DefinitionRecord.owner_id == self.owner_id)
        if kind:
            stmt = stmt.where(DefinitionRecord.kind == kind)
        stmt = stmt.order_by(DefinitionRecord.kind, DefinitionRecord.name)  # type: ignore[attr-defined]
        return list((await self.session.exec(stmt)).all())

    async def remove(self, kind: str, name: str) -> bool:
        record = await self.get(kind, name)
        if record is None:
            return False
        await self.session.delete(record)
        await self.session.flush()
        return True
