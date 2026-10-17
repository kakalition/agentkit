"""Retrieval-augmented generation: index source material, retrieve on demand.

``KnowledgeBase`` loads text (files, directories, or raw strings), chunks it,
and indexes the chunks with embeddings in the agent's database. The agent gets a
``search_knowledge`` tool that returns the most relevant passages.

    from agentkit.foundation.agent import Agent, KnowledgeBase

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
from agentkit.contracts.rag import Chunker, Reranker, Retriever
from agentkit.db.repositories import Repositories
from agentkit.runtime import build_runtime, repositories
from agentkit.support import Driver, register_driver
from agentkit.support.kinds import ChunkerDriver, DriverKind, RerankerDriver, RetrieverDriver
from agentkit.support.manager import Manager

__all__ = [
    "DEFAULT_CHUNK_CHARS",
    "DEFAULT_OVERLAP",
    "Chunker",
    "FixedChunker",
    "IdentityReranker",
    "InMemoryRetriever",
    "KnowledgeBase",
    "LexicalReranker",
    "Reranker",
    "RepositoryRetriever",
    "Retriever",
    "SemanticChunker",
    "chunk_text",
]

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

    # -- drivers --------------------------------------------------------
    def _driver_app(self) -> Any:
        """The app whose managers resolve chunker/retriever/reranker/ingest drivers."""
        if self.app is not None:
            return self.app
        try:
            from agentkit.foundation.facade import get_current_app

            return get_current_app()
        except Exception:  # pragma: no cover - defensive
            return None

    def _driver(self, kind: str) -> Any:
        app = self._driver_app()
        if app is None:
            return None
        try:
            return app.manager(kind).driver()
        except Exception:  # pragma: no cover - defensive
            return None

    # -- writes ---------------------------------------------------------
    async def add(self, text: str, *, source: str = "") -> int:
        """Chunk and index ``text``; returns the number of chunks added."""
        chunker = self._driver("chunker")
        if chunker is not None:
            chunks = chunker.chunk(text, chunk_chars=self.chunk_chars, overlap=self.overlap)
        else:
            chunks = chunk_text(text, chunk_chars=self.chunk_chars, overlap=self.overlap)
        if not chunks:
            return 0
        async with self._scope() as repos:
            return await repos.knowledge.add(source, chunks)

    async def _load_text(self, path: Path, settings: Any) -> str:
        loader = self._driver("ingest")
        if loader is not None:
            return await asyncio.to_thread(loader.load, path, settings=settings)
        from agentkit.ingest import extract_text

        return await asyncio.to_thread(extract_text, path, settings=settings)

    async def add_file(self, path: str | Path, *, source: str | None = None) -> int:
        path = Path(path).expanduser()
        settings = self._settings or get_settings()
        text = await self._load_text(path, settings)
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
            retriever = self._driver("retriever")
            if retriever is not None and not isinstance(retriever, RepositoryRetriever):
                hits = await retriever.search(query, limit=limit, source=source)
            else:
                hits = await repos.knowledge.search(query, limit=limit, source=source)
            reranker = self._driver("reranker")
            if reranker is not None:
                hits = reranker.rerank(query, hits)
            return hits

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


# --------------------------------------------------------------------------
# Drivers
# --------------------------------------------------------------------------


class SemanticChunker:
    """The default chunker: boundary-aware splitting (``semantic-text-splitter``)."""

    def __init__(self, *, chunk_chars: int = DEFAULT_CHUNK_CHARS, overlap: int = DEFAULT_OVERLAP) -> None:
        self.chunk_chars = chunk_chars
        self.overlap = overlap

    def chunk(self, text: str, **options: Any) -> list[str]:
        return chunk_text(
            text,
            chunk_chars=int(options.get("chunk_chars", self.chunk_chars)),
            overlap=int(options.get("overlap", self.overlap)),
        )


class FixedChunker:
    """A simple fixed-size overlapping chunker (no Rust dependency)."""

    def __init__(self, *, chunk_chars: int = DEFAULT_CHUNK_CHARS, overlap: int = DEFAULT_OVERLAP) -> None:
        self.chunk_chars = chunk_chars
        self.overlap = overlap

    def chunk(self, text: str, **options: Any) -> list[str]:
        text = (text or "").strip()
        if not text:
            return []
        size = int(options.get("chunk_chars", self.chunk_chars))
        step = max(1, size - int(options.get("overlap", self.overlap)))
        return [text[start : start + size].strip() for start in range(0, len(text), step) if text[start : start + size].strip()]


class RepositoryRetriever:
    """The default retriever: the agent database's indexed knowledge chunks."""

    def __init__(self, app: Any = None) -> None:
        self.app = app
        self._kb = KnowledgeBase(app) if app is not None else None

    async def search(self, query: str, *, limit: int = 5, source: str | None = None) -> list[Any]:
        kb = self._kb or KnowledgeBase()
        return await kb.search(query, limit=limit, source=source)


class InMemoryRetriever:
    """A simple substring retriever for tests and ephemeral agents."""

    def __init__(self) -> None:
        self._chunks: list[Any] = []

    def add(self, content: str, *, source: str = "") -> None:
        from types import SimpleNamespace

        self._chunks.append(
            SimpleNamespace(content=content, source=source, seq=len(self._chunks))
        )

    async def search(self, query: str, *, limit: int = 5, source: str | None = None) -> list[Any]:
        needle = (query or "").strip().lower()
        if not needle:
            return []
        hits = [
            chunk
            for chunk in self._chunks
            if (source is None or chunk.source == source) and needle in chunk.content.lower()
        ]
        return hits[:limit]


class IdentityReranker:
    """The default reranker: preserve the retriever's order."""

    def rerank(self, query: str, hits: list[Any], **options: Any) -> list[Any]:
        return list(hits)


class LexicalReranker:
    """A reranker scoring candidates by query-term overlap."""

    def rerank(self, query: str, hits: list[Any], **options: Any) -> list[Any]:
        terms = {term for term in (query or "").lower().split() if term}

        def overlap(hit: Any) -> float:
            content = str(getattr(hit, "content", hit) or "").lower()
            return sum(1.0 for term in terms if term in content)

        return sorted(hits, key=overlap, reverse=True)


class ChunkerManager(Manager):
    """Resolves the configured chunker (``chunker_driver``, default ``semantic``)."""

    kind = DriverKind.CHUNKER
    default_driver = ChunkerDriver.SEMANTIC


class RetrieverManager(Manager):
    """Resolves the configured retriever (``retriever_driver``, default ``repository``)."""

    kind = DriverKind.RETRIEVER
    default_driver = RetrieverDriver.REPOSITORY


class RerankerManager(Manager):
    """Resolves the configured reranker (``reranker_driver``, default ``identity``)."""

    kind = DriverKind.RERANKER
    default_driver = RerankerDriver.IDENTITY


@register_driver(DriverKind.CHUNKER, ChunkerDriver.SEMANTIC)
class SemanticChunkerDriver(Driver):
    def build(self) -> SemanticChunker:
        return SemanticChunker()
@register_driver(DriverKind.CHUNKER, ChunkerDriver.FIXED)
class FixedChunkerDriver(Driver):
    def build(self) -> FixedChunker:
        return FixedChunker()
@register_driver(DriverKind.RETRIEVER, RetrieverDriver.REPOSITORY)
class RepositoryRetrieverDriver(Driver):
    def build(self) -> RepositoryRetriever:
        app = self.app
        return RepositoryRetriever(app)
@register_driver(DriverKind.RETRIEVER, RetrieverDriver.MEMORY)
class MemoryRetrieverDriver(Driver):
    def build(self) -> InMemoryRetriever:
        return InMemoryRetriever()
@register_driver(DriverKind.RERANKER, RerankerDriver.IDENTITY)
class IdentityRerankerDriver(Driver):
    def build(self) -> IdentityReranker:
        return IdentityReranker()
@register_driver(DriverKind.RERANKER, RerankerDriver.LEXICAL)
class LexicalRerankerDriver(Driver):
    def build(self) -> LexicalReranker:
        return LexicalReranker()
