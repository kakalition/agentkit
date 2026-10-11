"""Durable per-owner memory: facts the agent should not forget between chats.

Memories are plain rows in the same database as conversations (owner-scoped),
each with a CPU-computed embedding. :func:`attach_memory` gives a PydanticAI
agent three tools — ``remember``, ``recall`` and ``forget_memory`` — and a
dynamic instructions block that lists what it already knows, so it can greet the
user by name, keep their preferences, and stop asking the same thing twice.
Recall is semantic (cosine over embeddings); when no embedder is available it
falls back to keyword matching. See :mod:`agentkit.embeddings`.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent, RunContext

DEFAULT_DIGEST_LIMIT = 50

MEMORY_GUIDE = (
    "You have long-term memory about the user. When they tell you a durable fact "
    "(their name, preferences, important dates, how they like things done), save "
    "it with the `remember` tool. Use `recall` to look something up and "
    "`forget_memory` to delete a fact by its id. Keep memories short and factual."
)


def _store(deps: Any) -> Any:
    return getattr(getattr(deps, "repos", None), "memories", None)


def _enabled(deps: Any) -> bool:
    settings = getattr(deps, "settings", None)
    return bool(getattr(settings, "memory_enabled", True))


def memory_digest(repos: Any, *, limit: int = DEFAULT_DIGEST_LIMIT) -> str | None:
    """A bullet list of everything remembered for the owner, or ``None`` if empty."""
    store = getattr(repos, "memories", None)
    if store is None or limit <= 0:
        return None
    rows = store.list(limit=limit)
    if not rows:
        return None
    lines = "\n".join(f"- #{row.id} {row.content}" for row in rows)
    return f"Known facts about the user:\n{lines}"


def attach_memory(agent: Agent[Any, Any]) -> Agent[Any, Any]:
    """Register memory tools + a dynamic memory digest on ``agent`` (idempotent)."""
    if getattr(agent, "_agentkit_memory_attached", False):
        return agent

    @agent.tool
    async def remember(ctx: RunContext[Any], fact: str) -> str:
        """Save a durable fact about the user (their name, preferences, dates, …)."""
        store = _store(ctx.deps)
        if store is None or not _enabled(ctx.deps):
            return "memory is unavailable"
        row = store.add(fact)
        return f"remembered as #{row.id}"

    @agent.tool
    async def recall(ctx: RunContext[Any], query: str) -> str:
        """Look up what you already remember about the user."""
        store = _store(ctx.deps)
        if store is None or not _enabled(ctx.deps):
            return "(memory unavailable)"
        hits = store.search(query)
        if not hits:
            return "(nothing remembered about that)"
        return "\n".join(f"{row.id}: {row.content}" for row in hits)

    @agent.tool
    async def forget_memory(ctx: RunContext[Any], memory_id: int) -> str:
        """Delete a remembered fact by its id."""
        store = _store(ctx.deps)
        if store is None or not _enabled(ctx.deps):
            return "memory is unavailable"
        return "forgotten" if store.forget(memory_id) else "no such memory"

    @agent.instructions
    def _memory_instructions(ctx: RunContext[Any]) -> str | None:
        if not _enabled(ctx.deps):
            return None
        owner_name = getattr(getattr(ctx.deps, "settings", None), "owner_name", None)
        parts = [MEMORY_GUIDE]
        if owner_name and owner_name != "Owner":
            parts.append(f"The user's name is {owner_name}.")
        digest = memory_digest(ctx.deps.repos)
        if digest:
            parts.append(digest)
        return "\n\n".join(parts)

    agent._agentkit_memory_attached = True  # type: ignore[attr-defined]
    return agent


__all__ = ["DEFAULT_DIGEST_LIMIT", "MEMORY_GUIDE", "attach_memory", "memory_digest"]
