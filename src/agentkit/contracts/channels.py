"""Channel contracts — chat transports and notification channels."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["Channel", "NotificationChannel"]


@runtime_checkable
class Channel(Protocol):
    """A chat transport (a gateway): deliver text to a conversation."""

    name: str

    async def send(self, conversation_id: str, text: str) -> None: ...

    def service(self) -> Any: ...


@runtime_checkable
class NotificationChannel(Protocol):
    """Deliver a notification over one channel, returning a detail string."""

    def send(self, notification: Any, *, conversation_id: str | None = None) -> str: ...
