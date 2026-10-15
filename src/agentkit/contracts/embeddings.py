"""The embeddings contract — text in, vectors out."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["EmbedderContract"]


@runtime_checkable
class EmbedderContract(Protocol):
    """Batch-embed texts into equal-length float vectors."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...
