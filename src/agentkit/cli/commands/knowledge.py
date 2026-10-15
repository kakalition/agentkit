"""Index and search the knowledge base (RAG)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from agentkit.cli._app import knowledge_app


@knowledge_app.command("add")
def knowledge_add(
    path: Path = typer.Argument(..., help="File or directory to index."),
    pattern: str = typer.Option("**/*.md", help="Glob when indexing a directory."),
) -> None:
    """Index a file or directory into the knowledge base."""

    from agentkit import KnowledgeBase

    kb = KnowledgeBase.from_settings()
    if path.is_dir():
        added = asyncio.run(kb.add_directory(path, pattern=pattern))
    else:
        added = asyncio.run(kb.add_file(path))
    typer.echo(f"indexed {added} chunk(s)")


@knowledge_app.command("add-file")
def knowledge_add_file(
    path: Path = typer.Argument(..., help="File to index (pdf/docx/html/txt/md/…)."),
    source: str | None = typer.Option(None, "--source", help="Label (default: the path)."),
) -> None:
    """Extract text from a document and index it."""
    from agentkit import KnowledgeBase
    from agentkit.ingest import IngestError

    try:
        added = asyncio.run(KnowledgeBase.from_settings().add_file(path, source=source))
    except (IngestError, OSError) as exc:
        typer.echo(f"could not ingest {path}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"indexed {added} chunk(s)")


@knowledge_app.command("add-url")
def knowledge_add_url(
    url: str = typer.Argument(..., help="URL to fetch and index."),
    source: str | None = typer.Option(None, "--source", help="Label (default: the url)."),
) -> None:
    """Fetch a URL and index its text."""
    from agentkit import KnowledgeBase
    from agentkit.ingest import IngestError

    try:
        added = asyncio.run(KnowledgeBase.from_settings().add_url(url, source=source))
    except (IngestError, OSError) as exc:
        typer.echo(f"could not ingest {url}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"indexed {added} chunk(s)")


@knowledge_app.command("add-text")
def knowledge_add_text(
    text: str = typer.Argument(..., help="Text to index."),
    source: str = typer.Option("", "--source", help="Label for this text."),
) -> None:
    """Index a literal string."""

    from agentkit import KnowledgeBase

    added = asyncio.run(KnowledgeBase.from_settings().add(text, source=source))
    typer.echo(f"indexed {added} chunk(s)")


@knowledge_app.command("search")
def knowledge_search(
    query: str = typer.Argument(..., help="Query text."),
    limit: int = typer.Option(5, help="Maximum passages."),
) -> None:
    """Search indexed knowledge."""

    from agentkit import KnowledgeBase

    kb = KnowledgeBase.from_settings()
    hits = asyncio.run(kb.search(query, limit=limit))
    typer.echo(kb.format_hits(hits))


@knowledge_app.command("list")
def knowledge_list() -> None:
    """List indexed sources."""

    from agentkit import KnowledgeBase

    kb = KnowledgeBase.from_settings()

    async def _list() -> list[tuple[str, int]]:
        return [(source, await kb.count(source)) for source in await kb.sources()]

    rows = asyncio.run(_list())
    if not rows:
        typer.echo("(nothing indexed)")
        return
    for source, count in rows:
        typer.echo(f"  {source} ({count} chunks)")
