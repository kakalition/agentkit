"""A generic webhook channel: POST outbound messages to a configured URL.

Inbound delivery is up to your HTTP layer (point it at ``app.answer``); this
gateway covers the outbound side so a delivery-driven agent can notify a webhook.
"""

from __future__ import annotations

from typing import Any

from agentkit.gateways.base import Gateway, GatewayError

__all__ = ["WebhookGateway"]


class WebhookGateway(Gateway):
    name = "webhook"

    def __init__(
        self,
        app: Any = None,
        *,
        settings: Any = None,
        allowed_channel_ids: Any = None,
        url: str | None = None,
    ) -> None:
        super().__init__(app, settings=settings, allowed_channel_ids=allowed_channel_ids)
        self.url = url or (getattr(self.settings, "webhook_url", None) if self.settings else None)

    async def send(self, conversation_id: str, text: str) -> None:
        url = self.url or (getattr(self.settings, "webhook_url", None) if self.settings else None)
        if not url:
            raise GatewayError("the webhook gateway needs WEBHOOK_URL to be set")
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json={"conversation_id": conversation_id, "text": text})
        if response.status_code >= 400:
            raise GatewayError(f"webhook delivery failed with status {response.status_code}")

    async def start(self) -> None:
        return None
