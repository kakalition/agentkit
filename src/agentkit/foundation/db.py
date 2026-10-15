"""Active-repository scoping for the thin ``Model`` / ``DB`` layer.

An async transaction opened with ``await DB.transaction()`` (or ``async with
DB.session()``) is made *ambient* through a contextvar, so ``await Model.create(...)``
inside the block joins the same session instead of opening its own.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

_active: ContextVar[Any] = ContextVar("agentkit_active_repos", default=None)


def active_repos() -> Any:
    """The ambient repositories, or ``None`` outside a ``DB`` scope."""
    return _active.get()


@asynccontextmanager
async def using_repos(repos: Any) -> AsyncIterator[Any]:
    token = _active.set(repos)
    try:
        yield repos
    finally:
        _active.reset(token)


@asynccontextmanager
async def session_scope(app: Any) -> AsyncIterator[Any]:
    """Yield the ambient repositories if any, else open a fresh app session."""
    existing = active_repos()
    if existing is not None:
        yield existing
        return
    async with app.repositories() as repos:
        token = _active.set(repos)
        try:
            yield repos
        finally:
            _active.reset(token)


__all__ = ["active_repos", "session_scope", "using_repos"]
