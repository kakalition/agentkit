"""Notifications — Laravel-style messages delivered over channels.

Define a notification and send it to one or more channels::

    from agentkit import Notification

    class ReminderDue(Notification):
        channels = ("conversation",)

        def __init__(self, text: str) -> None:
            self.text = text

        def to_conversation(self) -> str:
            return f"⏰ Reminder: {self.text}"

    app.notify(ReminderDue("stretch"), conversation_id="cli:1")

Built-in channels: ``log`` (structured log), ``conversation`` (writes into the
chat history so it appears in the web UI), and ``telegram`` (plug in a sender with
``app.notifier.channel("telegram", sender)``). Register your own channels the same
way.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from agentkit.logging import get_logger

__all__ = ["Notification", "Notifier", "SentNotification"]

_log = get_logger("agentkit.notifications")


@dataclass
class SentNotification:
    notification: Notification
    channel: str
    detail: str = ""


class Notification:
    """Base class for a notification."""

    channels: ClassVar[tuple[str, ...]] = ("log",)
    conversation_id: str | None = None
    data: dict[str, Any] = {}

    def content(self) -> str:
        """The notification's body. Override this (or the ``to_*`` methods)."""
        raise NotImplementedError

    def to_log(self) -> str:
        return self.content()

    def to_conversation(self) -> str:
        return self.content()

    def to_telegram(self) -> str:
        return self.content()


class Notifier:
    """Resolves channels and sends notifications."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self._channels: dict[str, Any] = {
            "log": self._send_log,
            "conversation": self._send_conversation,
            "telegram": self._send_telegram,
        }

    # -- registry -------------------------------------------------------
    def channel(self, name: str, sender: Any | None = None) -> Any:
        if sender is None:
            return self._channels.get(name)
        self._channels[name] = sender
        return sender

    # -- send -----------------------------------------------------------
    def send(
        self,
        notification: Notification,
        *,
        to: str | list[str] | None = None,
        conversation_id: str | None = None,
    ) -> list[SentNotification]:
        channels = _as_list(to) or list(notification.channels)
        conversation_id = conversation_id or getattr(notification, "conversation_id", None)
        sent: list[SentNotification] = []
        for channel in channels:
            sender = self._channels.get(channel)
            if sender is None:
                _log.warning("no notifier channel %r; skipping", channel)
                continue
            detail = sender(notification, conversation_id=conversation_id) or ""
            sent.append(SentNotification(notification, channel, str(detail)))
        return sent

    # -- built-in channels ---------------------------------------------
    @staticmethod
    def _send_log(notification: Notification, *, conversation_id: str | None = None) -> str:
        text = notification.to_log()
        _log.info("%s", text)
        return text

    def _send_conversation(self, notification: Notification, *, conversation_id: str | None) -> str:
        if not conversation_id:
            return ""
        from agentkit.session import serialize_message

        text = notification.to_conversation()
        with self.app.repositories() as repos:
            repos.conversations.get_or_create(conversation_id)
            repos.messages.append(
                conversation_id, [serialize_message(_assistant_message(text))]
            )
        return text

    def _send_telegram(self, notification: Notification, *, conversation_id: str | None) -> str:
        # Real Telegram delivery is plugged in with
        # ``app.notifier.channel("telegram", sender)``; without a sender we log.
        _log.debug("telegram channel not configured; logging instead")
        return self._send_log(notification, conversation_id=conversation_id)


def _assistant_message(text: str) -> Any:
    from pydantic_ai.messages import ModelResponse, TextPart

    return ModelResponse(parts=[TextPart(text)])


def _as_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)
