"""Memory consolidation: dedupe, summarize, and prune durable memories.

Registered as the durable task ``memory:consolidate`` (scheduled daily by
:class:`~agentkit.foundation.fullstack.FullStackProvider`) and exposed via
``agentkit memory:consolidate``. Offline by default: near-duplicates are merged by
embedding cosine, long same-kind groups are folded into one memory, and expired
rows are pruned. Pass ``summarizer`` (``list[str] -> str``) to summarize groups
with a model instead of the heuristic.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agentkit.db.repositories import MEMORY_KINDS, Repositories

__all__ = ["consolidate_memories", "register_consolidate_task"]

SUMMARIZE_GROUP_LIMIT = 8
CONSOLIDATE_TASK = "memory:consolidate"


def _heuristic_summary(contents: list[str]) -> str:
    return "; ".join(contents)


async def consolidate_memories(
    repos: Repositories,
    *,
    embedder: Any = None,
    duplicate_threshold: float = 0.92,
    dry_run: bool = False,
    group_limit: int = SUMMARIZE_GROUP_LIMIT,
    summarizer: Callable[[list[str]], str] | None = None,
) -> dict[str, int]:
    """Merge duplicates, summarize long groups, and prune expired memories.

    Returns a counts summary: ``{"merged", "summarized", "pruned"}``.
    """
    store = repos.memories
    if embedder is not None:
        store._embedder = embedder
        store._embedder_resolved = True
        store._embedder_failed = False

    summary = {"merged": 0, "summarized": 0, "pruned": 0}

    expired_rows: list[Any] = await store.expired()
    summary["pruned"] = len(expired_rows)
    if not dry_run:
        for memory in expired_rows:
            await store.forget(memory.id)

    duplicate_groups: list[list[Any]] = await store.near_duplicates(duplicate_threshold)
    for group in duplicate_groups:
        canonical = max(
            group, key=lambda m: (float(m.importance or 0.0), int(m.access_count or 0), len(m.content))
        )
        others = [m for m in group if m.id != canonical.id]
        summary["merged"] += len(others)
        if not dry_run:
            await store.merge(canonical, others)

    for kind in MEMORY_KINDS:
        rows = await store.list(kind=kind)
        if len(rows) <= group_limit:
            continue
        canonical = max(rows, key=lambda m: (float(m.importance or 0.0), int(m.access_count or 0)))
        others = [m for m in rows if m.id != canonical.id]
        contents = [m.content for m in rows]
        text = summarizer(contents) if summarizer is not None else _heuristic_summary(contents)
        summary["summarized"] += len(others)
        if not dry_run:
            if text.strip():
                canonical.content = text.strip()
                vector = await store._embed_document(canonical.content)
                from agentkit.embeddings import pack_vector

                canonical.embedding = pack_vector(vector) if vector else canonical.embedding
            await store.merge(canonical, others)

    return summary


def register_consolidate_task() -> str:
    """Register the durable ``memory:consolidate`` task (idempotent)."""
    from agentkit.scheduler import TASKS, task

    if CONSOLIDATE_TASK in TASKS:
        return CONSOLIDATE_TASK

    @task(CONSOLIDATE_TASK)
    async def _consolidate() -> dict[str, int]:
        from agentkit.config import get_settings
        from agentkit.runtime import build_runtime, repositories

        settings = get_settings()
        runtime = build_runtime(settings)
        async with repositories(runtime) as repos:
            return await consolidate_memories(
                repos,
                duplicate_threshold=float(settings.memory_consolidate_duplicate_threshold),
            )

    return CONSOLIDATE_TASK
