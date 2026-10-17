"""The :class:`Manager` base — one manager per subsystem (kind).

A manager resolves the *configured* driver for its kind, caches it as a
singleton, and lets applications register replacements::

    app.extend(DriverKind.CACHE, "pantry", lambda app: MyCache())

Selection is settings-driven: a manager reads ``<kind>_driver`` from the app's
settings (e.g. ``cache_driver``), falling back to its ``default_driver``. Drivers
are provided either by the manager itself (``create_<name>_driver`` methods, the
core/default drivers) or by the global registry in
:mod:`agentkit.support.drivers` (optional extras and user ``extend`` calls).

Adding a driver::

    from agentkit.support import DriverKind, Manager, register_driver
    from agentkit.support.kinds import CacheDriver

    @register_driver(DriverKind.CACHE, CacheDriver.REDIS)
    class RedisDriver(Driver):
        def build(self) -> Any:
            app = self.app
            return RedisCache(app.settings.redis_url)

        class CacheManager(Manager):
            kind = DriverKind.CACHE
            default_driver = CacheDriver.ARRAY

            def create_array_driver(self, app):
                return CacheStore()
"""

from __future__ import annotations

from typing import Any, ClassVar

from agentkit.errors import ConfigurationError
from agentkit.support import drivers
from agentkit.support.kinds import DriverKind

__all__ = ["Manager", "manager_class", "registered_managers"]


class Manager:
    """Base class resolving a settings-selected driver for one subsystem kind."""

    kind: ClassVar[DriverKind | str] = ""
    default_driver: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.kind:
            _MANAGERS[cls.kind] = cls

    def __init__(self, app: Any) -> None:
        self.app = app
        self._drivers: dict[str, Any] = {}
        self._overrides: dict[str, drivers.DriverFactory] = {}

    # -- selection ------------------------------------------------------
    @property
    def setting_name(self) -> str:
        return f"{self.kind}_driver"

    def configured_driver(self, name: str | None = None) -> str:
        """The explicit ``name``, the ``<kind>_driver`` setting, or the default."""
        if name:
            return str(name).strip()
        settings = getattr(self.app, "settings", None)
        configured = getattr(settings, self.setting_name, None) if settings is not None else None
        if configured:
            return str(configured).strip()
        return self.default_driver

    def driver(self, name: str | None = None) -> Any:
        """Resolve (and cache) the configured or named driver singleton."""
        resolved = self.configured_driver(name)
        if resolved not in self._drivers:
            self._drivers[resolved] = self.create(resolved)
        return self._drivers[resolved]

    # -- creation -------------------------------------------------------
    def create(self, name: str) -> Any:
        """Build the driver ``name`` — an ``extend`` override, a registered factory, or a ``create_*`` method."""
        override = self._overrides.get(name)
        if override is not None:
            return override(self.app)
        factory = drivers.resolve(self.kind, name)
        if factory is not None:
            return factory(self.app)
        method = getattr(self, f"create_{name}_driver", None)
        if method is None:
            raise ConfigurationError(
                f"unknown {self.kind} driver {name!r}; "
                f"available: {', '.join(self.available()) or '(none)'}"
            )
        return method(self.app)

    def extend(self, name: str, factory: drivers.DriverFactory) -> Manager:
        """Register a custom driver for this app only (Laravel's ``Cache::extend``).

        An ``extend`` override is scoped to this manager instance and takes
        precedence over registered and built-in drivers; libraries that ship
        global drivers use :func:`agentkit.support.register_driver` instead.
        """
        self._overrides[str(name)] = factory
        self._drivers.pop(str(name), None)
        return self

    # -- introspection --------------------------------------------------
    def available(self) -> list[str]:
        """Sorted driver names: overrides, registered factories, ``create_<name>_driver`` methods."""
        names = set(self._overrides) | set(drivers.available(self.kind))
        prefix, suffix = "create_", "_driver"
        for attribute in dir(self):
            if attribute.startswith(prefix) and attribute.endswith(suffix):
                names.add(attribute[len(prefix) : -len(suffix)])
        return sorted(names)

    def forget(self, name: str | None = None) -> None:
        """Drop cached driver instances (one, or all)."""
        if name is None:
            self._drivers.clear()
        else:
            self._drivers.pop(name, None)


_MANAGERS: dict[str, type[Manager]] = {}


def manager_class(kind: str) -> type[Manager]:
    """The manager class registered for ``kind`` (falls back to the base ``Manager``)."""
    return _MANAGERS.get(str(kind).strip().lower(), Manager)


def registered_managers() -> dict[str, type[Manager]]:
    """The ``{kind: manager class}`` registry snapshot."""
    return dict(_MANAGERS)
