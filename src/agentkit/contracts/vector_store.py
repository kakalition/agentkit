"""The vector-store contract — collection-scoped nearest-neighbour search."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

__all__ = ["VectorHit", "VectorStore"]


@dataclass
class VectorHit:
    """One nearest-neighbour result."""

    id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class VectorStore(Protocol):
    """Store vectors per collection and search them by cosine similarity."""

    async def upsert(
        self, collection: str, id: str, vector: list[float], *, metadata: dict[str, Any] | None = None
    ) -> None: ...

    async def query(
        self, collection: str, vector: list[float], *, limit: int = 5
    ) -> list[VectorHit]: ...

    async def rank(
        self,
        collection: str,
        vector: Sequence[float],
        items: Sequence[tuple[str, Sequence[float]]],
        *,
        limit: int | None = None,
    ) -> list[VectorHit]:
        """Cosine-rank caller-supplied ``items`` (id, vector) without indexing.

        Used by memory recall / RAG, whose vectors already live in the database;
        the default implementation is the numpy cosine scan.
        """
        ...

    async def delete(self, collection: str, id: str) -> bool: ...

    async def count(self, collection: str) -> int: ...

