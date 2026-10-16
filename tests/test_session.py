from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from agentkit.db.repositories import Repositories
from agentkit.deps import Deps
from agentkit.runtime import Runtime
from agentkit.session import ChatRunner


async def test_chatrunner_persists_history(runtime: Runtime, repos: Repositories):
    agent = Agent(name="a", deps_type=Deps, output_type=str, instructions="x")
    deps = Deps(
        settings=runtime.settings,
        repos=repos,
        model=FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("hi")])),
    )
    runner = ChatRunner(deps, agent=agent, conversation_id="cli:test")
    result = await runner.send("hello")
    assert result.output == "hi"
    assert result.history_length == 2
    assert len(await repos.messages.list("cli:test")) == 2

    second = await runner.send("again")
    assert second.history_length == 4
    assert len(await repos.messages.list("cli:test")) == 4


def _agent() -> Agent:
    return Agent(
        name="a",
        deps_type=Deps,
        output_type=str,
        instructions="x",
    )


async def test_chatrunner_ephemeral_writes_nothing(runtime: Runtime, repos: Repositories):
    deps = Deps(
        settings=runtime.settings,
        repos=repos,
        model=FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("hi")])),
    )
    runner = ChatRunner(deps, agent=_agent(), conversation_id="cli:temp", persist=False)
    result = await runner.send("hello")
    assert result.output == "hi"
    assert await repos.conversations.get("cli:temp") is None
    assert await repos.messages.list("cli:temp") == []
    assert deps.extras["ephemeral"] is True


def test_usage_totals_includes_context_fields(runtime: Runtime, repos: Repositories):
    from types import SimpleNamespace

    deps = Deps(settings=runtime.settings, repos=repos)
    runner = ChatRunner(deps, agent=_agent(), conversation_id="cli:telemetry")
    totals = runner._usage_totals(
        SimpleNamespace(
            requests=1, request_tokens=10, response_tokens=5, total_tokens=15, cache_read_tokens=3
        )
    )
    assert totals is not None
    assert totals["cache_read_tokens"] == 3
    assert totals["context_tokens"] == 10
    assert totals["context_window"] is None
    assert "cost_usd" in totals


def test_memory_writes_suppressed_when_ephemeral(runtime: Runtime):
    from agentkit.memory import _writable

    persistent = Deps(settings=runtime.settings, repos=None)
    temporary = Deps(settings=runtime.settings, repos=None, extras={"ephemeral": True})
    assert _writable(persistent) is True
    assert _writable(temporary) is False
