"""A tiny service container: bindings, singletons, and resolution."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

Factory = Callable[["Container"], Any]


class BindingError(KeyError):
    """Raised when resolving a name that was never bound."""


class Container:
    """Holds factories and resolved singletons for the app.

    ``bind(name, factory)`` registers a factory (called with the container);
    ``singleton(name, factory)`` caches the first result; ``instance(name, obj)``
    stores an already-built object. ``make(name)`` resolves.
    """

    def __init__(self) -> None:
        self._factories: dict[str, Any] = {}
        self._instances: dict[str, Any] = {}
        self._singletons: set[str] = set()

    def bind(self, name: str, factory: Any, *, singleton: bool = False) -> Container:
        self._factories[name] = factory
        if singleton:
            self._singletons.add(name)
        else:
            self._singletons.discard(name)
            self._instances.pop(name, None)
        return self

    def singleton(self, name: str, factory: Any) -> Container:
        return self.bind(name, factory, singleton=True)

    def instance(self, name: str, obj: Any) -> Any:
        self._instances[name] = obj
        return obj

    def bound(self, name: str) -> bool:
        return name in self._instances or name in self._factories

    def make(self, name: str) -> Any:
        if name in self._instances:
            return self._instances[name]
        if name not in self._factories:
            raise BindingError(name)
        factory = self._factories[name]
        value = factory(self) if callable(factory) else factory
        if name in self._singletons:
            self._instances[name] = value
        return value

    def forget(self, name: str) -> None:
        self._factories.pop(name, None)
        self._instances.pop(name, None)
        self._singletons.discard(name)

    def keys(self) -> list[str]:
        return sorted(set(self._factories) | set(self._instances))


__all__ = ["BindingError", "Container", "Factory"]
