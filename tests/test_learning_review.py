from __future__ import annotations

import asyncio
from types import SimpleNamespace

from pydantic_ai.messages import ModelRequest, UserPromptPart
from typer.testing import CliRunner

from agentkit.cli import app as cli_app
from agentkit.config import get_settings
from agentkit.db.repositories import Repositories
from agentkit.learning import (
    approve_lesson,
    lessons_digest,
    proposed_lessons,
    reflect,
    reject_lesson,
)
from agentkit.runtime import build_runtime, repositories
from agentkit.session import serialize_message


async def _seed(repos: Repositories, texts: list[str], conversation_id: str = "conv1") -> None:
    await repos.conversations.get_or_create(conversation_id)
    payloads = [
        serialize_message(ModelRequest(parts=[UserPromptPart(content=text)])) for text in texts
    ]
    await repos.messages.append(conversation_id, payloads)


_REVIEW = SimpleNamespace(learning_require_review=True)


async def test_review_gating_keeps_lessons_proposed(repos):
    await _seed(repos, ["Always refill the water bowl each morning."])
    summary = await reflect(repos, settings=_REVIEW)
    assert summary["lessons"] >= 1

    # proposed lessons are hidden from the active listing and the digest
    assert await repos.memories.list(kind="procedural") == []
    proposed = await proposed_lessons(repos)
    assert proposed and all(row.status == "proposed" for row in proposed)
    assert await lessons_digest(repos) is None

    lesson_id = proposed[0].id
    assert await approve_lesson(repos, lesson_id) is True
    assert await proposed_lessons(repos) == []
    digest = await lessons_digest(repos)
    assert digest is not None and "water bowl" in digest


async def test_reject_lesson_is_never_applied(repos):
    await _seed(repos, ["Always refill the water bowl each morning."])
    await reflect(repos, settings=_REVIEW)
    proposed = await proposed_lessons(repos)
    assert proposed
    assert await reject_lesson(repos, proposed[0].id) is True
    assert await proposed_lessons(repos) == []
    assert await repos.memories.list(kind="procedural") == []
    assert await lessons_digest(repos) is None
    # the rejected row is retained for audit
    rejected = await repos.memories.list(kind="procedural", status="rejected")
    assert len(rejected) == 1


async def test_active_by_default_when_review_off(repos):
    await _seed(repos, ["Always refill the water bowl each morning."])
    await reflect(repos)
    active = await repos.memories.list(kind="procedural")
    assert active and active[0].status == "active"
    assert await proposed_lessons(repos) == []


def test_cli_review_approve(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MEMORY_EMBEDDING_BACKEND", "hash")
    get_settings.cache_clear()

    runtime = build_runtime(get_settings())
    captured: dict[str, int] = {}

    async def _seed_lesson() -> None:
        async with repositories(runtime) as repos:
            row = await repos.memories.add(
                "Always water the plants.", kind="procedural", status="proposed"
            )
            captured["id"] = int(row.id)

    asyncio.run(_seed_lesson())

    runner = CliRunner()
    listed = runner.invoke(cli_app, ["learning:lessons", "--status", "proposed"])
    assert listed.exit_code == 0
    assert "water the plants" in listed.output

    approved = runner.invoke(cli_app, ["learning:review", "approve", str(captured["id"])])
    assert approved.exit_code == 0, approved.output

    active = runner.invoke(cli_app, ["learning:lessons"])
    assert "water the plants" in active.output
    get_settings.cache_clear()
