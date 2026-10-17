"""At-least-once spooled inter-agent messages (``mailbox_messages``).

The repository is owner-scoped and ordered by insertion; it is the durable backing
for :class:`agentkit.agents.mailbox.RepositoryMailboxSpool`.
"""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import MailboxMessageRecord

__all__ = ["MailboxMessageRepo"]


class MailboxMessageRepo:
    """Append, peek, and drain spooled messages for a recipient."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def append(self, to: str, message: str, sender: str | None = None) -> int | None:
        row = MailboxMessageRecord(
            owner_id=self.owner_id, recipient=to, sender=sender, message=message
        )
        self.session.add(row)
        await self.session.flush()
        return row.id

    async def drain(self, to: str) -> list[str]:
        """Return and delete every spooled message for ``to`` (select-ordered)."""
        rows = list(
            (
                await self.session.exec(
                    select(MailboxMessageRecord)
                    .where(
                        MailboxMessageRecord.owner_id == self.owner_id,
                        MailboxMessageRecord.recipient == to,
                    )
                    .order_by(MailboxMessageRecord.id)
                )
            ).all()
        )
        for row in rows:
            await self.session.delete(row)
        if rows:
            await self.session.flush()
        return [row.message for row in rows]

    async def peek(self, to: str) -> list[str]:
        """Return the spooled (undrained) messages for ``to``."""
        rows = list(
            (
                await self.session.exec(
                    select(MailboxMessageRecord)
                    .where(
                        MailboxMessageRecord.owner_id == self.owner_id,
                        MailboxMessageRecord.recipient == to,
                    )
                    .order_by(MailboxMessageRecord.id)
                )
            ).all()
        )
        return [row.message for row in rows]

    async def count(self, to: str) -> int:
        rows = await self.peek(to)
        return len(rows)
