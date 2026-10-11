from __future__ import annotations

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agentkit.approvals import approval_capability
from agentkit.deps import Deps


def _has_tool_return(messages: list[ModelMessage]) -> bool:
    return any(
        isinstance(part, ToolReturnPart)
        for message in messages
        for part in getattr(message, "parts", [])
    )


def _agent() -> Agent[Deps, str]:
    agent = Agent(
        name="approval",
        deps_type=Deps,
        output_type=str,
        instructions="x",
        capabilities=[approval_capability],
    )

    @agent.tool(requires_approval=True)
    async def dangerous(ctx: RunContext[Deps], value: str) -> str:
        ctx.deps.extras["done"] = value
        return "done"

    return agent


def _model() -> FunctionModel:
    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if _has_tool_return(messages):
            return ModelResponse(parts=[TextPart("ok")])
        return ModelResponse(parts=[ToolCallPart("dangerous", {"value": "x"})])

    return FunctionModel(fn)


async def test_denied_without_callback(deps: Deps):
    deps.model = _model()
    await _agent().run("go", deps=deps, model=deps.model)
    assert "done" not in deps.extras


async def test_approved_by_callback(deps: Deps):
    async def approve(requests):
        return {request.tool_call_id: True for request in requests}

    deps.approve = approve
    deps.model = _model()
    await _agent().run("go", deps=deps, model=deps.model)
    assert deps.extras.get("done") == "x"
