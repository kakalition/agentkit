"""The memory contracts — a durable owner store and a recall strategy."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["MemoryStore", "RecallStrategy"]


@runtime_checkable
class MemoryStore(Protocol):
    """Durable, owner-scoped memories."""

    async def remember(self, content: str, *, kind: str = "fact") -> int: ...

    async def search(self, query: str, *, limit: int = 5) -> list[Any]: ...

    async def all(self, limit: int | None = None) -> list[Any]: ...

    async def forget(self, memory_id: int) -> bool: ...


@runtime_checkable
class RecallStrategy(Protocol):
    """Blend a semantic similarity score with other signals into a rank score."""

    def score(self, query: str, similarity: float, memory: Any, now: Any) -> float: ...
