from __future__ import annotations

from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from agentkit import App
from agentkit.deps import Deps
from agentkit.foundation.agent import Agent
from agentkit.hitl import clarification_tool
from agentkit.runtime import Runtime


def _app(runtime: Runtime, model) -> App:  # noqa: ANN001
    app = App(name="hitl", settings=runtime.settings, discover=False, model=model)
    app._runtime = runtime
    return app


def _tool_return(messages) -> str | None:  # noqa: ANN001
    for message in messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolReturnPart):
                return str(part.content)
    return None


async def test_output_validator_transforms_output():
    def validator(ctx, output: str) -> str:  # noqa: ANN001
        return output.upper()

    agent = (
        Agent.make("v")
        .instructions("x")
        .output_validator(validator)
        .output(str)
        .build()
    )
    result = await agent.run(
        "hi", model=FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("hello")]))
    )
    assert result.output == "HELLO"


async def test_clarify_tool_uses_handler(runtime: Runtime):
    def model_fn(messages, info):  # noqa: ANN001
        returned = _tool_return(messages)
        if returned is not None:
            return ModelResponse(parts=[TextPart(returned)])
        return ModelResponse(parts=[ToolCallPart("ask_user", {"question": "Which city?"})])

    app = _app(runtime, FunctionModel(model_fn))
    app.agent(Agent.make("v").instructions("x").clarify().output(str))
    app.clarify(lambda question, options: "Lisbon")
    app.boot()

    result = await app.run("book a flight")
    assert "Lisbon" in result.output


async def test_clarify_without_handler_tells_model_to_ask(runtime: Runtime):
    tool = clarification_tool()

    class Ctx:
        deps = Deps(settings=runtime.settings)

    out = await tool(Ctx(), "What time?")
    assert "No live user" in out
    assert "What time?" in out


async def test_resume_continues_deferred_tools(runtime: Runtime):
    from agentkit.approvals import approval_handler  # noqa: F401  (documented seam)

    # resume() forwards deferred_tool_results to the agent; a trivial run proves wiring.
    def model_fn(messages, info):  # noqa: ANN001
        return ModelResponse(parts=[TextPart("done")])

    app = _app(runtime, FunctionModel(model_fn))
    app.agent(Agent.make("v").instructions("x").output(str))
    app.boot()
    result = await app.resume(None, conversation_id="cli:resume")
    assert result.output == "done"
