from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from agentkit import scheduler
from agentkit.config import AgentSettings
from agentkit.runtime import build_runtime, repositories
from agentkit.session import ChatResult, serialize_message
from agentkit.webui.app import build_webui_app
from agentkit.webui.introspect import messages_view


@pytest.fixture(autouse=True)
def _reset_scheduler():
    old = scheduler._runtime
    scheduler._runtime = None
    yield
    scheduler._runtime = old


async def _stub_answer(conversation_id: str, text: str, *, actor=None) -> ChatResult:
    return ChatResult(
        output=f"echo:{text}", artifacts=[{"kind": "note", "path": "x"}],
        history_length=2, usage={"total_tokens": 7},
    )


@pytest.fixture
def client(tmp_path):
    import asyncio

    settings = AgentSettings(
        owner_id="owner",
        agent_name="tester",
        agent_home=tmp_path,
        openai_api_key="sk-secret",
        libsql_auth_token="secret-token",
    )
    runtime = build_runtime(settings)

    async def _seed() -> None:
        async with repositories(runtime) as repos:
            await repos.conversations.get_or_create("webui:default", channel="webui")
            await repos.messages.append(
                "webui:default",
                [
                    serialize_message(ModelRequest(parts=[UserPromptPart(content="hi there")])),
                    serialize_message(ModelResponse(parts=[TextPart(content="hello!")])),
                ],
            )
            await repos.usage.add(conversation_id="webui:default", requests=1, total_tokens=5)
            await repos.audit.append("test.action", target="thing")
            await repos.a2a.upsert("t1", "owner", "ctx", "working", '{"x": 1}')
            await repos.schedules.upsert("job1", kind="cron", schedule="* * * * *", task="noop")

    asyncio.run(_seed())
    (settings.artifacts_dir / "report.txt").write_text("artifact-body")

    scheduler.task("noop")(lambda **_: None)
    app = build_webui_app(runtime=runtime, settings=settings, answer=_stub_answer)
    return TestClient(app)


def test_info_and_health(client):
    info = client.get("/api/info").json()
    assert info["name"] == "tester"
    assert info["chat_enabled"] is True
    assert "user:pass" not in info["database_url"]
    assert info["webui"]["enabled"] is True

    health = client.get("/api/health").json()
    assert health["ok"] is True


def test_conversations_and_messages(client):
    listing = client.get("/api/conversations").json()["conversations"]
    assert listing and listing[0]["id"] == "webui:default"
    assert listing[0]["message_count"] == 2

    detail = client.get("/api/conversations/webui:default").json()
    assert detail["channel"] == "webui"

    messages = client.get("/api/conversations/webui:default/messages").json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["parts"][0]["text"] == "hi there"
    assert messages[1]["parts"][0]["text"] == "hello!"


def test_clear_messages(client):
    assert client.delete("/api/conversations/webui:default/messages").json()["cleared"] is True
    assert client.get("/api/conversations/webui:default/messages").json()["messages"] == []


def test_usage_audit_a2a(client):
    usage = client.get("/api/usage").json()
    assert usage["totals"]["total_tokens"] == 5
    assert usage["recent"][0]["conversation_id"] == "webui:default"

    audit = client.get("/api/audit").json()["entries"]
    assert audit[0]["action"] == "test.action"
    assert client.get("/api/audit/verify").json()["ok"] is True

    tasks = client.get("/api/a2a").json()["tasks"]
    assert tasks[0]["id"] == "t1"
    assert client.get("/api/a2a/t1").json()["payload"] == {"x": 1}
    assert client.get("/api/a2a/missing").status_code == 404


def test_scheduler_crud(client):
    listed = client.get("/api/schedules").json()
    assert listed["jobs"][0]["name"] == "job1"
    assert "noop" in listed["tasks"]

    created = client.post(
        "/api/schedules",
        json={"name": "job2", "kind": "cron", "schedule": "0 8 * * *", "task": "noop"},
    )
    assert created.status_code == 201

    patched = client.patch("/api/schedules/job2", json={"enabled": False})
    assert patched.status_code == 200
    jobs = {j["name"]: j for j in client.get("/api/schedules").json()["jobs"]}
    assert jobs["job2"]["enabled"] is False

    assert client.delete("/api/schedules/job2").json()["removed"] is True
    assert client.delete("/api/schedules/job2").status_code == 404


def test_scheduler_rejects_unknown_task(client):
    response = client.post(
        "/api/schedules", json={"name": "bad", "kind": "cron", "schedule": "* * * * *", "task": "nope"}
    )
    assert response.status_code == 400


def test_scheduler_rejects_bad_cron(client):
    response = client.post(
        "/api/schedules",
        json={"name": "bad", "kind": "cron", "schedule": "not a cron", "task": "noop"},
    )
    assert response.status_code == 400


def test_soul_read_write(client):
    initial = client.get("/api/soul").json()
    assert initial["exists"] is False

    saved = client.put("/api/soul", json={"text": "# new soul"}).json()
    assert saved["saved"] is True
    assert client.get("/api/soul").json()["text"] == "# new soul"


def test_config_masks_secrets(client):
    config = client.get("/api/config").json()["config"]
    assert config["openai_api_key"] == "***"
    assert config["libsql_auth_token"] == "***"
    assert config["db_path"].endswith("agent.db")


def test_mask_url_strips_credentials():
    from agentkit.webui.config_api import config_view, mask_url

    assert mask_url("postgres://user:pass@host:5432/db") == "postgres://host:5432/db"
    assert mask_url("sqlite+libsql:///tmp/x.db") == "sqlite+libsql:///tmp/x.db"

    settings = AgentSettings(
        agent_name="m", database_url="postgres://u:p@db.example/app", openai_api_key="sk-x"
    )
    view = config_view(settings)
    assert view["database_url"] == "postgres://db.example/app"
    assert view["openai_api_key"] == "***"


def test_artifacts_list_and_download(client):
    listing = client.get("/api/artifacts").json()["artifacts"]
    assert listing[0]["path"] == "report.txt"

    download = client.get("/api/artifacts/report.txt")
    assert download.status_code == 200
    assert download.text == "artifact-body"


def test_artifact_path_traversal_blocked(client):
    assert client.get("/api/artifacts/..%2Fagent.db").status_code in (400, 404)


def test_chat_endpoint(client):
    response = client.post("/api/chat", json={"conversation_id": "webui:default", "text": "yo"})
    assert response.status_code == 200
    body = response.json()
    assert body["output"] == "echo:yo"
    assert body["usage"] == {"total_tokens": 7}


def test_chat_disabled_when_no_answer(tmp_path):
    settings = AgentSettings(agent_home=tmp_path, agent_name="quiet")
    runtime = build_runtime(settings)
    app = build_webui_app(runtime=runtime, settings=settings, answer=None)
    client = TestClient(app)
    assert client.get("/api/info").json()["chat_enabled"] is False
    assert client.post("/api/chat", json={"text": "hi"}).status_code == 501


def test_root_serves_fallback_when_unbuilt(tmp_path, monkeypatch):
    import agentkit.webui.app as app_module

    monkeypatch.setattr(app_module, "_static_candidates", lambda: [])
    settings = AgentSettings(agent_home=tmp_path, agent_name="unbuilt")
    runtime = build_runtime(settings)
    client = TestClient(build_webui_app(runtime=runtime, settings=settings))
    response = client.get("/")
    assert response.status_code == 200
    assert "agentkit web UI" in response.text


def test_spa_route_served_when_built(tmp_path, monkeypatch):
    import agentkit.webui.app as app_module

    build = tmp_path / "dist"
    (build / "assets").mkdir(parents=True)
    (build / "index.html").write_text("<html><body>SPA</body></html>")
    (build / "assets" / "app.js").write_text("console.log(1)")
    monkeypatch.setattr(app_module, "_static_candidates", lambda: [build])

    settings = AgentSettings(agent_home=tmp_path, agent_name="built")
    runtime = build_runtime(settings)
    client = TestClient(build_webui_app(runtime=runtime, settings=settings))
    assert "SPA" in client.get("/").text
    assert "SPA" in client.get("/workflows").text
    assert client.get("/assets/app.js").text == "console.log(1)"


def test_messages_view_tolerates_bad_payload():
    assert messages_view(["not json"]) == []


def test_run_all_appends_webui(monkeypatch, tmp_path):
    import agentkit.webui.server as server
    from agentkit.supervise import Service, run_all

    settings = AgentSettings(agent_home=tmp_path, agent_name="svc", webui_enabled=True)
    ran = threading.Event()
    stop = threading.Event()

    monkeypatch.setattr(server, "serve_webui", lambda **kwargs: ran.set())

    def hold():
        ran.wait(3)
        stop.set()

    run_all([Service("hold", hold)], settings=settings, stop_event=stop)
    assert ran.is_set()


def test_run_all_skips_webui_when_disabled(monkeypatch, tmp_path):
    import time

    import agentkit.webui.server as server
    from agentkit.supervise import Service, run_all

    settings = AgentSettings(agent_home=tmp_path, agent_name="svc", webui_enabled=False)
    started = threading.Event()
    stop = threading.Event()
    monkeypatch.setattr(server, "serve_webui", lambda **kw: started.set())

    def once():
        time.sleep(0.3)
        stop.set()

    run_all([Service("once", once)], settings=settings, stop_event=stop)
    assert not started.is_set()
