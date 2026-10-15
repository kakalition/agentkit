from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelRequest, UserPromptPart
from typer.testing import CliRunner

from agentkit.cli import app as cli_app
from agentkit.config import AgentSettings, get_settings
from agentkit.data import export_owner, forget_owner
from agentkit.runtime import build_runtime, repositories
from agentkit.session import serialize_message
from agentkit.webui.app import build_webui_app


async def _seed(repos) -> None:
    await repos.conversations.get_or_create("c1")
    await repos.messages.append(
        "c1", [serialize_message(ModelRequest(parts=[UserPromptPart(content="hi")]))]
    )
    await repos.memories.add("likes tea", kind="preference")
    await repos.profile.set(name="Ada")
    await repos.knowledge.add("notes", ["one", "two"])
    await repos.usage.add(conversation_id="c1", requests=1, total_tokens=3)
    await repos.feedback.add(rating=1, conversation_id="c1")
    await repos.audit.append("seed.action", target="thing")


async def test_export_bundle(repos):
    await _seed(repos)
    bundle = await export_owner(repos)
    assert bundle["owner_id"] == "owner"
    assert len(bundle["conversations"]) == 1
    assert len(bundle["messages"]) == 1
    assert bundle["memories"]
    assert bundle["owner_profile"]["name"] == "Ada"
    assert len(bundle["knowledge"]) == 2
    assert bundle["feedback"]
    assert bundle["usage"]


async def test_forget_dry_run_then_erase_keeps_audit(repos):
    await _seed(repos)

    dry = await forget_owner(repos, dry_run=True)
    assert dry["dry_run"] is True
    assert dry["would_delete"]["memories"] >= 1
    assert await repos.memories.list() != []

    result = await forget_owner(repos, dry_run=False)
    assert result["dry_run"] is False
    assert result["deleted"]["conversations"] == 1
    assert await repos.memories.list(status=None) == []
    assert await repos.knowledge.list() == []
    assert await repos.profile.get() is None

    entries = await repos.audit.entries()
    assert any(entry.action == "data.forget" for entry in entries)
    assert any(entry.action == "seed.action" for entry in entries)
    assert await repos.audit.verify() is True


def test_webui_data_endpoints_gate(tmp_path):
    settings = AgentSettings(owner_id="owner", agent_home=tmp_path, memory_embedding_backend="hash")
    runtime = build_runtime(settings)
    client = TestClient(build_webui_app(runtime=runtime, settings=settings))

    assert client.get("/api/data/export").status_code == 200
    # forget is opt-in: disabled by default
    assert client.post("/api/data/forget").status_code == 403

    settings.data_forget_enabled = True
    dry = client.post("/api/data/forget").json()
    assert dry["dry_run"] is True


def test_cli_data_export_and_forget_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MEMORY_EMBEDDING_BACKEND", "hash")
    get_settings.cache_clear()

    runtime = build_runtime(get_settings())

    async def _seed_memory() -> None:
        async with repositories(runtime) as repos:
            await repos.memories.add("remember me", kind="fact")

    asyncio.run(_seed_memory())
    runner = CliRunner()

    exported = runner.invoke(cli_app, ["data:export"])
    assert exported.exit_code == 0
    assert "remember me" in exported.output

    dry = runner.invoke(cli_app, ["data:forget"])
    assert dry.exit_code == 0
    assert "would delete" in dry.output

    erased = runner.invoke(cli_app, ["data:forget", "--yes"])
    assert erased.exit_code == 0
    assert "deleted" in erased.output
    get_settings.cache_clear()
