from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from agentkit.app import AgentApp
from agentkit.config import AgentSettings


async def test_agent_app_runs_turn(tmp_path):
    model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("hi there")]))
    agent = Agent(model, output_type=str)
    app = AgentApp.build(
        agent=agent,
        settings=AgentSettings(owner_id="owner", agent_home=tmp_path),
        model=model,
    )
    result = await app.run("hello")
    assert result.output == "hi there"
    assert result.history_length == 2
