"""Native history toolkit: owner-scoped reads over past conversations."""

from __future__ import annotations

import json
from typing import Any

from pydantic_ai import RunContext

from agentkit.deps import Deps
from agentkit.toolkits._common import repos_of

__all__ = ["_attach_history"]

MAX_LIMIT = 100


async def _owned_conversation(repos: Any, conversation_id: str) -> Any | None:
    conversation = await repos.conversations.get(conversation_id)
    if conversation is not None and conversation.owner_id != repos.owner_id:
        return None
    return conversation


def _index_for(ctx: RunContext[Deps]) -> Any:
    """The configured search index (falls back to a bounded scan)."""
    extras = getattr(ctx.deps, "extras", None) or {}
    app = extras.get("app")
    if app is not None:
        try:
            return app.manager("search").driver()
        except Exception:  # pragma: no cover - defensive
            pass
    from agentkit.search import ScanSearchIndex

    return ScanSearchIndex()


async def _search(ctx: RunContext[Deps], query: str, limit: int) -> str:
    repos = repos_of(ctx)
    if repos is None:
        return "ERROR: no repositories"
    needle = (query or "").strip()
    if not needle:
        return "ERROR: empty query"
    cap = max(1, min(int(limit), MAX_LIMIT))
    hits = await _index_for(ctx).search(repos, needle, limit=cap)
    if not hits:
        return "(no matches)"
    return json.dumps(
        [{"conversation_id": hit.conversation_id, "text": hit.text} for hit in hits], default=str
    )


def _attach_history(agent: Any, *, flag: str = "history_tools_enabled") -> Any:
    """Register the history tools on a built PydanticAI agent (idempotent)."""
    if getattr(agent, "_agentkit_history_attached", False):
        return agent

    @agent.tool
    async def list_conversations(ctx: RunContext[Deps], limit: int = 20) -> str:
        """List the agent's recent conversations.

        Args:
            limit: Maximum conversations to list (capped at 100).
        """
        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        rows = await repos.conversations.list(limit=max(1, min(int(limit), MAX_LIMIT)))
        if not rows:
            return "(no conversations)"
        return json.dumps(
            [
                {
                    "id": row.id,
                    "channel": row.channel,
                    "updated_at": row.updated_at.isoformat(),
                }
                for row in rows
            ],
            default=str,
        )

    @agent.tool
    async def search_history(ctx: RunContext[Deps], query: str, limit: int = 10) -> str:
        """Search past conversation messages (indexed full-text search).

        Args:
            query: The text to look for.
            limit: Maximum matches to return (capped at 100).
        """
        return await _search(ctx, query, limit)

    @agent.tool
    async def search_sessions(ctx: RunContext[Deps], query: str, limit: int = 10) -> str:
        """Alias for ``search_history``: search across past conversations.

        Args:
            query: The text to look for.
            limit: Maximum matches to return (capped at 100).
        """
        return await _search(ctx, query, limit)

    @agent.tool
    async def read_conversation(ctx: RunContext[Deps], id: str, limit: int = 20) -> str:
        """Read a conversation transcript by id.

        Args:
            id: The conversation id (from list_conversations).
            limit: Maximum recent messages to include.
        """
        from agentkit.compaction import transcript
        from agentkit.session import load_history

        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        if await _owned_conversation(repos, id) is None:
            return "(not found)"
        messages = await load_history(repos, id, max_messages=max(1, min(int(limit), MAX_LIMIT)))
        return transcript(messages) or "(empty conversation)"

    agent._agentkit_history_attached = True  # type: ignore[attr-defined]
    return agent
