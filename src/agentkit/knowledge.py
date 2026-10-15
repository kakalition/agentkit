"""Retrieval-augmented generation: index source material, retrieve on demand.

``KnowledgeBase`` loads text (files, directories, or raw strings), chunks it,
and indexes the chunks with embeddings in the agent's database. The agent gets a
``search_knowledge`` tool that returns the most relevant passages.

    from agentkit import Agent, KnowledgeBase

    kb = KnowledgeBase()                 # uses the default agent runtime
    kb.add_directory("docs")
    agent = Agent.make("notes").instructions("…").knowledge(kb).output(str).build()

:meth:`KnowledgeBase.index` renders a compact source listing you can fold into
instructions (``.knowledge(kb, index=True)`` does it for you).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from semantic_text_splitter import TextSplitter

from agentkit.config import get_settings
from agentkit.db.repositories import Repositories
from agentkit.runtime import build_runtime, repositories

__all__ = ["DEFAULT_CHUNK_CHARS", "DEFAULT_OVERLAP", "KnowledgeBase", "chunk_text"]

DEFAULT_CHUNK_CHARS = 1200
DEFAULT_OVERLAP = 200


def chunk_text(
    text: str, *, chunk_chars: int = DEFAULT_CHUNK_CHARS, overlap: int = DEFAULT_OVERLAP
) -> list[str]:
    """Split ``text`` into overlapping, boundary-aware chunks.

    Backed by ``semantic-text-splitter`` (Rust), which prefers semantic
    boundaries (paragraphs, sentences, words) over a fixed character window.
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_chars:
        return [text]
    splitter = TextSplitter(capacity=chunk_chars, overlap=overlap)
    return [chunk.strip() for chunk in splitter.chunks(text) if chunk.strip()]


class KnowledgeBase:
    """Indexed, searchable source material for one agent."""

    def __init__(
        self,
        app: Any = None,
        *,
        settings: Any = None,
        repos_factory: type[Repositories] = Repositories,
        chunk_chars: int = DEFAULT_CHUNK_CHARS,
        overlap: int = DEFAULT_OVERLAP,
    ) -> None:
        self.app = app
        self._settings = settings
        self.repos_factory = repos_factory
        self.chunk_chars = chunk_chars
        self.overlap = overlap
        self._runtime: Any = None

    @classmethod
    def from_settings(cls, settings: Any = None) -> KnowledgeBase:
        return cls(settings=settings or get_settings())

    # -- session --------------------------------------------------------
    @asynccontextmanager
    async def _scope(self) -> AsyncIterator[Any]:
        if self.app is not None:
            async with self.app.repositories() as repos:
                yield repos
            return
        if self._runtime is None:
            self._runtime = build_runtime(self._settings or get_settings(), repos_factory=self.repos_factory)
        async with repositories(self._runtime) as repos:
            yield repos

    # -- writes ---------------------------------------------------------
    async def add(self, text: str, *, source: str = "") -> int:
        """Chunk and index ``text``; returns the number of chunks added."""
        chunks = chunk_text(text, chunk_chars=self.chunk_chars, overlap=self.overlap)
        if not chunks:
            return 0
        async with self._scope() as repos:
            return await repos.knowledge.add(source, chunks)

    async def add_file(self, path: str | Path, *, source: str | None = None) -> int:
        from agentkit.ingest import extract_text

        path = Path(path).expanduser()
        settings = self._settings or get_settings()
        text = await asyncio.to_thread(extract_text, path, settings=settings)
        return await self.add(text, source=source or str(path))

    async def add_url(self, url: str, *, source: str | None = None) -> int:
        """Fetch a URL and index its text (guarded by ingest settings)."""
        from agentkit.ingest import fetch_url

        settings = self._settings or get_settings()
        text = await fetch_url(url, settings=settings)
        return await self.add(text, source=source or url)

    async def add_directory(
        self, directory: str | Path, *, pattern: str = "**/*.md"
    ) -> int:
        directory = Path(directory).expanduser()
        added = 0
        for file in sorted(directory.glob(pattern)):
            if file.is_file():
                added += await self.add_file(file)
        return added

    async def add_many(self, documents: dict[str, str]) -> int:
        """Index ``{source: text}``; returns total chunks added."""
        total = 0
        for source, text in documents.items():
            total += await self.add(text, source=source)
        return total

    async def clear(self, source: str | None = None) -> int:
        async with self._scope() as repos:
            return await repos.knowledge.clear(source)

    # -- reads ----------------------------------------------------------
    async def search(self, query: str, *, limit: int = 5, source: str | None = None) -> list[Any]:
        async with self._scope() as repos:
            return await repos.knowledge.search(query, limit=limit, source=source)

    async def sources(self) -> list[str]:
        async with self._scope() as repos:
            return await repos.knowledge.sources()

    async def count(self, source: str | None = None) -> int:
        async with self._scope() as repos:
            return await repos.knowledge.count(source)

    async def index(self, *, limit: int = 50) -> str:
        """A compact source listing for instructions (empty when nothing indexed)."""
        async with self._scope() as repos:
            sources = await repos.knowledge.sources()
            if not sources:
                return ""
            lines = []
            for source in sources[:limit]:
                lines.append(f"- {source} ({await repos.knowledge.count(source)} chunks)")
            more = "" if len(sources) <= limit else f"\n- …and {len(sources) - limit} more"
            return "Indexed knowledge (search with `search_knowledge`):\n" + "\n".join(lines) + more

    def format_hits(self, hits: list[Any]) -> str:
        if not hits:
            return "No matching passages."
        rendered = []
        for position, chunk in enumerate(hits, start=1):
            rendered.append(f"[{position}] {chunk.source}#{chunk.seq}\n{chunk.content}")
        return "\n\n".join(rendered)
