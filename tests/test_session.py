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
