"""Index and search the knowledge base (RAG) — class-based."""

from __future__ import annotations

from pathlib import Path

import typer

from agentkit.foundation import Command


class KnowledgeAddCommand(Command):
    group = 'knowledge'
    signature = "knowledge:add {path} {--pattern=**/*.md}"
    description = "Index a file or directory into the knowledge base."

    async def handle(self, path: Path, pattern: str = "**/*.md") -> None:
        from agentkit import KnowledgeBase

        kb = KnowledgeBase.from_settings()
        if path.is_dir():
            added = await kb.add_directory(path, pattern=pattern)
        else:
            added = await kb.add_file(path)
        self.info(f"indexed {added} chunk(s)")


class KnowledgeAddFileCommand(Command):
    group = 'knowledge'
    signature = "knowledge:add-file {path} {--source=}"
    description = "Extract text from a document and index it."

    async def handle(self, path: Path, source: str | None = None) -> None:
        from agentkit import KnowledgeBase
        from agentkit.ingest import IngestError

        try:
            added = await KnowledgeBase.from_settings().add_file(path, source=source)
        except (IngestError, OSError) as exc:
            self.error(f"could not ingest {path}: {exc}")
            raise typer.Exit(code=1) from exc
        self.info(f"indexed {added} chunk(s)")


class KnowledgeAddUrlCommand(Command):
    group = 'knowledge'
    signature = "knowledge:add-url {url} {--source=}"
    description = "Fetch a URL and index its text."

    async def handle(self, url: str, source: str | None = None) -> None:
        from agentkit import KnowledgeBase
        from agentkit.ingest import IngestError

        try:
            added = await KnowledgeBase.from_settings().add_url(url, source=source)
        except (IngestError, OSError) as exc:
            self.error(f"could not ingest {url}: {exc}")
            raise typer.Exit(code=1) from exc
        self.info(f"indexed {added} chunk(s)")


class KnowledgeAddTextCommand(Command):
    group = 'knowledge'
    signature = "knowledge:add-text {text} {--source=}"
    description = "Index a literal string."

    async def handle(self, text: str, source: str = "") -> None:
        from agentkit import KnowledgeBase

        added = await KnowledgeBase.from_settings().add(text, source=source)
        self.info(f"indexed {added} chunk(s)")


class KnowledgeSearchCommand(Command):
    group = 'knowledge'
    signature = "knowledge:search {query} {--limit=5}"
    description = "Search indexed knowledge."

    async def handle(self, query: str, limit: int = 5) -> None:
        from agentkit import KnowledgeBase

        kb = KnowledgeBase.from_settings()
        hits = await kb.search(query, limit=limit)
        self.info(kb.format_hits(hits))


class KnowledgeListCommand(Command):
    group = 'knowledge'
    signature = "knowledge:list"
    description = "List indexed sources."

    async def handle(self) -> None:
        from agentkit import KnowledgeBase

        kb = KnowledgeBase.from_settings()
        rows = [(source, await kb.count(source)) for source in await kb.sources()]
        if not rows:
            self.info("(nothing indexed)")
            return
        for source, count in rows:
            self.info(f"  {source} ({count} chunks)")


COMMANDS: list[type] = [
    KnowledgeAddCommand,
    KnowledgeAddFileCommand,
    KnowledgeAddUrlCommand,
    KnowledgeAddTextCommand,
    KnowledgeSearchCommand,
    KnowledgeListCommand,
]
