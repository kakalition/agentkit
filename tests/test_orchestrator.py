from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agentkit.deps import Deps
from agentkit.orchestrator import Orchestrator


def _specialist() -> Agent[Deps, str]:
    return Agent(name="specialist", deps_type=Deps, output_type=str, instructions="specialist")


def test_add_specialist_registers_tool():
    orchestrator = Orchestrator(name="orch", instructions="route")
    orchestrator.add_specialist(
        _specialist(), tool_name="handle_things", description="handle things"
    )
    tools = set(orchestrator.agent._function_toolset.tools.keys())
    assert "handle_things" in tools


def _has_tool_return(messages: list[ModelMessage]) -> bool:
    return any(
        isinstance(part, ToolReturnPart)
        for message in messages
        for part in getattr(message, "parts", [])
    )


async def test_orchestrator_delegates(deps: Deps):
    orchestrator = Orchestrator(name="orch", instructions="route")
    orchestrator.add_specialist(_specialist(), tool_name="handle_things", description="x")

    def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        names = {tool.name for tool in info.function_tools}
        if "handle_things" in names:
            if _has_tool_return(messages):
                return ModelResponse(parts=[TextPart("routed")])
            return ModelResponse(parts=[ToolCallPart("handle_things", {"request": "do it"})])
        return ModelResponse(parts=[TextPart("specialist reply")])

    deps.model = FunctionModel(model_fn)
    result = await orchestrator.agent.run("please do it", deps=deps, model=deps.model)
    assert result.output == "routed"
