from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agentkit.db.repositories import MemoryRepo, Repositories


class _ConstEmbedder:
    """Every text embeds to the same vector (so similarity ties)."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]


async def test_memory_kind_validation(repos: Repositories):
    row = await repos.memories.add("Ada", kind="person", importance=0.8)
    assert row.kind == "person"
    assert row.importance == 0.8
    with pytest.raises(ValueError, match="unknown memory kind"):
        await repos.memories.add("x", kind="nonsense")


async def test_hybrid_search_prefers_important_when_similarity_ties(repos: Repositories):
    repo = MemoryRepo(repos.session, "owner", embedder=_ConstEmbedder())
    await repo.add("low value", importance=0.1)
    await repo.add("high value", importance=0.95)
    hits = await repo.search("anything")
    assert hits[0].content == "high value"


async def test_search_filters_by_kind(repos: Repositories):
    await repos.memories.add("Prefers tea", kind="preference")
    await repos.memories.add("Cat named Mochi", kind="person")
    hits = await repos.memories.search("cat", kind="person")
    assert [row.kind for row in hits] == ["person"]


async def test_record_use_bumps_counts(repos: Repositories):
    row = await repos.memories.add("Ada")
    assert row.access_count == 0
    assert await repos.memories.record_use([row]) == 1
    refreshed = await repos.memories.get(row.id)
    assert refreshed is not None
    assert refreshed.access_count == 1
    assert refreshed.last_used_at is not None


async def test_expired_and_prune(repos: Repositories):
    past = datetime.now(UTC) - timedelta(days=1)
    future = datetime.now(UTC) + timedelta(days=1)
    await repos.memories.add("temporary", expires_at=past)
    await repos.memories.add("lasting", expires_at=future)
    await repos.memories.add("forever")
    assert len(await repos.memories.expired()) == 1
    assert await repos.memories.prune_expired() == 1
    assert [row.content for row in await repos.memories.list()] == ["forever", "lasting"]


async def test_near_duplicates_and_merge(repos: Repositories):
    first = await repos.memories.add("The user likes strong coffee", importance=0.9)
    second = await repos.memories.add("The user likes strong coffee", importance=0.4)
    await repos.memories.record_use([second])
    groups = await repos.memories.near_duplicates(threshold=0.9)
    assert len(groups) == 1
    canonical = await repos.memories.merge(groups[0][0], groups[0][1:])
    assert canonical.id == first.id
    assert canonical.importance == 0.9
    assert canonical.access_count >= 1
    assert len(await repos.memories.list()) == 1
