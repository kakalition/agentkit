from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from agentkit.approvals import ApprovalQueue
from agentkit.config import AgentSettings
from agentkit.deps import ApprovalRequest
from agentkit.foundation import App
from agentkit.runtime import build_runtime, repositories
from agentkit.session import ChatResult
from agentkit.webui.app import build_webui_app


async def test_approval_queue_roundtrip():
    queue = ApprovalQueue()
    request = ApprovalRequest(tool_call_id="t1", tool_name="db_delete", args={"id": 1})
    pending_task = asyncio.create_task(queue.request([request]))
    await asyncio.sleep(0)

    assert [p.tool_call_id for p in queue.pending()] == ["t1"]
    assert queue.decide("t1", True) is True
    assert await pending_task == {"t1": True}
    assert queue.pending() == []
    assert queue.decide("t1", True) is False  # already resolved


async def test_app_cancel_registry(tmp_path):
    settings = AgentSettings(owner_id="owner", agent_home=tmp_path, memory_embedding_backend="hash")
    app = App(name="t", settings=settings, discover=False, model=object())
    app._runtime = build_runtime(settings)

    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def _work() -> None:
        app._track("c1")
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = asyncio.create_task(_work())
    await started.wait()
    assert app.running() == ["c1"]
    assert app.cancel("c1") is True
    await asyncio.gather(task, return_exceptions=True)
    assert cancelled.is_set()
    assert app.cancel("c1") is False


class _FakeApp:
    def __init__(self) -> None:
        self.approvals = ApprovalQueue()

    async def stream(self, text: str, *, conversation_id: str, actor=None):
        yield SimpleNamespace(kind="text", text="he")
        yield SimpleNamespace(
            kind="final",
            result=ChatResult(output="hello " + text, artifacts=[], history_length=1, usage=None),
        )

    def cancel(self, conversation_id: str) -> bool:
        return conversation_id == "webui:default"


def _client(tmp_path, with_app=True):
    settings = AgentSettings(owner_id="owner", agent_home=tmp_path, memory_embedding_backend="hash")
    runtime = build_runtime(settings)
    app = build_webui_app(
        runtime=runtime, settings=settings, app=_FakeApp() if with_app else None
    )
    return TestClient(app), runtime


def test_stream_and_cancel_endpoints(tmp_path):
    client, _ = _client(tmp_path)
    streamed = client.post("/api/chat/stream", json={"text": "there"})
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    assert "hello there" in streamed.text

    cancelled = client.post("/api/chat/cancel", json={"conversation_id": "webui:default"})
    assert cancelled.json() == {"cancelled": True}
    assert client.post("/api/chat/cancel", json={"conversation_id": "other"}).json() == {
        "cancelled": False
    }


def test_streaming_unavailable_without_app(tmp_path):
    client, _ = _client(tmp_path, with_app=False)
    assert client.post("/api/chat/stream", json={"text": "hi"}).status_code == 501


def test_lessons_review_api(tmp_path):
    client, runtime = _client(tmp_path)

    async def _seed() -> None:
        async with repositories(runtime) as repos:
            await repos.memories.add("Always water the plants.", kind="procedural", status="proposed")

    asyncio.run(_seed())

    rows = client.get("/api/lessons?status=proposed").json()["lessons"]
    assert rows and rows[0]["content"] == "Always water the plants."
    lesson_id = rows[0]["id"]

    approved = client.post(f"/api/lessons/{lesson_id}/approve")
    assert approved.json() == {"id": lesson_id, "status": "active"}
    assert client.get("/api/lessons?status=active").json()["lessons"]

    pending = client.get("/api/approvals").json()
    assert pending == {"approvals": []}
