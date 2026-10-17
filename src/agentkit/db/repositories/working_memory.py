"""Thread-scoped working memory (owner + conversation namespaced key/value)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import WorkingMemoryRecord

__all__ = ["WorkingMemoryRepo"]


class WorkingMemoryRepo:
    """Per-``(owner, namespace)`` key/value entries with overwrite semantics."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def set(self, namespace: str, key: str, value: Any) -> WorkingMemoryRecord:
        row = await self._get(namespace, key)
        if row is None:
            row = WorkingMemoryRecord(
                owner_id=self.owner_id, namespace=namespace, key=key, value=str(value)
            )
        else:
            row.value = str(value)
            row.updated_at = datetime.now(UTC)
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, namespace: str, key: str) -> str | None:
        row = await self._get(namespace, key)
        return row.value if row is not None else None

    async def list(self, namespace: str) -> dict[str, str]:
        stmt = select(WorkingMemoryRecord).where(
            WorkingMemoryRecord.owner_id == self.owner_id,
            WorkingMemoryRecord.namespace == namespace,
        )
        rows = list((await self.session.exec(stmt)).all())
        return {row.key: row.value for row in rows}

    async def forget(self, namespace: str, key: str) -> bool:
        row = await self._get(namespace, key)
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    async def clear(self, namespace: str) -> int:
        rows = list(
            (
                await self.session.exec(
                    select(WorkingMemoryRecord).where(
                        WorkingMemoryRecord.owner_id == self.owner_id,
                        WorkingMemoryRecord.namespace == namespace,
                    )
                )
            ).all()
        )
        for row in rows:
            await self.session.delete(row)
        if rows:
            await self.session.flush()
        return len(rows)

    async def _get(self, namespace: str, key: str) -> WorkingMemoryRecord | None:
        stmt = select(WorkingMemoryRecord).where(
            WorkingMemoryRecord.owner_id == self.owner_id,
            WorkingMemoryRecord.namespace == namespace,
            WorkingMemoryRecord.key == key,
        )
        return (await self.session.exec(stmt.limit(1))).first()
