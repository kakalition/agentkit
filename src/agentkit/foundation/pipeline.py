"""A small middleware pipeline.

Mirrors Laravel's ``Pipeline``: build a stack of middleware, send it a passable,
and terminate in a destination. Middleware receives the passable and a
``call_next`` coroutine to continue the chain::

    async def timing(passable, call_next):
        start = time.perf_counter()
        result = await call_next()
        log.info("turn took %.3fs", time.perf_counter() - start)
        return result

    await Pipeline().send(text).through(timing).then(runner.send)
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

MiddlewareFunc = Callable[[Any, Callable[[Any], Awaitable[Any]]], Any]
Destination = Callable[[Any], Any]


class Pipeline:
    """A reusable async middleware stack."""

    def __init__(self, middlewares: list[MiddlewareFunc] | None = None, *, passable: Any = None) -> None:
        self._middlewares: list[MiddlewareFunc] = list(middlewares or [])
        self._passable = passable

    def send(self, passable: Any) -> Pipeline:
        clone = self._clone()
        clone._passable = passable
        return clone

    def through(self, *middlewares: MiddlewareFunc) -> Pipeline:
        clone = self._clone()
        clone._middlewares.extend(middlewares)
        return clone

    def _clone(self) -> Pipeline:
        return Pipeline(self._middlewares, passable=self._passable)

    async def then(self, destination: Destination) -> Any:
        chain = destination
        for middleware in reversed(self._middlewares):
            chain = _wrap(middleware, chain)
        result = chain(self._passable)
        if inspect.isawaitable(result):
            result = await result
        return result


def _wrap(middleware: MiddlewareFunc, nxt: Destination) -> Destination:
    async def handler(passable: Any) -> Any:
        async def call_next(next_passable: Any = None) -> Any:
            result = nxt(passable if next_passable is None else next_passable)
            if inspect.isawaitable(result):
                result = await result
            return result

        result = middleware(passable, call_next)
        if inspect.isawaitable(result):
            result = await result
        return result

    return handler


async def run_pipeline(middlewares: list[MiddlewareFunc], passable: Any, destination: Destination) -> Any:
    """Convenience: run ``middlewares`` once around ``destination(passable)``."""
    return await Pipeline(middlewares).send(passable).then(destination)


__all__ = ["Middleware", "MiddlewareFunc", "MiddlewareGroup", "Pipeline", "run_pipeline"]


class MiddlewareGroup:
    """A named bundle of middleware (Laravel's middleware groups).

        app.middleware(MiddlewareGroup("web", [logging_middleware, auth]))
        app.middleware("web")   # expands to the group's members
    """

    def __init__(self, name: str, middlewares: list[Any] | None = None) -> None:
        self.name = name
        self.middlewares = list(middlewares or [])

    def __iter__(self) -> Any:
        return iter(self.middlewares)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"MiddlewareGroup({self.name!r}, {len(self.middlewares)} middleware)"


class Middleware:
    """Base class for turn middleware.

    Subclass and override :meth:`handle`; instances are callable, so they can be
    passed to ``app.middleware(...)`` directly.
    """

    async def handle(self, turn: Any, call_next: Any) -> Any:
        raise NotImplementedError

    async def __call__(self, turn: Any, call_next: Any) -> Any:
        return await self.handle(turn, call_next)
