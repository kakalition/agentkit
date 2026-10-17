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

import inspect
from dataclasses import dataclass
from typing import Any, ClassVar

from agentkit.contracts.channels import NotificationChannel
from agentkit.foundation.events import ShouldQueue
from agentkit.foundation.queue import Job
from agentkit.logging import get_logger
from agentkit.support import Driver, register_driver
from agentkit.support.kinds import DriverKind, NotificationChannelDriver
from agentkit.support.manager import Manager

__all__ = [
    "ConversationNotificationChannel",
    "LogNotificationChannel",
    "Notification",
    "NotificationChannel",
    "NotificationChannelManager",
    "Notifier",
    "QueuedNotificationJob",
    "SentNotification",
    "TelegramNotificationChannel",
]

_log = get_logger("agentkit.notifications")


@dataclass
class SentNotification:
    notification: Notification
    channel: str
    detail: str = ""


class Notification:
    """Base class for a notification.

    Mix in :class:`~agentkit.ShouldQueue` to deliver through the durable queue.
    """

    channels: ClassVar[tuple[str, ...]] = ("log",)
    conversation_id: str | None = None
    data: dict[str, Any] = {}
    queue: ClassVar[str | None] = None
    delay: ClassVar[float | None] = None

    def content(self) -> str:
        """The notification's body. Override this (or the ``to_*`` methods)."""
        raise NotImplementedError

    def to_log(self) -> str:
        return self.content()

    def to_conversation(self) -> str:
        return self.content()

    def to_telegram(self) -> str:
        return self.content()

    def to_slack(self) -> str:
        return self.content()

    def to_email(self) -> str:
        return self.content()

    def to_discord(self) -> str:
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
        _queued: bool = False,
    ) -> list[SentNotification]:
        conversation_id = conversation_id or getattr(notification, "conversation_id", None)
        if (
            not _queued
            and isinstance(notification, ShouldQueue)
            and self.app is not None
            and self._enqueue(notification, to=to, conversation_id=conversation_id)
        ):
            return []
        channels = _as_list(to) or list(notification.channels)
        sent: list[SentNotification] = []
        for channel in channels:
            sender = self._channels.get(channel)
            if sender is None:
                _log.warning("no notifier channel %r; skipping", channel)
                continue
            detail = sender(notification, conversation_id=conversation_id) or ""
            sent.append(SentNotification(notification, channel, str(detail)))
        return sent

    def _enqueue(
        self,
        notification: Notification,
        *,
        to: str | list[str] | None,
        conversation_id: str | None,
    ) -> bool:
        from agentkit._sync import run_sync

        queue = getattr(self.app, "queue", None)
        if queue is None:
            return False
        job = QueuedNotificationJob(
            notification_path=f"{type(notification).__module__}:{type(notification).__qualname__}",
            kwargs=_notification_kwargs(notification),
            channels=_as_list(to) or list(notification.channels),
            conversation_id=conversation_id,
        )
        try:
            run_sync(queue.push(job))
        except Exception:  # pragma: no cover - fall back to inline
            _log.exception("could not queue notification %r", type(notification).__name__)
            return False
        return True

    # -- built-in channels ---------------------------------------------
    @staticmethod
    def _send_log(notification: Notification, *, conversation_id: str | None = None) -> str:
        text = notification.to_log()
        _log.info("%s", text)
        return text

    def _send_conversation(self, notification: Notification, *, conversation_id: str | None) -> str:
        if not conversation_id:
            return ""
        from agentkit._sync import run_sync
        from agentkit.session import serialize_message

        text = notification.to_conversation()

        async def _write() -> None:
            async with self.app.repositories() as repos:
                await repos.conversations.get_or_create(conversation_id)
                await repos.messages.append(
                    conversation_id, [serialize_message(_assistant_message(text))]
                )

        # ``send`` stays sync (listeners are sync), but the write goes through the
        # async data layer off the caller's loop.
        run_sync(_write())
        return text

    def _send_telegram(self, notification: Notification, *, conversation_id: str | None) -> str:
        # Real Telegram delivery is plugged in with
        # ``app.notifier.channel("telegram", sender)``; without a sender we log.
        _log.debug("telegram channel not configured; logging instead")
        return self._send_log(notification, conversation_id=conversation_id)


def _assistant_message(text: str) -> Any:
    from pydantic_ai.messages import ModelResponse, TextPart

    return ModelResponse(parts=[TextPart(text)])


def _notification_kwargs(notification: Notification) -> dict[str, Any]:
    signature = inspect.signature(type(notification).__init__)
    kwargs: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if name == "self" or parameter.kind in (
            parameter.VAR_POSITIONAL,
            parameter.VAR_KEYWORD,
        ):
            continue
        if hasattr(notification, name):
            kwargs[name] = getattr(notification, name)
    return kwargs


class QueuedNotificationJob(Job):
    """Rebuild a ``ShouldQueue`` notification on the worker and deliver it."""

    queue: str = "default"

    def __init__(
        self,
        notification_path: str = "",
        kwargs: dict[str, Any] | None = None,
        channels: list[str] | None = None,
        conversation_id: str | None = None,
    ) -> None:
        self.notification_path = notification_path
        self.kwargs = dict(kwargs or {})
        self.channels = list(channels or [])
        self.conversation_id = conversation_id

    def handle(self, app: Any) -> Any:
        import importlib

        module_name, _, qualname = self.notification_path.partition(":")
        target: Any = importlib.import_module(module_name)
        for part in qualname.split("."):
            target = getattr(target, part)
        notification = target(**self.kwargs)
        return app.notifier.send(
            notification,
            to=self.channels or None,
            conversation_id=self.conversation_id,
            _queued=True,
        )


def _as_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


# ---------------------------------------------------------------------------
# Notification-channel drivers
# ---------------------------------------------------------------------------


class LogNotificationChannel:
    """Write the notification to the structured log."""

    def __init__(self, notifier: Notifier | None = None) -> None:
        self.notifier = notifier

    def send(self, notification: Notification, *, conversation_id: str | None = None) -> str:
        return Notifier._send_log(notification, conversation_id=conversation_id)


class ConversationNotificationChannel:
    """Append the notification into the conversation history (web UI visible)."""

    def __init__(self, notifier: Notifier) -> None:
        self.notifier = notifier

    def send(self, notification: Notification, *, conversation_id: str | None = None) -> str:
        return self.notifier._send_conversation(notification, conversation_id=conversation_id)


class TelegramNotificationChannel:
    """Deliver to a plugged-in Telegram sender, else log."""

    def __init__(self, notifier: Notifier) -> None:
        self.notifier = notifier

    def send(self, notification: Notification, *, conversation_id: str | None = None) -> str:
        return self.notifier._send_telegram(notification, conversation_id=conversation_id)


class NotificationChannelManager(Manager):
    """Resolves the configured notification channel (``notification_channel_driver``, default ``log``)."""

    kind = DriverKind.NOTIFICATION_CHANNEL
    default_driver = NotificationChannelDriver.LOG


@register_driver(DriverKind.NOTIFICATION_CHANNEL, NotificationChannelDriver.LOG)
class LogNotificationChannelDriver(Driver):
    def build(self) -> LogNotificationChannel:
        return LogNotificationChannel(getattr(self.app, "notifier", None))


@register_driver(DriverKind.NOTIFICATION_CHANNEL, NotificationChannelDriver.CONVERSATION)
class ConversationNotificationChannelDriver(Driver):
    def build(self) -> ConversationNotificationChannel:
        return ConversationNotificationChannel(self.app.notifier)


@register_driver(DriverKind.NOTIFICATION_CHANNEL, NotificationChannelDriver.TELEGRAM)
class TelegramNotificationChannelDriver(Driver):
    def build(self) -> TelegramNotificationChannel:
        return TelegramNotificationChannel(self.app.notifier)
