"""Service — a base class for domain services.

Laravel services are plain classes; agentkit's base wires the app in and gives you
the settings, repositories, container, and notifications for free::

    from agentkit.foundation.service import Service

    class ReminderService(Service):
        async def upcoming(self, conversation_id: str) -> list:
            async with self.repositories as repos:
                return await repos.reminders.list()
"""

from __future__ import annotations

from typing import Any

__all__ = ["Service"]


class Service:
    """Base class for an application service."""

    def __init__(self, app: Any = None) -> None:
        self.app = app

    def boot(self) -> None:
        """Optional hook called after construction/boot."""

    @property
    def settings(self) -> Any:
        return self.app.settings

    @property
    def repositories(self) -> Any:
        """The app's async repository scope (``async with self.repositories as repos:``)."""
        return self.app.repositories()

    def resolve(self, name: str) -> Any:
        """Resolve a binding from the container."""
        return self.app.make(name)

    def notify(self, notification: Any, **kwargs: Any) -> Any:
        return self.app.notify(notification, **kwargs)

    def schedule(self, task: str, **kwargs: Any) -> Any:
        return self.app.schedule(task, **kwargs)

    def current_app(self) -> Any:
        return self.app
