"""Slack gateway (socket mode) over the shared :class:`Gateway` base.

Requires the ``slack`` extra (``slack_bolt``). A channel/thread maps to a
conversation; approvals are delivered as message buttons. Settings:
``slack_bot_token``, ``slack_app_token``, ``slack_allowed_channel_ids``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from agentkit.deps import ApprovalRequest
from agentkit.gateways.base import Gateway, GatewayError

__all__ = ["SlackGateway"]


class SlackGateway(Gateway):
    name = "slack"

    def __init__(
        self,
        app: Any = None,
        *,
        settings: Any = None,
        client: Any = None,
        allowed_channel_ids: Sequence[str] | None = None,
        **kwargs: Any,
    ) -> None:
        settings = settings if settings is not None else getattr(app, "settings", None)
        if allowed_channel_ids is None:
            allowed_channel_ids = getattr(settings, "slack_allowed_channel_ids", []) or []
        super().__init__(
            app, settings=settings, allowed_channel_ids=allowed_channel_ids, **kwargs
        )
        self._client = client

    def client(self) -> Any:
        if self._client is None:
            try:
                from slack_sdk import WebClient
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise GatewayError(
                    "Slack needs the 'slack' extra (pip install agentkit[slack])"
                ) from exc
            token = getattr(self.settings, "slack_bot_token", None)
            if not token:
                raise GatewayError("SLACK_BOT_TOKEN is not set")
            self._client = WebClient(token=token)
        return self._client

    def conversation_id(self, external_id: Any) -> str:
        if isinstance(external_id, (tuple, list)):
            channel = external_id[0] if external_id else ""
            thread = external_id[1] if len(external_id) > 1 else ""
            return f"slack:{channel}:{thread or ''}"
        return super().conversation_id(external_id)

    async def start(self) -> None:
        try:
            from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
            from slack_bolt.app.async_app import AsyncApp
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise GatewayError(
                "Slack needs the 'slack' extra (pip install agentkit[slack])"
            ) from exc
        settings = self.settings
        token = getattr(settings, "slack_bot_token", None)
        app_token = getattr(settings, "slack_app_token", None)
        if not token or not app_token:
            raise GatewayError("SLACK_BOT_TOKEN and SLACK_APP_TOKEN are required")
        bolt = AsyncApp(token=token)
        gateway = self

        @bolt.event("message")
        async def _on_message(event: dict[str, Any], say: Any, **_: Any) -> None:
            if event.get("bot_id") or event.get("subtype"):
                return
            channel = event.get("channel")
            thread = event.get("thread_ts") or event.get("ts") or ""
            if not gateway.is_allowed(channel):
                return
            text = event.get("text") or ""
            result = await gateway.run_turn((channel, thread), text)
            output = getattr(result, "output", None) or "(no reply)"
            await say(output, thread_ts=thread or None)

        @bolt.action("agentkit_approve")
        async def _approve(ack: Any, body: Any, action: Any) -> None:
            await ack()
            gateway.resolve_approval(str(action.get("value")), True)

        @bolt.action("agentkit_deny")
        async def _deny(ack: Any, body: Any, action: Any) -> None:
            await ack()
            gateway.resolve_approval(str(action.get("value")), False)

        handler = AsyncSocketModeHandler(bolt, app_token)
        await handler.start_async()

    async def send(self, conversation_id: str, text: str) -> None:
        _, _, rest = conversation_id.partition(":")
        channel, _, thread = rest.partition(":")
        payload: dict[str, Any] = {"channel": channel, "text": text}
        if thread:
            payload["thread_ts"] = thread
        await asyncio.to_thread(lambda: self.client().chat_postMessage(**payload))

    async def prompt_approval(self, external_id: Any, request: ApprovalRequest) -> None:
        _, _, rest = self.conversation_id(external_id).partition(":")
        channel, _, thread = rest.partition(":")
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"Approve `{request.tool_name}`?\n{request.args}"}},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "style": "primary",
                        "action_id": "agentkit_approve",
                        "value": request.tool_call_id,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Deny"},
                        "style": "danger",
                        "action_id": "agentkit_deny",
                        "value": request.tool_call_id,
                    },
                ],
            },
        ]
        payload: dict[str, Any] = {"channel": channel, "blocks": blocks, "text": "approval needed"}
        if thread:
            payload["thread_ts"] = thread
        await asyncio.to_thread(lambda: self.client().chat_postMessage(**payload))
