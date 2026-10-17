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

#: Annotations the container never fabricates (a scalar/builtin has no service
#: meaning); a parameter typed like these must be supplied or have a default.
_PRIMITIVES = (
    str,
    int,
    float,
    bool,
    bytes,
    bytearray,
    complex,
    list,
    tuple,
    dict,
    set,
    frozenset,
    type(None),
)


def _injectable(annotation: Any) -> bool:
    if annotation is inspect.Parameter.empty or annotation is Any:
        return False
    return annotation not in _PRIMITIVES


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
        self._tags: dict[str, set[Any]] = {}
        self._contextual: dict[Any, dict[Any, Any]] = {}

    def bind(
        self, name: Any, factory: Any, *, singleton: bool = False, tag: str | None = None
    ) -> Container:
        self._factories[name] = factory
        if singleton:
            self._singletons.add(name)
        else:
            self._singletons.discard(name)
            self._instances.pop(name, None)
        if tag is not None:
            self.tag(name, tag)
        return self

    # -- tags -----------------------------------------------------------
    def tag(self, abstracts: Any, tag: str) -> Container:
        """Register one name (or many) under ``tag`` for grouped resolution."""
        names = abstracts if isinstance(abstracts, (list, tuple, set)) else [abstracts]
        bucket = self._tags.setdefault(str(tag), set())
        for name in names:
            bucket.add(name)
        return self

    def tagged(self, tag: str) -> dict[str, Any]:
        """Resolve every name registered under ``tag`` as ``{name: instance}``."""
        return {str(name): self.make(name) for name in self._tags.get(str(tag), set())}

    # -- contextual binding --------------------------------------------
    def when(self, concrete: Any) -> ContextualBindingBuilder:
        """Start a contextual binding: ``when(Client).needs(Connection).give(Redis)``."""
        return ContextualBindingBuilder(self, concrete)

    def _give_contextual(self, concrete: Any, abstract: Any, implementation: Any) -> Container:
        self._contextual.setdefault(concrete, {})[abstract] = implementation
        return self

    def _resolve_contextual(self, implementation: Any) -> Any:
        if isinstance(implementation, type):
            if self.bound(implementation):
                return self.make(implementation)
            return self._autowire(implementation)
        if callable(implementation):
            return implementation(self)
        return implementation

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
            if isinstance(factory, type):
                value = self.build(factory)
            elif callable(factory):
                value = factory(self)
            else:
                value = factory
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
        contextual = self._contextual.get(cls, {})
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
            if annotation in contextual:
                kwargs[parameter_name] = self._resolve_contextual(contextual[annotation])
                continue
            try:
                kwargs[parameter_name] = self.make(annotation)
            except BindingError:
                if parameter.default is inspect.Parameter.empty:
                    raise
        return cls(**kwargs)

    # -- invocation / normalization -------------------------------------
    def call(
        self, target: Any, params: dict[str, Any] | None = None, *args: Any, **kwargs: Any
    ) -> Any:
        """Invoke ``target`` with its typed parameters injected (Laravel's ``call``).

        ``params`` (plus ``**kwargs``) are explicit arguments and always win; the
        remaining typed parameters with no default are resolved from the
        container. Stays synchronous and returns awaitables untouched — callers
        await the result. Never used for tool parameters (PydanticAI owns those).
        """
        handler = target
        if isinstance(target, type):
            handler = self.make(target)
        if not callable(handler):
            method = getattr(handler, "handle", None)
            if not callable(method):
                raise BindingError(f"cannot call {target!r}")
            handler = method
        provided = {**(params or {}), **kwargs}
        injected = self._inject(handler, provided, len(args))
        return handler(*args, **injected)

    def _inject(self, func: Any, provided: dict[str, Any], positional: int) -> dict[str, Any]:
        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):  # pragma: no cover - builtins
            return dict(provided)
        try:
            hints = typing.get_type_hints(func)
        except Exception:  # pragma: no cover - unresolvable annotations
            hints = {}
        owner = type(func.__self__) if inspect.ismethod(func) else None
        contextual = self._contextual.get(owner, {})
        names = [
            name
            for name, parameter in signature.parameters.items()
            if parameter.kind
            in (
                parameter.POSITIONAL_ONLY,
                parameter.POSITIONAL_OR_KEYWORD,
                parameter.KEYWORD_ONLY,
            )
        ]
        bound = set(names[:positional])
        result = dict(provided)
        for name, parameter in signature.parameters.items():
            if name == "self" or parameter.kind in (
                parameter.VAR_POSITIONAL,
                parameter.VAR_KEYWORD,
                parameter.POSITIONAL_ONLY,
            ):
                continue
            if name in bound or name in result:
                continue
            annotation = hints.get(name, parameter.annotation)
            if not _injectable(annotation):
                if parameter.default is inspect.Parameter.empty:
                    raise BindingError(f"cannot inject parameter {name!r}")
                continue
            if annotation in contextual:
                result[name] = self._resolve_contextual(contextual[annotation])
                continue
            try:
                result[name] = self.make(annotation)
            except BindingError:
                if parameter.default is inspect.Parameter.empty:
                    raise
        return result

    def wrap(self, target: Any, *, protocol: str | None = None) -> Any:
        """Normalize a seam target to its protocol callable/instance.

        Accepts a closure, callable, class, instance, or ``"module:attr"`` spec;
        class targets are instantiated (autowired when possible). Returns the
        invocable, or ``None`` for an unresolvable string spec.
        """
        from agentkit.foundation.callable import normalize

        return normalize(target, protocol=protocol, container=self).invocable

    def forget(self, name: Any) -> None:
        self._factories.pop(name, None)
        self._instances.pop(name, None)
        self._singletons.discard(name)

    def keys(self) -> list[str]:
        return sorted(str(k) for k in set(self._factories) | set(self._instances))


class ContextualBindingBuilder:
    """Fluent builder for contextual bindings (``when().needs().give()``)."""

    def __init__(self, container: Container, concrete: Any) -> None:
        self._container = container
        self._concrete = concrete
        self._abstract: Any = None

    def needs(self, abstract: Any) -> ContextualBindingBuilder:
        self._abstract = abstract
        return self

    def give(self, implementation: Any) -> Container:
        if self._abstract is None:
            raise BindingError("needs() must be called before give()")
        return self._container._give_contextual(self._concrete, self._abstract, implementation)


__all__ = ["BindingError", "Container", "ContextualBindingBuilder", "Factory"]

