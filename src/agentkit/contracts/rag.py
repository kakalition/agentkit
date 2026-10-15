"""The RAG contracts — chunk, retrieve, and rerank."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["Chunker", "Reranker", "Retriever"]


@runtime_checkable
class Chunker(Protocol):
    """Split a document into retrievable chunks."""

    def chunk(self, text: str, **options: Any) -> list[str]: ...


@runtime_checkable
class Retriever(Protocol):
    """Return the passages most relevant to a query."""

    async def search(self, query: str, *, limit: int = 5, source: str | None = None) -> list[Any]: ...


@runtime_checkable
class Reranker(Protocol):
    """Reorder candidate passages for a query."""

    def rerank(self, query: str, hits: list[Any], **options: Any) -> list[Any]: ...
