"""Active-repository scoping for the thin ``Model`` / ``DB`` layer.

A transaction opened with ``DB.transaction()`` (or a ``DB.session()`` block) is
made *ambient* through a contextvar, so ``Model.create(...)`` inside the block
joins the same session instead of opening its own.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_active: ContextVar[Any] = ContextVar("agentkit_active_repos", default=None)


def active_repos() -> Any:
    """The ambient repositories, or ``None`` outside a ``DB`` scope."""
    return _active.get()


@contextmanager
def using_repos(repos: Any) -> Iterator[Any]:
    token = _active.set(repos)
    try:
        yield repos
    finally:
        _active.reset(token)


@contextmanager
def session_scope(app: Any) -> Iterator[Any]:
    """Yield the ambient repositories if any, else open a fresh app session."""
    existing = active_repos()
    if existing is not None:
        yield existing
        return
    with app.repositories() as repos:
        token = _active.set(repos)
        try:
            yield repos
        finally:
            _active.reset(token)


__all__ = ["active_repos", "session_scope", "using_repos"]
