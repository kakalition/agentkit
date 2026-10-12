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

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from agentkit.config import get_settings
from agentkit.db.repositories import Repositories
from agentkit.runtime import build_runtime, repositories

__all__ = ["DEFAULT_CHUNK_CHARS", "DEFAULT_OVERLAP", "KnowledgeBase", "chunk_text"]

DEFAULT_CHUNK_CHARS = 1200
DEFAULT_OVERLAP = 200


def chunk_text(
    text: str, *, chunk_chars: int = DEFAULT_CHUNK_CHARS, overlap: int = DEFAULT_OVERLAP
) -> list[str]:
    """Split ``text`` into overlapping chunks, preferring paragraph boundaries."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_chars, length)
        if end < length:
            window = text[start:end]
            split = window.rfind("\n\n")
            if split < chunk_chars // 2:
                split = window.rfind("\n")
            if split > chunk_chars // 3:
                end = start + split
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return chunks


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
    @contextmanager
    def _scope(self) -> Iterator[Any]:
        if self.app is not None:
            with self.app.repositories() as repos:
                yield repos
            return
        if self._runtime is None:
            self._runtime = build_runtime(self._settings or get_settings(), repos_factory=self.repos_factory)
        with repositories(self._runtime) as repos:
            yield repos

    # -- writes ---------------------------------------------------------
    def add(self, text: str, *, source: str = "") -> int:
        """Chunk and index ``text``; returns the number of chunks added."""
        chunks = chunk_text(text, chunk_chars=self.chunk_chars, overlap=self.overlap)
        if not chunks:
            return 0
        with self._scope() as repos:
            return repos.knowledge.add(source, chunks)

    def add_file(self, path: str | Path, *, source: str | None = None) -> int:
        path = Path(path).expanduser()
        text = path.read_text(encoding="utf-8", errors="ignore")
        return self.add(text, source=source or str(path))

    def add_directory(
        self, directory: str | Path, *, pattern: str = "**/*.md"
    ) -> int:
        directory = Path(directory).expanduser()
        added = 0
        for file in sorted(directory.glob(pattern)):
            if file.is_file():
                added += self.add_file(file)
        return added

    def add_many(self, documents: dict[str, str]) -> int:
        """Index ``{source: text}``; returns total chunks added."""
        return sum(self.add(text, source=source) for source, text in documents.items())

    def clear(self, source: str | None = None) -> int:
        with self._scope() as repos:
            return repos.knowledge.clear(source)

    # -- reads ----------------------------------------------------------
    def search(self, query: str, *, limit: int = 5, source: str | None = None) -> list[Any]:
        with self._scope() as repos:
            return repos.knowledge.search(query, limit=limit, source=source)

    def sources(self) -> list[str]:
        with self._scope() as repos:
            return repos.knowledge.sources()

    def count(self, source: str | None = None) -> int:
        with self._scope() as repos:
            return repos.knowledge.count(source)

    def index(self, *, limit: int = 50) -> str:
        """A compact source listing for instructions (empty when nothing indexed)."""
        with self._scope() as repos:
            sources = repos.knowledge.sources()
            if not sources:
                return ""
            lines = []
            for source in sources[:limit]:
                lines.append(f"- {source} ({repos.knowledge.count(source)} chunks)")
            more = "" if len(sources) <= limit else f"\n- …and {len(sources) - limit} more"
            return "Indexed knowledge (search with `search_knowledge`):\n" + "\n".join(lines) + more

    def format_hits(self, hits: list[Any]) -> str:
        if not hits:
            return "No matching passages."
        rendered = []
        for position, chunk in enumerate(hits, start=1):
            rendered.append(f"[{position}] {chunk.source}#{chunk.seq}\n{chunk.content}")
        return "\n\n".join(rendered)
