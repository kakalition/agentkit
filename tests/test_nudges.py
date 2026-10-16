from __future__ import annotations

from pydantic_ai.messages import ModelRequest, UserPromptPart

from agentkit.db.repositories import Repositories
from agentkit.foundation.application import App
from agentkit.learning import propose_memories
from agentkit.nudges import register_memory_nudges
from agentkit.runtime import Runtime
from agentkit.session import serialize_message


async def _add_user_message(repos: Repositories, conversation_id: str, text: str) -> None:
    await repos.conversations.get_or_create(conversation_id, channel="cli")
    await repos.messages.append(
        conversation_id, [serialize_message(ModelRequest(parts=[UserPromptPart(text)]))]
    )


async def test_propose_memories_queues_for_review(repos: Repositories):
    await _add_user_message(repos, "cli:n", "My name is Ada. I live in Berlin.")
    ids = await propose_memories(repos, conversation_id="cli:n")
    assert ids
    proposed = await repos.memories.proposed()
    assert proposed and {row.status for row in proposed} == {"proposed"}


def test_nudges_off_by_default(runtime: Runtime):
    app = App(name="n", settings=runtime.settings, discover=False)
    app.boot()
    assert register_memory_nudges(app) is None


async def test_nudges_fire_on_cadence(runtime: Runtime, monkeypatch):
    calls: list[str | None] = []

    async def fake(repos, **kwargs):  # noqa: ANN001, ANN003
        calls.append(kwargs.get("conversation_id"))
        return [1]

    monkeypatch.setattr("agentkit.learning.propose_memories", fake)
    settings = runtime.settings.model_copy(update={"memory_nudge_every": 2})
    app = App(name="n", settings=settings, discover=False)
    app.boot()

    from agentkit.foundation.facade import emit

    await emit("turn.end", conversation_id="cli:x")
    await emit("turn.end", conversation_id="cli:x")
    assert calls == ["cli:x"]
    await emit("turn.end", conversation_id="cli:x")
    assert calls == ["cli:x"]
    await emit("turn.end", conversation_id="cli:x")
    assert calls == ["cli:x", "cli:x"]
