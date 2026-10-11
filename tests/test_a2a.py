from __future__ import annotations

import httpx
from a2a import types as t

from agentkit.a2a.client import A2AClient
from agentkit.a2a.server import TaskAgentExecutor, build_a2a_app, build_card
from agentkit.a2a.task_store import SQLAlchemyTaskStore
from agentkit.runtime import Runtime, repositories

BASE = "http://test"


async def test_task_store_roundtrip(runtime: Runtime):
    store = SQLAlchemyTaskStore(runtime)
    task = t.Task(
        id="t1",
        context_id="c1",
        status=t.TaskStatus(state=t.TaskState.TASK_STATE_COMPLETED),
        artifacts=[t.Artifact(parts=[t.Part(text="hi")])],
    )
    await store.save(task, None)  # type: ignore[arg-type]
    got = await store.get("t1", None)  # type: ignore[arg-type]
    assert got is not None and got.artifacts[0].parts[0].text == "hi"
    listing = await store.list(t.ListTasksRequest(), None)  # type: ignore[arg-type]
    assert listing.total_size == 1
    await store.delete("t1", None)  # type: ignore[arg-type]
    assert await store.get("t1", None) is None  # type: ignore[arg-type]


async def _answer(text: str) -> str:
    return f"echo: {text}"


async def test_server_roundtrip_and_persistence(runtime: Runtime):
    card = build_card(
        name="Echo",
        description="echo",
        url=BASE,
        skills=[{"id": "echo", "name": "Echo", "description": "echo"}],
    )
    app = build_a2a_app(
        card=card,
        executor=TaskAgentExecutor(_answer),
        task_store=SQLAlchemyTaskStore(runtime),
        healthz=lambda: True,
    )
    client = A2AClient(transport=httpx.ASGITransport(app))
    assert (await client.fetch_card(BASE)).name == "Echo"
    assert await client.call_agent(BASE, "hi") == "echo: hi"

    with repositories(runtime) as repos:
        rows = repos.a2a.list()
    assert rows and rows[0].state == "TASK_STATE_COMPLETED"
    assert "echo: hi" in rows[0].payload

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url=BASE
    ) as http:
        assert (await http.get("/healthz")).json()["status"] == "ok"
