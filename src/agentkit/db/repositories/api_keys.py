"""Owner-scoped API keys (hashed) for opt-in authentication."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import APIKey


def _decode_roles(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return [str(role) for role in value] if isinstance(value, list) else []


class APIKeyRepo:
    """Create/list/revoke API keys and resolve a presented hash to its row."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def create(
        self,
        *,
        name: str,
        key_hash: str,
        prefix: str = "",
        roles: list[str] | tuple[str, ...] = (),
        owner_id: str | None = None,
    ) -> APIKey:
        row = APIKey(
            owner_id=owner_id or self.owner_id,
            name=name,
            key_hash=key_hash,
            prefix=prefix,
            roles=json.dumps(list(roles)),
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list(
        self, *, owner_id: str | None = None, include_revoked: bool = False
    ) -> list[APIKey]:
        stmt = select(APIKey).where(APIKey.owner_id == (owner_id or self.owner_id))
        if not include_revoked:
            stmt = stmt.where(APIKey.revoked_at.is_(None))  # type: ignore[union-attr]
        stmt = stmt.order_by(APIKey.id.desc())
        return list((await self.session.exec(stmt)).all())

    async def get(self, ident: int | str, *, owner_id: str | None = None) -> APIKey | None:
        """Fetch by numeric id or by name (owner-scoped)."""
        stmt = select(APIKey).where(APIKey.owner_id == (owner_id or self.owner_id))
        if str(ident).isdigit():
            stmt = stmt.where(APIKey.id == int(ident))
        else:
            stmt = stmt.where(APIKey.name == str(ident))
        return (await self.session.exec(stmt.limit(1))).first()

    async def revoke(self, ident: int | str, *, owner_id: str | None = None) -> bool:
        row = await self.get(ident, owner_id=owner_id)
        if row is None or row.revoked_at is not None:
            return False
        row.revoked_at = datetime.now(UTC)
        self.session.add(row)
        await self.session.flush()
        return True

    async def resolve(self, key_hash: str) -> APIKey | None:
        """Global (owner-agnostic) lookup of an active key by its hash."""
        stmt = select(APIKey).where(APIKey.key_hash == key_hash).limit(1)
        return (await self.session.exec(stmt)).first()

    async def touch(self, key_id: int) -> None:
        row = await self.session.get(APIKey, key_id)
        if row is not None:
            row.last_used_at = datetime.now(UTC)
            self.session.add(row)
            await self.session.flush()


__all__ = ["APIKeyRepo"]
