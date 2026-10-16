"""Declarative team definitions authored in the Studio (name + JSON spec)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import TeamDefinitionRecord


class TeamSpecRepo:
    """Owner-scoped CRUD over :class:`~agentkit.db.models.TeamDefinitionRecord`."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def upsert(
        self, name: str, *, kind: str = "groupchat", definition: str = "{}"
    ) -> TeamDefinitionRecord:
        record = await self.session.get(TeamDefinitionRecord, name)
        if record is None:
            record = TeamDefinitionRecord(name=name, owner_id=self.owner_id)
        record.kind = kind
        record.definition = definition
        record.updated_at = datetime.now(UTC)
        self.session.add(record)
        await self.session.flush()
        return record

    async def get(self, name: str) -> TeamDefinitionRecord | None:
        return await self.session.get(TeamDefinitionRecord, name)

    async def list(self) -> list[TeamDefinitionRecord]:
        stmt = (
            select(TeamDefinitionRecord)
            .where(TeamDefinitionRecord.owner_id == self.owner_id)
            .order_by(TeamDefinitionRecord.name)
        )
        return list((await self.session.exec(stmt)).all())

    async def remove(self, name: str) -> bool:
        record = await self.session.get(TeamDefinitionRecord, name)
        if record is None:
            return False
        await self.session.delete(record)
        await self.session.flush()
        return True
