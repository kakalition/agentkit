from __future__ import annotations

import asyncio
import json

import httpx
from typer.testing import CliRunner

from agentkit.cli import app as cli_app
from agentkit.config import AgentSettings, get_settings
from agentkit.runtime import repositories
from agentkit.webhooks import WebhookDispatcher, sign


def test_sign_is_deterministic_hmac():
    sig = sign("secret", b'{"a":1}')
    assert sig.startswith("sha256=")
    assert sig == sign("secret", b'{"a":1}')
    assert sig != sign("other", b'{"a":1}')


async def _seed_hook(runtime, **kwargs) -> None:
    async with repositories(runtime) as repos:
        await repos.webhooks.add("http://hook.local/x", **kwargs)


def test_dispatcher_delivers_and_logs(runtime):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(runtime, client=client, backoff_base=0)

    asyncio.run(_seed_hook(runtime, events=["turn.end"], secret="s3cr3t"))
    results = asyncio.run(dispatcher.emit("turn.end", {"conversation_id": "c1"}))

    assert results == [{"webhook_id": 1, "event": "turn.end", "status": "ok", "attempts": 1}]
    assert seen[0].headers["x-agentkit-event"] == "turn.end"
    assert seen[0].headers["x-agentkit-signature"].startswith("sha256=")
    assert json.loads(seen[0].content)["data"]["conversation_id"] == "c1"

    async def _deliveries():
        async with repositories(runtime) as repos:
            return await repos.webhook_deliveries.list()

    rows = asyncio.run(_deliveries())
    assert rows and rows[0].status == "ok"


def test_dispatcher_matches_and_retries(runtime):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(runtime, client=client, max_attempts=3, backoff_base=0)
    asyncio.run(_seed_hook(runtime, events=["db.create"]))

    # a non-subscribed event is ignored
    assert asyncio.run(dispatcher.emit("turn.end", {})) == []

    results = asyncio.run(dispatcher.emit("db.create", {"model": "note"}))
    assert results[0]["status"] == "failed"
    assert results[0]["attempts"] == 3
    assert calls["n"] == 3


def test_cli_webhook_add_list_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MEMORY_EMBEDDING_BACKEND", "hash")
    get_settings.cache_clear()
    runner = CliRunner()

    added = runner.invoke(cli_app, ["webhook", "add", "http://hook.local/x", "--events", "turn.end"])
    assert added.exit_code == 0, added.output
    listed = runner.invoke(cli_app, ["webhook", "list"])
    assert listed.exit_code == 0
    assert "http://hook.local/x" in listed.output

    deleted = runner.invoke(cli_app, ["webhook", "delete", "1"])
    assert deleted.exit_code == 0, deleted.output
    assert runner.invoke(cli_app, ["webhook", "list"]).output.strip() == "(no webhooks)"
    get_settings.cache_clear()


def test_fullstack_registers_webhooks(tmp_path):
    from agentkit.foundation import App

    settings = AgentSettings(
        owner_id="owner",
        agent_home=tmp_path,
        memory_embedding_backend="hash",
        webhooks_enabled=True,
    )
    app = App(name="wh", settings=settings, discover=False)
    app.fullstack().boot()
    assert getattr(app, "_webhook_dispatcher", None) is not None
