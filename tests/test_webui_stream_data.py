from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic_ai import Agent as PydanticAgent
from pydantic_ai.models.test import TestModel

from agentkit.config import AgentSettings
from agentkit.deps import Deps
from agentkit.foundation import App
from agentkit.runtime import build_runtime
from agentkit.webui.app import build_webui_app


def _app(tmp_path, **settings_kwargs) -> App:
    settings = AgentSettings(
        agent_home=tmp_path, memory_embedding_backend="hash", **settings_kwargs
    )
    app = App("webui", settings=settings, discover=False, model=TestModel())
    app.boot()
    app.agent(PydanticAgent(TestModel(), output_type=str, deps_type=Deps, instructions="hi"))
    return app


def _client(app: App) -> TestClient:
    return TestClient(
        build_webui_app(
            runtime=app.runtime, settings=app.settings, app=app, answer=app.answer
        )
    )


def _sse_events(response_text: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    for chunk in response_text.replace("\r\n", "\n").split("\n\n"):
        name = "message"
        data = ""
        for line in chunk.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].lstrip()
        if chunk.strip():
            events.append((name, data))
    return events


def test_chat_stream_emits_text_and_final(tmp_path):
    client = _client(_app(tmp_path))
    response = client.post(
        "/api/chat/stream", json={"conversation_id": "webui:s1", "text": "hello"}
    )
    assert response.status_code == 200
    events = _sse_events(response.text)
    kinds = [name for name, _ in events]
    assert kinds[0] == "hello"
    assert kinds[-1] == "done"
    assert "final" in kinds


def test_chat_stream_501_without_app(tmp_path):
    settings = AgentSettings(agent_home=tmp_path, memory_embedding_backend="hash")
    runtime = build_runtime(settings)
    client = TestClient(build_webui_app(runtime=runtime, settings=settings))
    response = client.post("/api/chat/stream", json={"conversation_id": "x", "text": "hi"})
    assert response.status_code == 501


def test_events_route_registered(tmp_path):
    # ``/api/events`` is an infinite SSE loop, so asserting registration (rather
    # than consuming the stream) avoids a hanging read.
    client = _client(_app(tmp_path))
    paths = {getattr(route, "path", None) for route in client.app.routes}
    assert "/api/events" in paths


def test_data_export_and_forget(tmp_path):
    app = _app(tmp_path, data_forget_enabled=True)
    client = _client(app)
    exported = client.get("/api/data/export")
    assert exported.status_code == 200 and isinstance(exported.json(), dict)

    dry = client.post("/api/data/forget").json()
    assert dry["dry_run"] is True and "would_delete" in dry
    confirmed = client.post("/api/data/forget", params={"confirm": "true"}).json()
    assert confirmed["dry_run"] is False and "deleted" in confirmed


def test_data_forget_disabled_is_forbidden(tmp_path):
    client = _client(_app(tmp_path))
    assert client.post("/api/data/forget").status_code == 403


def test_conversation_detail(tmp_path):
    app = _app(tmp_path)
    client = _client(app)
    client.post("/api/chat", json={"conversation_id": "webui:c9", "text": "hi"})
    detail = client.get("/api/conversations/webui:c9")
    assert detail.status_code == 200
    assert detail.json()["id"] == "webui:c9"
    assert client.get("/api/conversations/missing").status_code == 404
