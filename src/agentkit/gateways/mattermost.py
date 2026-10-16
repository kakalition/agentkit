"""Mattermost gateway: deliver messages to an incoming-webhook channel."""

from __future__ import annotations

from typing import Any

from agentkit.gateways.base import Gateway, GatewayError

__all__ = ["MattermostGateway"]


class MattermostGateway(Gateway):
    name = "mattermost"

    def __init__(
        self,
        app: Any = None,
        *,
        settings: Any = None,
        allowed_channel_ids: Any = None,
        webhook_url: str | None = None,
        base_url: str | None = None,
        token: str | None = None,
    ) -> None:
        super().__init__(app, settings=settings, allowed_channel_ids=allowed_channel_ids)
        self.webhook_url = webhook_url or getattr(self.settings, "mattermost_webhook_url", None)
        self.base_url = base_url or getattr(self.settings, "mattermost_base_url", None)
        self.token = token or getattr(self.settings, "mattermost_token", None)

    @staticmethod
    def _channel(conversation_id: str) -> str:
        return conversation_id.split(":", 1)[1] if ":" in conversation_id else conversation_id

    async def send(self, conversation_id: str, text: str) -> None:
        url = self.webhook_url or (
            getattr(self.settings, "mattermost_webhook_url", None) if self.settings else None
        )
        if not url:
            raise GatewayError("the mattermost gateway needs MATTERMOST_WEBHOOK_URL to be set")
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url, json={"text": text, "channel": self._channel(conversation_id)}
            )
        if response.status_code >= 400:
            raise GatewayError(f"mattermost delivery failed with status {response.status_code}")

    async def start(self) -> None:
        # Inbound is delivered by a Mattermost outgoing webhook; nothing to poll.
        return None
