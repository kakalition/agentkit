"""Owner-scoped gateway DM pairings (``gateway_pairings``).

The durable backing for :class:`agentkit.gateways.pairing.RepositoryPairingRegistry`.
A row starts as a *pending* code (``code``/``code_expires_at``) and becomes
*paired* once ``confirm`` stamps ``paired_at``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import GatewayPairingRecord

__all__ = ["PairingRepo"]


class PairingRepo:
    """Issue, confirm, and inspect pairing codes per ``(scope, external_id)``."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def request(
        self, scope: str, external_id: str, code: str, expires_at: datetime
    ) -> GatewayPairingRecord:
        row = await self._get(scope, external_id)
        if row is None:
            row = GatewayPairingRecord(owner_id=self.owner_id, scope=scope, external_id=external_id)
        row.code = code
        row.code_expires_at = expires_at
        row.paired_at = None
        row.updated_at = datetime.now(UTC)
        self.session.add(row)
        await self.session.flush()
        return row

    async def confirm(self, scope: str, external_id: str, code: str, now: datetime) -> bool:
        row = await self._get(scope, external_id)
        if row is None or not row.code or row.code != code:
            return False
        expires = row.code_expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires is not None and now > expires:
            return False
        row.paired_at = now
        row.code = ""
        row.code_expires_at = None
        row.updated_at = now
        self.session.add(row)
        await self.session.flush()
        return True

    async def is_paired(self, scope: str, external_id: str) -> bool:
        row = await self._get(scope, external_id)
        return row is not None and row.paired_at is not None

    async def unpair(self, scope: str, external_id: str) -> bool:
        row = await self._get(scope, external_id)
        if row is None:
            return False
        paired = row.paired_at is not None
        await self.session.delete(row)
        await self.session.flush()
        return paired

    async def paired(self, scope: str) -> list[str]:
        stmt = (
            select(GatewayPairingRecord)
            .where(
                GatewayPairingRecord.owner_id == self.owner_id,
                GatewayPairingRecord.scope == scope,
                GatewayPairingRecord.paired_at.is_not(None),
            )
            .order_by(GatewayPairingRecord.external_id)
        )
        rows = list((await self.session.exec(stmt)).all())
        return [row.external_id for row in rows]

    async def _get(self, scope: str, external_id: str) -> GatewayPairingRecord | None:
        stmt = select(GatewayPairingRecord).where(
            GatewayPairingRecord.owner_id == self.owner_id,
            GatewayPairingRecord.scope == scope,
            GatewayPairingRecord.external_id == str(external_id),
        )
        return (await self.session.exec(stmt.limit(1))).first()
