"""WS3.2 — eval datasets (store, manager, file import)."""

from __future__ import annotations

from typing import Any

from agentkit.contracts.dataset import DatasetStore
from agentkit.datasets import (
    MemoryDatasetStore,
    RepositoryDatasetStore,
    load_dataset_file,
)
from agentkit.foundation.application import App
from agentkit.foundation.facade import using
from agentkit.runtime import Runtime


def _app(runtime: Runtime, **updates: Any) -> App:
    settings = runtime.settings.model_copy(update=updates) if updates else runtime.settings
    app = App(name="ds", settings=settings, discover=False)
    app._runtime = runtime
    return app


async def test_memory_store_crud() -> None:
    store = MemoryDatasetStore()
    await store.put("math", [{"input": "1+1", "expected": "2"}], source="inline")
    assert isinstance(store, DatasetStore)
    assert await store.cases("math") == [{"input": "1+1", "expected": "2"}]
    assert [row["name"] for row in await store.list()] == ["math"]
    assert (await store.get("math"))["source"] == "inline"
    assert await store.remove("math") is True
    assert await store.get("math") is None


def test_load_csv(tmp_path: Any) -> None:
    path = tmp_path / "cases.csv"
    path.write_text("input,expected\n2+2,4\n3*3,9\n", encoding="utf-8")
    cases = load_dataset_file(path)
    assert cases == [{"input": "2+2", "expected": "4"}, {"input": "3*3", "expected": "9"}]


def test_load_jsonl_and_json(tmp_path: Any) -> None:
    jsonl = tmp_path / "cases.jsonl"
    jsonl.write_text('{"input": "a"}\n\n{"input": "b"}\n', encoding="utf-8")
    assert load_dataset_file(jsonl) == [{"input": "a"}, {"input": "b"}]

    doc = tmp_path / "cases.json"
    doc.write_text('{"cases": [{"input": "c"}]}', encoding="utf-8")
    assert load_dataset_file(doc) == [{"input": "c"}]


def test_default_driver_is_repository(runtime: Runtime) -> None:
    app = _app(runtime)
    with using(app):
        assert isinstance(app.manager("dataset").driver(), RepositoryDatasetStore)


def test_memory_driver_selected(runtime: Runtime) -> None:
    app = _app(runtime, dataset_driver="memory")
    with using(app):
        assert isinstance(app.manager("dataset").driver(), MemoryDatasetStore)


async def test_repository_store_roundtrip(runtime: Runtime) -> None:
    app = _app(runtime)
    store = RepositoryDatasetStore(app)
    await store.put("suite", [{"input": "x"}], source="file")
    assert await store.cases("suite") == [{"input": "x"}]
    assert [row.name for row in await store.list()] == ["suite"]
    assert await store.remove("suite") is True
    assert await store.cases("suite") == []
