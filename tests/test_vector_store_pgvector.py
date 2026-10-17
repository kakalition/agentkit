"""T5 — pgvector integration test (opt-in; skips without a live Postgres).

Set ``AGENTKIT_TEST_POSTGRES_URL`` (e.g.
``postgresql://postgres:postgres@localhost:5432/postgres``) to run these; otherwise
they skip. The ``pgvector`` extension is created automatically.
"""

from __future__ import annotations

import os

import pytest

from agentkit.vector_store import PgVectorStore

PG_URL = os.environ.get("AGENTKIT_TEST_POSTGRES_URL", "")
COLLECTION = "agentkit_pgvector_test"

pytestmark = pytest.mark.skipif(
    not PG_URL, reason="set AGENTKIT_TEST_POSTGRES_URL to run pgvector integration tests"
)


async def test_pgvector_roundtrip_and_cosine_ordering() -> None:
    store = PgVectorStore(PG_URL)
    for id in ("a", "b", "c"):
        await store.delete(COLLECTION, id)
    await store.upsert(COLLECTION, "a", [1.0, 0.0], metadata={"k": "a"})
    await store.upsert(COLLECTION, "b", [0.0, 1.0])
    await store.upsert(COLLECTION, "c", [0.9, 0.1])
    try:
        assert await store.count(COLLECTION) == 3
        hits = await store.query(COLLECTION, [1.0, 0.0], limit=3)
        # ordered by the ``<=>`` cosine distance: identical > near > orthogonal
        assert [hit.id for hit in hits] == ["a", "c", "b"]
        assert hits[0].metadata == {"k": "a"}
        assert await store.delete(COLLECTION, "a") is True
        assert await store.count(COLLECTION) == 2
    finally:
        for id in ("a", "b", "c"):
            await store.delete(COLLECTION, id)
