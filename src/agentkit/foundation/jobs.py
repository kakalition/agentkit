"""The in-process cache — Laravel's ``Cache`` for agents.

``Job``/``Queue`` now live in :mod:`agentkit.foundation.queue`; ``Job`` is
re-exported here for convenience.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

from agentkit.foundation.queue import Job

__all__ = ["CacheStore", "Job"]


class CacheStore:
    """A small in-process TTL cache (per process), like Laravel's array store."""

    def __init__(self, *, maxsize: int = 1024) -> None:
        self._store: OrderedDict[str, tuple[float | None, Any]] = OrderedDict()
        self.maxsize = maxsize

    def get(self, key: str, default: Any = None) -> Any:
        entry = self._store.get(key)
        if entry is None:
            return default
        expires, value = entry
        if expires is not None and expires < time.monotonic():
            self._store.pop(key, None)
            return default
        self._store.move_to_end(key)
        return value

    def has(self, key: str) -> bool:
        return self.get(key, _MISSING) is not _MISSING

    def put(self, key: str, value: Any, ttl: float | None = None) -> Any:
        expires = None if ttl is None else time.monotonic() + ttl
        self._store[key] = (expires, value)
        self._store.move_to_end(key)
        while len(self._store) > self.maxsize:
            self._store.popitem(last=False)
        return value

    def remember(self, key: str, factory: Any, ttl: float | None = None) -> Any:
        if self.has(key):
            return self.get(key)
        return self.put(key, factory() if callable(factory) else factory, ttl)

    def forget(self, key: str) -> None:
        self._store.pop(key, None)

    def flush(self) -> None:
        self._store.clear()


_MISSING = object()
