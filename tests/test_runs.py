from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic_ai import Agent as PydanticAgent
from pydantic_ai.models.test import TestModel

from agentkit.config import AgentSettings
from agentkit.deps import Deps
from agentkit.foundation import App
from agentkit.runs import (
    InMemoryRecorder,
    RepositoryRunRecorder,
    RunEvent,
    recorder_for,
)
from agentkit.runtime import repositories
from agentkit.webui.app import build_webui_app


def _app(tmp_path) -> App:
    settings = AgentSettings(agent_home=tmp_path, memory_embedding_backend="hash")
    app = App("runs", settings=settings, discover=False, model=TestModel())
    app.boot()
    app.agent(PydanticAgent(TestModel(), output_type=str, deps_type=Deps, instructions="hi"))
    return app


def test_recorder_assigns_seq_and_copies_run_id():
    recorder = InMemoryRecorder("run-1")
    event = recorder.record(RunEvent(kind="start", text="hi"))
    assert event.seq == 0 and event.run_id == "run-1"
    assert recorder.emit("final", text="done").seq == 1


async def test_repository_recorder_flushes(runtime):
    async with repositories(runtime) as repos:
        recorder = RepositoryRunRecorder(repos.run_events, "flush-run")
        recorder.emit("start", text="hi")
        recorder.emit("final", text="done")
        await recorder.flush()
        assert recorder.events == []
        events = await repos.run_events.events("flush-run")
        assert [event.kind for event in events] == ["start", "final"]


def test_recorder_for_disabled_is_in_memory():
    class _Repos:
        run_events = object()

    assert isinstance(recorder_for(_Repos(), "r", enabled=False), InMemoryRecorder)


async def test_app_run_persists_run_events(tmp_path):
    app = _app(tmp_path)
    await app.run("hello", conversation_id="runs:c1")
    async with app.repositories() as repos:
        runs = await repos.run_events.list_runs()
        assert any(run["run_id"] == "runs:c1" for run in runs)
        events = await repos.run_events.events("runs:c1")
    kinds = [event.kind for event in events]
    assert kinds[0] == "start"
    assert "final" in kinds


def test_runs_endpoints(tmp_path):
    app = _app(tmp_path)
    client = TestClient(
        build_webui_app(runtime=app.runtime, settings=app.settings, app=app, answer=app.answer)
    )
    client.post("/api/chat", json={"conversation_id": "webui:r1", "text": "hi"})
    runs = client.get("/api/studio/runs").json()["runs"]
    assert any(run["run_id"] == "webui:r1" for run in runs)
    detail = client.get("/api/studio/runs/webui:r1").json()
    assert detail["events"]


def test_score_run_endpoint(tmp_path):
    app = _app(tmp_path)
    client = TestClient(
        build_webui_app(runtime=app.runtime, settings=app.settings, app=app, answer=app.answer)
    )
    client.post("/api/chat", json={"conversation_id": "webui:s1", "text": "hi"})
    response = client.post("/api/studio/runs/webui:s1/score", json={"grader": "trace"})
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "webui:s1"
    assert "score" in body
    assert body["record_id"] is not None


def test_inspect_app_reports_new_drivers(tmp_path):
    app = _app(tmp_path)
    client = TestClient(
        build_webui_app(runtime=app.runtime, settings=app.settings, app=app, answer=app.answer)
    )
    body = client.get("/api/studio/app").json()
    assert body["vector"]["driver"] == "repository"
    assert body["dataset"]["driver"] == "repository"
    assert body["working_memory"]["driver"] == "memory"
    assert "vector" in body["drivers"]
