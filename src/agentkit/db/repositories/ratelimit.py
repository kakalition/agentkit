"""Fixed-window rate-limit counters (works on SQLite and Postgres)."""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import RateWindow


class RateWindowRepo:
    """Increment/track per-``(owner, key, window)`` request counters."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def increment(self, key: str, window_start: int, *, owner_id: str | None = None) -> int:
        owner = owner_id or self.owner_id
        row = await self._get(owner, key, window_start)
        if row is None:
            row = RateWindow(owner_id=owner, key=key, window_start=window_start, count=1)
        else:
            row.count += 1
        self.session.add(row)
        await self.session.flush()
        return int(row.count)

    async def count(self, key: str, window_start: int, *, owner_id: str | None = None) -> int:
        row = await self._get(owner_id or self.owner_id, key, window_start)
        return int(row.count) if row is not None else 0

    async def prune(self, before: int) -> int:
        stmt = select(RateWindow).where(RateWindow.window_start < before)
        rows = list((await self.session.exec(stmt)).all())
        for row in rows:
            await self.session.delete(row)
        if rows:
            await self.session.flush()
        return len(rows)

    async def _get(self, owner: str, key: str, window_start: int) -> RateWindow | None:
        stmt = select(RateWindow).where(
            RateWindow.owner_id == owner,
            RateWindow.key == key,
            RateWindow.window_start == window_start,
        )
        return (await self.session.exec(stmt.limit(1))).first()


__all__ = ["RateWindowRepo"]
