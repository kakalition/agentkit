"""The global driver registry (contract + driver architecture).

A *kind* is a subsystem (``DriverKind.CACHE``, ``DriverKind.EMBEDDINGS``, …) and
a *driver* is one implementation of that subsystem's contract. Drivers are
registered against a nested ``(kind, name)`` key so kinds never collide::

    from agentkit.support import DriverKind, register_driver
    from agentkit.support.kinds import CacheDriver

    @register_driver(DriverKind.CACHE, CacheDriver.ARRAY)
    class ArrayDriver(Driver):
        def build(self) -> Any:
            app = self.app
            return CacheStore()
Resolution is intentionally global and import-time-safe (mirroring
:mod:`agentkit.model_providers`): registering a driver has no side effects, and
libraries may ship drivers that an application selects purely through settings.

String specs (``"cache:redis"``) are accepted as a convenience and normalise to
the same nested tuple keys.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

__all__ = [
    "Driver",
    "DriverFactory",
    "available",
    "kinds",
    "parse",
    "register",
    "register_driver",
    "registered",
    "resolve",
    "unregister",
]

DriverFactory = Callable[[Any], Any]
"""A driver factory: ``factory(app) -> driver``."""


class Driver:
    """Class-based driver: registered by class, instantiated per app.

        @register_driver(DriverKind.CACHE, CacheDriver.REDIS)
        class RedisCache(Driver):
            kind = DriverKind.CACHE
            name = CacheDriver.REDIS

            def build(self):
                return RedisStore(self.app)
    """

    kind: ClassVar[str] = ""
    name: ClassVar[str] = ""

    def __init__(self, app: Any = None) -> None:
        self.app = app

    def build(self) -> Any:
        raise NotImplementedError

    @classmethod
    def factory(cls) -> DriverFactory:
        def make(app: Any) -> Any:
            return cls(app).build()

        return make

    @classmethod
    def supported(cls) -> bool:
        """Whether this driver can run in the current environment."""
        return True


_REGISTRY: dict[tuple[str, str], DriverFactory] = {}


def _key(kind: Any, name: Any) -> tuple[str, str]:
    return (str(kind).strip().lower(), str(name).strip().lower())


def parse(spec: str | tuple[str, str]) -> tuple[str, str]:
    """Normalise a ``"kind:name"`` string or ``(kind, name)`` pair to a tuple key."""
    if isinstance(spec, tuple):
        return _key(*spec)
    kind, sep, name = str(spec).partition(":")
    if not sep:
        raise ValueError(f"driver spec {spec!r} must be 'kind:name'")
    return _key(kind, name)


def register(kind: str, name: str, driver: Any) -> None:
    """Register (or replace) the :class:`Driver` subclass for ``(kind, name)``."""
    if not (isinstance(driver, type) and issubclass(driver, Driver)):
        raise TypeError(
            f"drivers must be Driver subclasses; got {driver!r}. "
            "Define a class with a build() method and register the class."
        )
    _REGISTRY[_key(kind, name)] = driver.factory()


def register_driver(kind: str, name: str):
    """Decorator form of :func:`register` for a :class:`Driver` subclass.

        @register_driver(DriverKind.CACHE, "redis")
        class RedisCacheDriver(Driver):
            def build(self):
                return RedisCache(self.app.settings.redis_url)
    """

    def decorator(driver: Any) -> Any:
        register(kind, name, driver)
        return driver

    return decorator


def unregister(kind: str, name: str) -> None:
    """Remove a registered driver (mainly for tests and ``extend`` overrides)."""
    _REGISTRY.pop(_key(kind, name), None)


def resolve(kind: str, name: str) -> DriverFactory | None:
    """The factory registered for ``(kind, name)``, or ``None``."""
    return _REGISTRY.get(_key(kind, name))


def available(kind: str) -> list[str]:
    """Sorted driver names registered for ``kind``."""
    key = str(kind).strip().lower()
    return sorted(name for (registered_kind, name) in _REGISTRY if registered_kind == key)


def kinds() -> list[str]:
    """Every kind that has at least one registered driver."""
    return sorted({kind for (kind, _) in _REGISTRY})


def registered() -> dict[str, list[str]]:
    """A ``{kind: [driver, …]}`` snapshot of the registry."""
    return {kind: available(kind) for kind in kinds()}
