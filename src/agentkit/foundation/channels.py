"""Class-based channels: a transport that turns inbound messages into turns.

A :class:`Channel` is the class form of a channel factory (``factory(app) ->
Service | list[Service]``)::

    class SlackChannel(Channel):
        name = "slack"
        def handle(self):
            async def run(service): ...   # long-poll / listen
            return Service(name="slack", run=run)

Both the class form (under ``app/Channels/``) and the legacy ``*_channel``
function form are discovered and registered.
"""

from __future__ import annotations

from typing import Any, ClassVar

__all__ = ["Channel"]


class Channel:
    """Base class for a channel; returns one or more supervised services."""

    name: ClassVar[str] = ""

    def __init__(self, app: Any = None) -> None:
        self.app = app

    def channel_name(self) -> str:
        return self.name or type(self).__name__.replace("Channel", "").lower()

    def handle(self) -> Any:
        """Return a :class:`~agentkit.supervise.Service` or list of services."""
        raise NotImplementedError

    def services(self, app: Any = None) -> Any:
        if app is not None:
            self.app = app
        return self.handle()
