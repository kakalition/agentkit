"""The search contract — an index over conversation history.

Concrete indexes are resolved by :class:`agentkit.support.Manager` for the
``search`` kind (``search_driver``: ``fts`` default, ``scan`` fallback). Indexes
are stateless singletons; the per-request repositories are passed in, so the same
driver serves every session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

__all__ = ["SearchHit", "SearchIndex"]


@dataclass(slots=True)
class SearchHit:
    """One search result: the conversation it belongs to and a short preview."""

    conversation_id: str
    text: str
    score: float = 0.0


@runtime_checkable
class SearchIndex(Protocol):
    """A searchable index over conversation messages."""

    async def search(self, repos: Any, query: str, *, limit: int = 10) -> list[SearchHit]: ...

    async def index(self, repos: Any, conversation_id: str, payloads: list[str]) -> int: ...

    async def remove(self, repos: Any, conversation_id: str) -> int: ...
