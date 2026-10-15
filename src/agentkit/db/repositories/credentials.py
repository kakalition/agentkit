"""Owner-scoped encrypted credentials (ciphertext only — never plaintext)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import Credential


class CredentialRepo:
    """Store ciphertext + metadata keyed by ``(owner_id, name)``."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def set(
        self, name: str, *, ciphertext: str, kind: str = "secret", metadata: str = "{}"
    ) -> Credential:
        row = await self.get(name)
        if row is None:
            row = Credential(
                owner_id=self.owner_id,
                name=name,
                kind=kind,
                ciphertext=ciphertext,
                extra=metadata,
            )
        else:
            row.kind = kind
            row.ciphertext = ciphertext
            row.extra = metadata
            row.updated_at = datetime.now(UTC)
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, name: str) -> Credential | None:
        stmt = select(Credential).where(
            Credential.owner_id == self.owner_id, Credential.name == name
        )
        return (await self.session.exec(stmt.limit(1))).first()

    async def list(self) -> list[Credential]:
        stmt = select(Credential).where(Credential.owner_id == self.owner_id).order_by(
            Credential.name
        )
        return list((await self.session.exec(stmt)).all())

    async def delete(self, name: str) -> bool:
        row = await self.get(name)
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True


__all__ = ["CredentialRepo"]
