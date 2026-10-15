"""Native knowledge-admin toolkit: index/replace/forget indexed documents.

Reads are always available; writes (``replace_document``/``forget_document``)
require approval. Chunking reuses :func:`agentkit.knowledge.chunk_text`.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic_ai import RunContext

from agentkit.deps import Deps
from agentkit.knowledge import chunk_text
from agentkit.toolkits._common import emit_event, repos_of

__all__ = ["attach_knowledge_admin"]


def attach_knowledge_admin(agent: Any, *, flag: str = "knowledge_admin_enabled") -> Any:
    """Register the knowledge-admin tools on a built PydanticAI agent (idempotent)."""
    if getattr(agent, "_agentkit_knowledge_admin_attached", False):
        return agent

    @agent.tool
    async def index_document(ctx: RunContext[Deps], text: str, source: str) -> str:
        """Index a document so it can be found with search_knowledge.

        Args:
            text: The document contents.
            source: A label for the document (e.g. a path or title).
        """
        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        chunks = chunk_text(text)
        if not chunks:
            return "ERROR: nothing to index"
        added = await repos.knowledge.add(source, chunks)
        await emit_event("knowledge.indexed", source=source, chunks=added)
        return f"indexed {added} chunk(s) from {source!r}"

    @agent.tool(requires_approval=True)
    async def replace_document(ctx: RunContext[Deps], source: str, text: str) -> str:
        """Replace an indexed document's contents (requires approval).

        Args:
            source: The document label to replace.
            text: The new contents.
        """
        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        added = await repos.knowledge.replace(source, chunk_text(text))
        await emit_event("knowledge.replaced", source=source, chunks=added)
        return f"replaced {source!r} with {added} chunk(s)"

    @agent.tool(requires_approval=True)
    async def forget_document(ctx: RunContext[Deps], source: str) -> str:
        """Remove an indexed document (requires approval).

        Args:
            source: The document label to remove.
        """
        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        removed = await repos.knowledge.clear(source)
        await emit_event("knowledge.forgotten", source=source)
        return f"removed {removed} chunk(s) of {source!r}"

    @agent.tool
    async def list_documents(ctx: RunContext[Deps]) -> str:
        """List the indexed documents and their chunk counts."""
        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        sources = await repos.knowledge.sources()
        if not sources:
            return "(no indexed documents)"
        return json.dumps(
            [{"source": source, "chunks": await repos.knowledge.count(source)} for source in sources],
            default=str,
        )

    agent._agentkit_knowledge_admin_attached = True  # type: ignore[attr-defined]
    return agent
