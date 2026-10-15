"""Owner-scoped webhook subscriptions and their delivery log."""

from __future__ import annotations

import json

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import Webhook, WebhookDelivery


class WebhookRepo:
    """Register, list, and remove outbound webhook subscriptions."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def add(
        self, url: str, *, events: list[str] | None = None, secret: str = "", enabled: bool = True
    ) -> Webhook:
        row = Webhook(
            owner_id=self.owner_id,
            url=url,
            events=json.dumps(list(events or ["*"])),
            secret=secret,
            enabled=enabled,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list(self, *, enabled_only: bool = False) -> list[Webhook]:
        stmt = select(Webhook).where(Webhook.owner_id == self.owner_id)
        if enabled_only:
            stmt = stmt.where(Webhook.enabled == True)  # noqa: E712
        stmt = stmt.order_by(Webhook.id)
        return list((await self.session.exec(stmt)).all())

    async def get(self, webhook_id: int) -> Webhook | None:
        row = await self.session.get(Webhook, webhook_id)
        if row is not None and row.owner_id != self.owner_id:
            return None
        return row

    async def delete(self, webhook_id: int) -> bool:
        row = await self.get(webhook_id)
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    @staticmethod
    def events_of(row: Webhook) -> list[str]:
        try:
            value = json.loads(row.events or "[]")
        except json.JSONDecodeError:
            return ["*"]
        return [str(item) for item in value] if isinstance(value, list) else ["*"]


class WebhookDeliveryRepo:
    """Append-only log of webhook delivery attempts."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def record(
        self,
        *,
        webhook_id: int | None,
        event: str,
        payload: str,
        status: str,
        attempts: int = 1,
        error: str = "",
    ) -> WebhookDelivery:
        row = WebhookDelivery(
            webhook_id=webhook_id,
            event=event,
            payload=payload,
            status=status,
            attempts=attempts,
            error=error,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list(self, *, webhook_id: int | None = None, limit: int = 100) -> list[WebhookDelivery]:
        stmt = select(WebhookDelivery)
        if webhook_id is not None:
            stmt = stmt.where(WebhookDelivery.webhook_id == webhook_id)
        stmt = stmt.order_by(WebhookDelivery.id.desc()).limit(limit)
        return list((await self.session.exec(stmt)).all())


__all__ = ["WebhookDeliveryRepo", "WebhookRepo"]
