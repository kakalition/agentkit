"""The memory contracts — a durable owner store and a recall strategy."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["MemoryStore", "RecallStrategy"]


@runtime_checkable
class MemoryStore(Protocol):
    """Durable, owner-scoped memories.

    The contract spans two surfaces: the original one
    (``remember``/``search``/``all``/``forget``) and the capability-facing one
    that :class:`~agentkit.memory.MemoryCapability` and
    :class:`~agentkit.db.repositories.memory.MemoryRepo` use
    (``add``/``list``/``record_use``). Implementations must provide both so the
    same store can back either caller.
    """

    async def remember(self, content: str, *, kind: str = "fact") -> int: ...

    async def add(self, content: str, *, kind: str = "fact", **kwargs: Any) -> Any: ...

    async def search(
        self, query: str, *, kind: str | None = None, limit: int = 5, status: str | None = "active"
    ) -> list[Any]: ...

    async def all(self, limit: int | None = None) -> list[Any]: ...

    async def record_use(self, memories: Any) -> int: ...

    async def forget(self, memory_id: int) -> bool: ...

    async def list(
        self, limit: int | None = None, *, kind: str | None = None, status: str | None = "active"
    ) -> list[Any]: ...


@runtime_checkable
class RecallStrategy(Protocol):
    """Blend a semantic similarity score with other signals into a rank score."""

    def score(self, query: str, similarity: float, memory: Any, now: Any) -> float: ...
