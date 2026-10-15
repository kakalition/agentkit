"""The cache contract — ``app.cache`` / the ``Cache`` facade implement this."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["CacheContract"]


@runtime_checkable
class CacheContract(Protocol):
    """A key/value cache with optional TTLs (Laravel's ``Store`` surface)."""

    def get(self, key: str, default: Any = None) -> Any: ...

    def put(self, key: str, value: Any, ttl: float | None = None) -> Any: ...

    def remember(self, key: str, factory: Any, ttl: float | None = None) -> Any: ...

    def has(self, key: str) -> bool: ...

    def forget(self, key: str) -> None: ...

    def flush(self) -> None: ...
