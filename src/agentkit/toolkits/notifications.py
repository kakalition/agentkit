"""Native notification toolkit: send notifications over channels.

The ``conversation`` channel writes into the current chat history (so it shows up
in the web UI); other channels go through the app's :class:`Notifier`, whose
senders are operator-registered.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import RunContext

from agentkit.deps import Deps
from agentkit.foundation.notifications import Notification
from agentkit.logging import get_logger
from agentkit.toolkits._common import app_of, emit_event, repos_of

__all__ = ["_attach_notifications"]

log = get_logger("agentkit.notifications")


class _TextNotification(Notification):
    def __init__(self, text: str) -> None:
        self.text = text

    def content(self) -> str:
        return self.text


async def _deliver(ctx: RunContext[Deps], text: str, channels: list[str]) -> list[str]:
    from agentkit.session import serialize_message

    repos = repos_of(ctx)
    app = app_of(ctx)
    conversation_id = ctx.deps.conversation_id
    delivered: list[str] = []
    for channel in channels:
        if channel == "conversation":
            if repos is None:
                continue
            await repos.conversations.get_or_create(conversation_id)
            await repos.messages.append(
                conversation_id, [serialize_message(_assistant_message(text))]
            )
            delivered.append("conversation")
        elif channel == "log":
            log.info("%s", text)
            delivered.append("log")
        else:
            sender = app.notifier.channel(channel) if app is not None else None
            if sender is None:
                continue
            try:
                sender(_TextNotification(text), conversation_id=conversation_id)
                delivered.append(channel)
            except Exception:  # pragma: no cover - a bad sender must not break the turn
                log.exception("notification channel %s failed", channel)
    return delivered


def _assistant_message(text: str) -> Any:
    from pydantic_ai.messages import ModelResponse, TextPart

    return ModelResponse(parts=[TextPart(text)])


def _attach_notifications(agent: Any, *, flag: str = "notification_tools_enabled") -> Any:
    """Register the notification tools on a built PydanticAI agent (idempotent)."""
    if getattr(agent, "_agentkit_notifications_attached", False):
        return agent

    @agent.tool(requires_approval=True)
    async def notify(ctx: RunContext[Deps], text: str, channels: list[str] | None = None) -> str:
        """Send a notification over one or more channels (requires approval).

        Args:
            text: The notification body.
            channels: Channels to use (default ["conversation"]).
        """
        chosen = channels or ["conversation"]
        delivered = await _deliver(ctx, text, chosen)
        await emit_event("notify.sent", channels=delivered)
        return f"notified via {', '.join(delivered)}" if delivered else "(no channel delivered)"

    @agent.tool
    async def notify_me(ctx: RunContext[Deps], text: str) -> str:
        """Post a note into the current conversation.

        Args:
            text: The note body.
        """
        delivered = await _deliver(ctx, text, ["conversation"])
        return "noted" if delivered else "(conversation unavailable)"

    agent._agentkit_notifications_attached = True  # type: ignore[attr-defined]
    return agent
