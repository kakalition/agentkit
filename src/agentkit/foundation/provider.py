"""Service providers: the ``register`` / ``boot`` lifecycle unit.

A provider binds concerns onto the app (register) and performs side effects
(boot). Importing a provider must be side-effect-free; only ``register`` and
``boot`` may act.

Declare simple container bindings with the ``bindings``/``singletons`` maps, and
defer a provider that only registers bindings by implementing ``provides()``
(Laravel's deferred providers)::

    class RiakProvider(DeferrableProvider):
        def register(self, app):
            app.singleton(Connection, lambda c: Connection(c.make("config").riak))
        def provides(self):
            return [Connection]
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:  # pragma: no cover
    from agentkit.foundation.application import App


class Provider:
    """Base class for application providers."""

    # abstract => concrete (a class or a factory)
    bindings: ClassVar[dict[Any, Any]] = {}
    singletons: ClassVar[dict[Any, Any]] = {}

    def __init__(self, app: App | None = None) -> None:
        self.app = app

    @property
    def name(self) -> str:
        return type(self).__name__

    def register(self, app: App) -> None:
        """Bind concerns onto the container / registries. Pure; no side effects."""

    def boot(self, app: App) -> None:
        """Perform side effects: register tasks, listeners, warm caches."""

    def provides(self) -> list[Any]:
        """Service names this provider binds (defer loading until one is needed)."""
        return []

    def commands(self) -> list[Any]:
        """Extra CLI commands contributed by this provider."""
        return []

    def schedules(self) -> list[Any]:
        """Extra schedule definitions contributed by this provider."""
        return []


class DeferrableProvider(Provider):
    """A provider that only binds services; loaded on first use of a provided name.

    Override :meth:`provides` to list the names it binds.
    """

    def provides(self) -> list[Any]:
        raise NotImplementedError


__all__ = ["DeferrableProvider", "Provider"]

