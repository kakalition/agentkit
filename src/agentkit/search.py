"""Search indexes over conversation history.

The ``search`` kind resolves a :class:`~agentkit.contracts.search.SearchIndex`
from ``search_driver``:

* ``fts`` (default) — SQLite FTS5 over ``messages`` (created in schema sync);
  the repository falls back to ``LIKE`` when FTS5 is unavailable.
* ``scan`` — the bounded linear scan (the historical behavior).
"""

from __future__ import annotations

from typing import Any

from agentkit.contracts.search import SearchHit, SearchIndex
from agentkit.support import register_driver
from agentkit.support.kinds import DriverKind, SearchDriver
from agentkit.support.manager import Manager

__all__ = ["FtsSearchIndex", "ScanSearchIndex", "SearchHit", "SearchIndex", "SearchManager"]

MAX_PREVIEW = 400
MAX_SCAN_CONVERSATIONS = 50
MAX_SCAN_MESSAGES = 200


def _preview(payload: str) -> str:
    """Turn a serialized message payload into a short, human-readable preview."""
    try:
        from agentkit.session import deserialize_messages

        messages = deserialize_messages([payload])
    except Exception:  # pragma: no cover - tolerate corrupt rows
        return payload[:MAX_PREVIEW]
    parts: list[str] = []
    for message in messages:
        for part in getattr(message, "parts", []):
            content = getattr(part, "content", None)
            if isinstance(content, str) and content.strip():
                parts.append(content.strip())
    return ("\n".join(parts) or payload)[:MAX_PREVIEW]


class FtsSearchIndex:
    """SQLite FTS5 index over messages (``LIKE`` fallback lives in the repo)."""

    async def search(self, repos: Any, query: str, *, limit: int = 10) -> list[SearchHit]:
        needle = (query or "").strip()
        if not needle:
            return []
        rows = await repos.messages.search_text(needle, limit=limit)
        return [SearchHit(conversation_id=cid, text=_preview(payload)) for cid, payload in rows]

    async def index(self, repos: Any, conversation_id: str, payloads: list[str]) -> int:
        # The FTS5 triggers keep the index in sync; nothing to do here.
        return len(payloads)

    async def remove(self, repos: Any, conversation_id: str) -> int:
        return 0


class ScanSearchIndex:
    """A bounded linear scan (the historical behavior); no index to maintain."""

    async def search(self, repos: Any, query: str, *, limit: int = 10) -> list[SearchHit]:
        from agentkit.session import deserialize_messages

        needle = (query or "").strip().lower()
        if not needle:
            return []
        cap = max(1, int(limit))
        hits: list[SearchHit] = []
        for conversation in await repos.conversations.list(limit=MAX_SCAN_CONVERSATIONS):
            rows = await repos.messages.list(conversation.id, limit=MAX_SCAN_MESSAGES)
            for message in deserialize_messages([row.payload for row in rows]):
                for part in getattr(message, "parts", []):
                    content = getattr(part, "content", None)
                    if isinstance(content, str) and needle in content.lower():
                        hits.append(SearchHit(conversation.id, content[:MAX_PREVIEW]))
                        if len(hits) >= cap:
                            return hits
        return hits

    async def index(self, repos: Any, conversation_id: str, payloads: list[str]) -> int:
        return len(payloads)

    async def remove(self, repos: Any, conversation_id: str) -> int:
        return 0


class SearchManager(Manager):
    """Resolves the configured search index (``search_driver``, default ``fts``)."""

    kind = DriverKind.SEARCH
    default_driver = SearchDriver.FTS


@register_driver(DriverKind.SEARCH, SearchDriver.FTS)
def _fts_search_driver(app: Any) -> FtsSearchIndex:
    return FtsSearchIndex()


@register_driver(DriverKind.SEARCH, SearchDriver.SCAN)
def _scan_search_driver(app: Any) -> ScanSearchIndex:
    return ScanSearchIndex()
