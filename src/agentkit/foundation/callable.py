"""Shared normalization for class/functional duality (Laravel's boundary layer).

Laravel never removes closures; it normalizes *both* forms to one internal
abstraction at each boundary. The same idea here: a seam accepts a closure,
a callable, a class, an instance, or a ``"module:attr"`` string spec and
:func:`normalize` resolves it to the protocol callable/instance the seam needs.

    from agentkit.foundation.callable import normalize, invoke

    normalize(AuditListener)                 # -> Resolved(instance=AuditListener())
    normalize(lambda ev: ...)                # -> Resolved(callable=<fn>)
    normalize("myapp.listeners:Audit")       # -> lazy import, then as above

This module is deliberately dependency-light. The tree forbids ``foundation.*``
imports at module level from ``db/repositories/*`` (a cycle), so the current app
and container are resolved lazily and string specs are imported on demand. A bad
spec is logged and skipped, never fatal — mirroring ``discover_providers``.
"""

from __future__ import annotations

import functools
import importlib
import inspect
from dataclasses import dataclass
from typing import Any

from agentkit.logging import get_logger

log = get_logger("agentkit.callable")

__all__ = ["Resolved", "invoke", "normalize"]

#: Per protocol, the instance method that becomes the seam's callable when the
#: instance itself is not callable (a ``Listener``/``Middleware`` instance is
#: callable, so it is used as-is and its markers survive).
_PROTOCOL_METHODS: dict[str, tuple[str, ...]] = {
    "listener": ("handle", "__call__"),
    "channel": ("handle",),
    "command": ("handle",),
    "middleware": ("handle", "__call__"),
    "job": ("handle",),
}


@dataclass
class Resolved:
    """The normalized form of a seam target.

    ``callable`` is the invocable (a function, or a callable/bound-method derived
    from an instance); ``instance`` is the resolved object when the target was a
    class/instance; ``origin`` is one of ``closure`` | ``class`` | ``instance`` |
    ``string`` (or ``unresolved`` for a bad spec).
    """

    target: Any
    callable: Any = None
    instance: Any = None
    origin: str = "instance"

    @property
    def invocable(self) -> Any:
        """The callable (or, for class-shaped seams, the instance)."""
        return self.callable if self.callable is not None else self.instance


def _is_function(target: Any) -> bool:
    return (
        inspect.isfunction(target)
        or inspect.ismethod(target)
        or inspect.isbuiltin(target)
        or isinstance(target, functools.partial)
    )


def _resolve_instance(
    instance: Any, target: Any, protocol: str | None, origin: str
) -> Resolved:
    call: Any = instance if callable(instance) else None
    if call is None and protocol:
        for name in _PROTOCOL_METHODS.get(protocol, ()):
            method = getattr(instance, name, None)
            if callable(method):
                call = method
                break
    return Resolved(target=target, callable=call, instance=instance, origin=origin)


def _container(app: Any = None) -> Any:
    """The container to autowire ``__init__`` from (lazy; may be ``None``)."""
    if app is None:
        from agentkit.foundation.facade import get_current_app

        app = get_current_app()
    return getattr(app, "container", None) if app is not None else None


def _instantiate(cls: type, container: Any, app: Any, protocol: str | None) -> Any:
    if container is None:
        container = _container(app)
    if container is not None:
        try:
            return container.build(cls)
        except Exception:  # noqa: BLE001 - fall back to a plain constructor
            log.debug("autowire of %r failed; falling back to %s()", cls, cls.__name__)
    return cls()


def _from_string(
    spec: str, protocol: str | None, container: Any, app: Any
) -> Resolved | None:
    module_name, sep, attr = spec.partition(":")
    if not sep:
        log.warning("callable spec %r is not 'module:attr'; skipping", spec)
        return None
    try:
        target: Any = importlib.import_module(module_name)
        for part in attr.split("."):
            target = getattr(target, part)
    except Exception:  # noqa: BLE001 - never fatal
        log.exception("could not import callable spec %r", spec)
        return None
    resolved = normalize(target, protocol=protocol, container=container, app=app)
    return Resolved(
        target=spec,
        callable=resolved.callable,
        instance=resolved.instance,
        origin="string",
    )


def normalize(
    target: Any,
    *,
    protocol: str | None = None,
    container: Any = None,
    app: Any = None,
) -> Resolved:
    """Resolve a closure | callable | class | instance | ``"module:attr"`` spec.

    ``protocol`` names the seam (``listener``/``channel``/``command``/
    ``middleware``/``job``) and selects the instance method that becomes the
    callable when the resolved object is not itself callable. Classes are
    instantiated with container autowiring, falling back to a plain constructor.
    """
    if isinstance(target, Resolved):
        return target
    if isinstance(target, str):
        resolved = _from_string(target, protocol, container, app)
        if resolved is None:
            return Resolved(target=target, origin="unresolved")
        return resolved
    if isinstance(target, type):
        instance = _instantiate(target, container, app, protocol)
        return _resolve_instance(instance, target, protocol, "class")
    if _is_function(target):
        return Resolved(target=target, callable=target, instance=None, origin="closure")
    return _resolve_instance(target, target, protocol, "instance")


def invoke(
    target: Any,
    *args: Any,
    protocol: str | None = None,
    container: Any = None,
    framework_params: bool = False,
    **kwargs: Any,
) -> Any:
    """Normalize ``target`` and call it (container-injecting when asked).

    ``Container.call`` stays synchronous and returns awaitables untouched, so a
    caller that awaits the result still works.
    """
    resolved = normalize(target, protocol=protocol, container=container)
    func = resolved.invocable
    if func is None:
        raise TypeError(f"{target!r} is not invocable")
    if framework_params:
        container = container if container is not None else _container()
        if container is not None:
            return container.call(func, None, *args, **kwargs)
    return func(*args, **kwargs)
