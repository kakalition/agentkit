"""A small service container: bindings, singletons, and resolution.

Resolution mirrors Laravel: bindings first, then **autowiring** — resolving a class
name constructs it, injecting its typed dependencies from the container (or
building them recursively).
"""

from __future__ import annotations

import inspect
import typing
from collections.abc import Callable
from typing import Any

Factory = Callable[["Container"], Any]


class BindingError(KeyError):
    """Raised when a name cannot be resolved."""


class Container:
    """Holds factories and resolved singletons for the app.

    ``bind(name, factory)`` registers a factory (called with the container);
    ``singleton(name, factory)`` caches the first result; ``instance(name, obj)``
    stores an already-built object. ``make(name)`` resolves — and autowires a class
    when ``name`` is a type that was not explicitly bound.
    """

    def __init__(self) -> None:
        self._factories: dict[Any, Any] = {}
        self._instances: dict[Any, Any] = {}
        self._singletons: set[Any] = set()

    def bind(self, name: Any, factory: Any, *, singleton: bool = False) -> Container:
        self._factories[name] = factory
        if singleton:
            self._singletons.add(name)
        else:
            self._singletons.discard(name)
            self._instances.pop(name, None)
        return self

    def singleton(self, name: Any, factory: Any) -> Container:
        return self.bind(name, factory, singleton=True)

    def instance(self, name: Any, obj: Any) -> Any:
        self._instances[name] = obj
        return obj

    def bound(self, name: Any) -> bool:
        return name in self._instances or name in self._factories

    def build(self, cls: type) -> Any:
        """Construct a class, injecting its typed dependencies (Laravel's ``build``)."""
        return self._autowire(cls)

    def make(self, name: Any) -> Any:
        if name in self._instances:
            return self._instances[name]
        if name in self._factories:
            factory = self._factories[name]
            value = factory(self) if callable(factory) else factory
            if name in self._singletons:
                self._instances[name] = value
            return value
        if isinstance(name, type):
            return self._autowire(name)
        raise BindingError(name)

    def _autowire(self, cls: type) -> Any:
        try:
            signature = inspect.signature(cls)
        except (TypeError, ValueError):  # pragma: no cover - builtins
            return cls()
        try:
            hints = typing.get_type_hints(cls.__init__)  # type: ignore[misc]
        except Exception:  # pragma: no cover - unresolvable annotations
            hints = {}
        kwargs: dict[str, Any] = {}
        for parameter_name, parameter in signature.parameters.items():
            if parameter_name == "self" or parameter.kind in (
                parameter.VAR_POSITIONAL,
                parameter.VAR_KEYWORD,
            ):
                continue
            annotation = hints.get(parameter_name, parameter.annotation)
            if annotation is inspect.Parameter.empty:
                if parameter.default is inspect.Parameter.empty:
                    raise BindingError(f"cannot autowire {cls.__name__}.{parameter_name}")
                continue
            try:
                kwargs[parameter_name] = self.make(annotation)
            except BindingError:
                if parameter.default is inspect.Parameter.empty:
                    raise
        return cls(**kwargs)

    def forget(self, name: Any) -> None:
        self._factories.pop(name, None)
        self._instances.pop(name, None)
        self._singletons.discard(name)

    def keys(self) -> list[str]:
        return sorted(str(k) for k in set(self._factories) | set(self._instances))


__all__ = ["BindingError", "Container", "Factory"]

