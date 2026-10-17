"""WS3.1 — vector store contract, manager, and drivers."""

from __future__ import annotations

from typing import Any

import pytest

from agentkit.contracts.vector_store import VectorStore
from agentkit.embeddings import similarity_scores, sqlite_vec_available
from agentkit.errors import ConfigurationError
from agentkit.foundation.application import App
from agentkit.foundation.facade import using
from agentkit.runtime import Runtime
from agentkit.vector_store import (
    NumpyVectorStore,
    PgVectorStore,
    SqliteVecVectorStore,
    current_vector_store,
)


async def test_upsert_query_delete_count() -> None:
    store = NumpyVectorStore()
    await store.upsert("c", "a", [1.0, 0.0], metadata={"k": "a"})
    await store.upsert("c", "b", [0.0, 1.0])
    assert await store.count("c") == 2
    hits = await store.query("c", [1.0, 0.0], limit=1)
    assert hits[0].id == "a"
    assert hits[0].metadata == {"k": "a"}
    assert await store.delete("c", "a") is True
    assert await store.count("c") == 1


async def test_numpy_query_matches_cosine_scan_parity() -> None:
    store = NumpyVectorStore()
    vectors = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.9, 0.1, 0.0], [0.2, 0.8, 0.0]]
    for index, vector in enumerate(vectors):
        await store.upsert("c", str(index), vector)
    query = [1.0, 0.0, 0.0]
    expected = similarity_scores(query, vectors)
    order = sorted(range(len(vectors)), key=lambda i: expected[i], reverse=True)
    hits = await store.query("c", query, limit=len(vectors))
    assert [hit.id for hit in hits] == [str(i) for i in order]
    assert [hit.score for hit in hits] == pytest.approx([expected[i] for i in order])


async def test_rank_matches_cosine_scan_parity() -> None:
    store = NumpyVectorStore()
    query = [1.0, 0.2, 0.0]
    items = [("a", [1.0, 0.0, 0.0]), ("b", [0.0, 1.0, 0.0]), ("c", [0.3, 0.9, 0.0])]
    expected = similarity_scores(query, [v for _, v in items])
    hits = await store.rank("c", query, items, limit=2)
    order = sorted(range(len(items)), key=lambda i: expected[i], reverse=True)[:2]
    assert [hit.id for hit in hits] == [items[i][0] for i in order]


def _app(runtime: Runtime, **updates: Any) -> App:
    settings = runtime.settings.model_copy(update=updates) if updates else runtime.settings
    app = App(name="vec", settings=settings, discover=False)
    app._runtime = runtime
    return app


def test_default_driver_is_repository(runtime: Runtime) -> None:
    app = _app(runtime)
    with using(app):
        assert isinstance(app.manager("vector").driver(), NumpyVectorStore)
        assert isinstance(app.vector_store, NumpyVectorStore)


def test_current_vector_store_resolves_from_app(runtime: Runtime) -> None:
    app = _app(runtime)
    with using(app):
        assert isinstance(current_vector_store(), NumpyVectorStore)


def test_pgvector_requires_postgres(runtime: Runtime) -> None:
    store = PgVectorStore("sqlite:///tmp.db")
    with pytest.raises(ConfigurationError):
        import asyncio

        asyncio.run(store.count("c"))


def test_sqlite_vec_store_raises_without_the_extra(monkeypatch: Any) -> None:
    import agentkit.vector_store as vector_store

    monkeypatch.setattr(vector_store, "sqlite_vec_available", lambda: False)
    with pytest.raises(ConfigurationError, match="agentkit\\[vec\\]"):
        SqliteVecVectorStore(":memory:")


def test_pgvector_driver_selected_from_settings(runtime: Runtime) -> None:
    app = _app(runtime, vector_store_driver="pgvector")
    with using(app):
        assert isinstance(app.manager("vector").driver(), PgVectorStore)
        assert app.manager("vector").configured_driver() == "pgvector"


def test_numpy_store_is_a_vector_store() -> None:
    assert isinstance(NumpyVectorStore(), VectorStore)


@pytest.mark.skipif(not sqlite_vec_available(), reason="sqlite-vec not installed")
async def test_sqlite_vec_store_roundtrip(tmp_path: Any) -> None:
    store = SqliteVecVectorStore(tmp_path / "vectors.db")
    await store.upsert("c", "a", [1.0, 0.0], metadata={"k": "a"})
    await store.upsert("c", "b", [0.0, 1.0])
    assert await store.count("c") == 2
    hits = await store.query("c", [1.0, 0.0], limit=1)
    assert hits[0].id == "a"
    assert hits[0].metadata == {"k": "a"}
    assert await store.delete("c", "a") is True
    assert await store.count("c") == 1


@pytest.mark.skipif(not sqlite_vec_available(), reason="sqlite-vec not installed")
async def test_memory_recall_ranks_through_sqlite_vec(runtime: Runtime, repos: Any) -> None:
    repo = repos.memories
    await repo.add("alpha note", kind="fact", importance=0.0)
    await repo.add("beta note", kind="preference", importance=0.0)
    baseline = [memory.id for memory in await repo.search("note")]
    app = _app(runtime, vector_store_driver="sqlite_vec")
    with using(app):
        assert isinstance(current_vector_store(), SqliteVecVectorStore)
        under = [memory.id for memory in await repo.search("note")]
    assert under == baseline
