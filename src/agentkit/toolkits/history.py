"""Native history toolkit: owner-scoped reads over past conversations."""

from __future__ import annotations

import json
from typing import Any

from pydantic_ai import RunContext

from agentkit.deps import Deps
from agentkit.toolkits._common import repos_of

__all__ = ["attach_history"]

MAX_LIMIT = 100


async def _owned_conversation(repos: Any, conversation_id: str) -> Any | None:
    conversation = await repos.conversations.get(conversation_id)
    if conversation is not None and conversation.owner_id != repos.owner_id:
        return None
    return conversation


def attach_history(agent: Any, *, flag: str = "history_tools_enabled") -> Any:
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
        """Search past conversation messages for a substring.

        Args:
            query: The text to look for (case-insensitive).
        """
        from agentkit.session import deserialize_messages

        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        needle = (query or "").strip().lower()
        if not needle:
            return "ERROR: empty query"
        hits: list[dict[str, Any]] = []
        conversations = await repos.conversations.list(limit=50)
        for conversation in conversations:
            rows = await repos.messages.list(conversation.id, limit=200)
            for payload in deserialize_messages([row.payload for row in rows]):
                for part in getattr(payload, "parts", []):
                    content = getattr(part, "content", None)
                    if isinstance(content, str) and needle in content.lower():
                        hits.append(
                            {"conversation_id": conversation.id, "text": content[:400]}
                        )
                    if len(hits) >= max(1, min(int(limit), MAX_LIMIT)):
                        return json.dumps(hits, default=str)
        return json.dumps(hits, default=str) if hits else "(no matches)"

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
