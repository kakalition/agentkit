"""The ingestion contract — turn a document or bytes into plain text."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

__all__ = ["DocumentLoader"]


@runtime_checkable
class DocumentLoader(Protocol):
    """Extract plain text from a local file, path or raw bytes."""

    def supports(self, suffix: str) -> bool: ...

    def load(
        self,
        source: str | Path | bytes,
        *,
        suffix: str | None = None,
        settings: Any = None,
    ) -> str: ...
