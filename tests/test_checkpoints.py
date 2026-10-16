from __future__ import annotations

from fastapi.testclient import TestClient

from agentkit.checkpoints import (
    FileCheckpointStore,
    MemoryCheckpointStore,
    checkpointer_for,
)
from agentkit.config import AgentSettings
from agentkit.runtime import build_runtime, repositories
from agentkit.webui.app import build_webui_app


async def test_memory_store_bounded_retention():
    store = MemoryCheckpointStore(retention=2)
    for seq in range(5):
        await store.put("run", seq, {"seq": seq})
    rows = await store.list("run")
    assert [row.seq for row in rows] == [3, 4]


async def test_file_store_round_trip(tmp_path):
    store = FileCheckpointStore(tmp_path / "cp")
    await store.put("run", 0, {"x": 1}, label="a")
    await store.put("run", 1, {"x": 2}, label="b")
    assert (await store.latest("run")).label == "b"
    assert await store.delete("run") == 2
    assert await store.list("run") == []


async def test_checkpointer_for_scope_store(runtime):
    async with repositories(runtime) as repos:
        store = checkpointer_for(repos, enabled=True)
        await store.put("scoped", 0, {"x": 1})
        assert (await store.latest("scoped")).seq == 0


def test_checkpointed_graph_executor_uses_store():
    import asyncio

    from agentkit.checkpoints import MemoryCheckpointStore
    from agentkit.graph import END, CheckpointedGraphExecutor, StateGraph

    graph = StateGraph()
    graph.add_node("a", lambda state: {"x": 1})
    graph.add_edge("a", END)
    graph.set_entry("a")

    store = MemoryCheckpointStore()
    executor = CheckpointedGraphExecutor(store, run_id="g1")
    asyncio.run(executor.run(graph, {}))
    rows = asyncio.run(store.list("g1"))
    assert [row.label for row in rows] == ["a"]


def test_checkpoint_endpoints(tmp_path):
    settings = AgentSettings(agent_home=tmp_path, memory_embedding_backend="hash")
    runtime = build_runtime(settings)
    with TestClient(build_webui_app(runtime=runtime, settings=settings)) as client:
        # No checkpoints yet — an empty list (not a 404).
        assert client.get("/api/studio/checkpoints/run-1").json()["checkpoints"] == []
        assert client.get("/api/studio/checkpoints/run-1/0").status_code == 404
