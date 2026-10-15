"""Discord gateway over ``discord.py``.

Guild channels and DMs map to conversations; approvals are collected with
reaction buttons. Requires the ``discord`` extra. Settings:
``discord_bot_token``, ``discord_allowed_guild_ids``.
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from typing import Any

from agentkit.deps import ApprovalRequest
from agentkit.gateways.base import Gateway, GatewayError

__all__ = ["DiscordGateway"]

APPROVE_EMOJI = "✅"
DENY_EMOJI = "❌"


class DiscordGateway(Gateway):
    name = "discord"

    def __init__(
        self,
        app: Any = None,
        *,
        settings: Any = None,
        client: Any = None,
        allowed_guild_ids: Sequence[int] | None = None,
        **kwargs: Any,
    ) -> None:
        settings = settings if settings is not None else getattr(app, "settings", None)
        if allowed_guild_ids is None:
            allowed_guild_ids = getattr(settings, "discord_allowed_guild_ids", []) or []
        super().__init__(
            app, settings=settings, allowed_channel_ids=allowed_guild_ids, **kwargs
        )
        self._client = client
        self._channels: dict[str, Any] = {}
        self._approval_messages: dict[str, str] = {}

    async def start(self) -> None:
        try:
            import discord
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise GatewayError(
                "Discord needs the 'discord' extra (pip install agentkit[discord])"
            ) from exc
        token = getattr(self.settings, "discord_bot_token", None)
        if not token:
            raise GatewayError("DISCORD_BOT_TOKEN is not set")
        if self._client is None:
            intents = discord.Intents.default()
            intents.message_content = True
            self._client = discord.Client(intents=intents)
        client = self._client
        gateway = self

        @client.event
        async def on_message(message: Any) -> None:
            if getattr(message.author, "bot", False):
                return
            guild = getattr(getattr(message, "guild", None), "id", None)
            if guild is not None and gateway.allowed and guild not in gateway.allowed:
                return
            channel_id = message.channel.id
            gateway._channels[str(channel_id)] = message.channel
            result = await gateway.run_turn(channel_id, message.content or "")
            output = getattr(result, "output", None) or "(no reply)"
            await message.channel.send(output)

        @client.event
        async def on_raw_reaction_add(payload: Any) -> None:
            emoji = str(getattr(payload, "emoji", ""))
            if emoji not in {APPROVE_EMOJI, DENY_EMOJI}:
                return
            tool_call_id = gateway._approval_messages.pop(str(payload.message_id), None)
            if tool_call_id is None:
                return
            gateway.resolve_approval(tool_call_id, emoji == APPROVE_EMOJI)

        await client.start(token)

    async def send(self, conversation_id: str, text: str) -> None:
        channel = self._channels.get(conversation_id)
        if channel is None:
            channel_id = conversation_id.split(":", 1)[1]
            callback = getattr(self._client, "get_channel", None)
            channel = callback(int(channel_id)) if callback else None
        if channel is None:
            raise GatewayError(f"unknown Discord conversation {conversation_id!r}")
        await channel.send(text)

    async def prompt_approval(self, external_id: Any, request: ApprovalRequest) -> None:
        channel = self._channels.get(self.conversation_id(external_id))
        if channel is None:
            await super().prompt_approval(external_id, request)
            return
        message = await channel.send(f"Approve `{request.tool_name}`?\n{request.args}")
        self._approval_messages[str(getattr(message, "id", ""))] = request.tool_call_id
        for emoji in (APPROVE_EMOJI, DENY_EMOJI):
            with contextlib.suppress(Exception):
                await message.add_reaction(emoji)
