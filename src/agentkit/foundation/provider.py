"""Service providers: the ``register`` / ``boot`` lifecycle unit.

A provider binds concerns onto the app (register) and performs side effects
(boot). Importing a provider must be side-effect-free; only ``register`` and
``boot`` may act.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from agentkit.foundation.application import App


class Provider:
    """Base class for application providers."""

    def __init__(self, app: App | None = None) -> None:
        self.app = app

    @property
    def name(self) -> str:
        return type(self).__name__

    def register(self, app: App) -> None:
        """Bind concerns onto the container / registries. Pure; no side effects."""

    def boot(self, app: App) -> None:
        """Perform side effects: register tasks, listeners, warm caches."""

    def commands(self) -> list[Any]:
        """Extra CLI commands contributed by this provider."""
        return []

    def schedules(self) -> list[Any]:
        """Extra schedule definitions contributed by this provider."""
        return []


__all__ = ["Provider"]
