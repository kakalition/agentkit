"""Current-application resolution for the Laravel-style facades.

A facade (``Memory``, ``Schedule``, ``DB`` …) is a class whose class-method
attributes resolve to the *current* :class:`~agentkit.foundation.application.App`
binding at call time::

    await Memory.remember("My name is Ada")

Resolution goes through :func:`current_app`. Because services run on daemon
threads (see :mod:`agentkit.supervise`), the current app is tracked in **both** a
:mod:`contextvars` variable (for async code) and a thread-local (seeded by
``run_all``), so a facade works inside a worker thread even though a contextvar
would not propagate there.
"""

from __future__ import annotations

import contextvars
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

log = logging.getLogger("agentkit.events")

_current_app: contextvars.ContextVar[Any | None] = contextvars.ContextVar(
    "agentkit_current_app", default=None
)
_thread_state = threading.local()


def set_current_app(app: Any | None) -> Any | None:
    """Set the current app in both the contextvar and this thread; return the previous."""
    previous = get_current_app()
    _current_app.set(app)
    _thread_state.app = app
    return previous


def get_current_app() -> Any | None:
    """The current app, preferring the thread-local (for worker threads)."""
    app = getattr(_thread_state, "app", None)
    if app is not None:
        return app
    return _current_app.get()


def current_app() -> Any:
    """The current app, or raise when nothing is bound."""
    app = get_current_app()
    if app is None:
        raise RuntimeError(
            "no current App: construct an App (or AgentApp) and call boot()/serve(), "
            "or scope one with agentkit.foundation.facade.using(app)"
        )
    return app


@contextmanager
def using(app: Any) -> Iterator[Any]:
    """Scope the current app for the duration of the block."""
    token = _current_app.set(app)
    previous = getattr(_thread_state, "app", None)
    _thread_state.app = app
    try:
        yield app
    finally:
        _current_app.reset(token)
        _thread_state.app = previous


async def emit(event: str, **payload: Any) -> bool:
    """Fire a lifecycle event on the current app's dispatcher, if any.

    A listener error never propagates: events observe the app, they do not drive
    it. Returns whether an event was dispatched.
    """
    app = get_current_app()
    dispatcher = getattr(app, "events", None) if app is not None else None
    if dispatcher is None:
        return False
    try:
        await dispatcher.dispatch_async(event, **payload)
    except Exception:  # pragma: no cover - defensive
        log.exception("event listener for %s failed", event)
    return True


class FacadeMeta(type):
    """Route unmapped class attributes to the resolved facade instance."""

    def __getattr__(cls, name: str) -> Any:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return getattr(cls._resolve(), name)


class Facade(metaclass=FacadeMeta):
    """Base class for class-method facades resolved through the current App."""

    @classmethod
    def binding(cls) -> str:
        """The container binding name this facade resolves to."""
        raise NotImplementedError(f"{cls.__name__} must define binding()")

    @classmethod
    def driver_kind(cls) -> str | None:
        """When set, resolve through ``app.manager(kind).driver()`` instead of ``binding()``."""
        return None

    @classmethod
    def _resolve(cls) -> Any:
        app = current_app()
        kind = cls.driver_kind()
        if kind:
            return app.manager(kind).driver()
        return app.make(cls.binding())

    @classmethod
    def using(cls, app: Any):
        """Scope the current app (``with Memory.using(app): ...``)."""
        return using(app)


__all__ = [
    "Facade",
    "FacadeMeta",
    "current_app",
    "emit",
    "get_current_app",
    "set_current_app",
    "using",
]
