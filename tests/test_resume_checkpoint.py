"""WS2.2 — branch/restore a conversation from a stored checkpoint."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from agentkit import Agent, App
from agentkit.errors import ConfigurationError, NotFound
from agentkit.runtime import Runtime


def _app(runtime: Runtime, *, checkpoints: bool = True) -> App:
    update: dict[str, Any] = {"checkpoints_enabled": checkpoints, "checkpoint_retention": 50}
    settings = runtime.settings.model_copy(update=update)
    app = App(name="cp", settings=settings, discover=False)
    app._runtime = runtime
    app._model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("ok")]))  # noqa: ARG005
    app.agent(Agent.make("cp").instructions("x").output(str))
    app.boot()
    return app


async def _message_count(app: App, conversation_id: str) -> int:
    async with app.repositories() as repos:
        return len(await repos.messages.list(conversation_id))


async def test_restore_in_place_reproduces_prior_turns(runtime: Runtime) -> None:
    app = _app(runtime)
    await app.run("one", conversation_id="cli:a")
    after_one = await _message_count(app, "cli:a")
    await app.run("two", conversation_id="cli:a")
    assert await _message_count(app, "cli:a") > after_one

    destination = await app.resume_from_checkpoint("cli:a")
    assert destination == "cli:a"
    assert await _message_count(app, "cli:a") == after_one


async def test_branch_writes_a_new_conversation(runtime: Runtime) -> None:
    app = _app(runtime)
    await app.run("one", conversation_id="cli:a")
    after_one = await _message_count(app, "cli:a")
    await app.run("two", conversation_id="cli:a")

    destination = await app.resume_from_checkpoint("cli:a", target="cli:b")
    assert destination == "cli:b"
    assert await _message_count(app, "cli:b") == after_one
    # the source conversation is untouched by a branch
    assert await _message_count(app, "cli:a") > after_one


async def test_resume_unknown_conversation_raises(runtime: Runtime) -> None:
    app = _app(runtime)
    with pytest.raises(NotFound):
        await app.resume_from_checkpoint("cli:missing")


async def test_resume_requires_checkpoints_enabled(runtime: Runtime) -> None:
    app = _app(runtime, checkpoints=False)
    with pytest.raises(ConfigurationError):
        await app.resume_from_checkpoint("cli:a")
