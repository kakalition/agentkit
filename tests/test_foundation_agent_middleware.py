"""WS1.1 — agent (model/tool) middleware hooks are wired to PydanticAI."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from agentkit import Agent
from agentkit.foundation.agent_middleware import (
    AgentCallContext,
    AgentMiddlewareCapability,
    BaseAgentMiddleware,
    LoggingMiddleware,
    NoopMiddleware,
)
from agentkit.runtime import Runtime


def _tool_model(messages: list[Any], info: Any) -> ModelResponse:  # noqa: ARG001
    returned = any(
        isinstance(part, ToolReturnPart)
        for message in messages
        for part in getattr(message, "parts", [])
    )
    if not returned:
        return ModelResponse(parts=[ToolCallPart("echo", {"text": "hi"})])
    return ModelResponse(parts=[TextPart("done")])


async def echo(ctx: RunContext[Any], text: str) -> str:
    """Echo the text back."""
    return f"echo:{text}"


def test_noop_default_adds_no_capability() -> None:
    builder = Agent.make("noop").instructions("x").output(str)
    assert builder._agent_middleware_hooks() is None


def test_explicit_noop_is_treated_as_default() -> None:
    builder = Agent.make("noop").agent_middleware(NoopMiddleware())
    assert builder._agent_middleware_hooks() is None


def test_explicit_middleware_produces_hooks() -> None:
    builder = Agent.make("mw").agent_middleware(LoggingMiddleware())
    hooks = builder._agent_middleware_hooks()
    assert hooks is not None


async def test_wrap_model_order_and_mutation() -> None:
    order: list[str] = []

    class Tagged(BaseAgentMiddleware):
        def __init__(self, tag: str) -> None:
            self.tag = tag

        async def before_model(self, ctx: Any) -> None:
            order.append(f"before:{self.tag}")

        async def after_model(self, ctx: Any, response: Any) -> Any:
            order.append(f"after:{self.tag}")
            return f"{response}{self.tag}"

        async def wrap_model_call(self, ctx: Any, call_next: Any) -> Any:
            order.append(f"wrap:{self.tag}")
            return await call_next()

    hooks = AgentMiddlewareCapability([Tagged("a"), Tagged("b")]).hooks()

    async def handler(request_context: Any) -> Any:
        return request_context

    out = await hooks.wrap_model_request(
        object(), request_context="R", handler=handler
    )
    assert order == [
        "before:a",
        "before:b",
        "wrap:a",
        "wrap:b",
        "after:b",
        "after:a",
    ]
    assert out == "Rba"


async def test_wrap_tool_args_and_result_mutation() -> None:
    class UpperArgs(BaseAgentMiddleware):
        async def before_tool(self, ctx: Any, name: str, args: Any) -> Any:
            return {key: str(value).upper() for key, value in args.items()}

    class AddResult(BaseAgentMiddleware):
        async def after_tool(self, ctx: Any, name: str, result: Any) -> Any:
            return f"{result}!"

    hooks = AgentMiddlewareCapability([UpperArgs(), AddResult()]).hooks()

    async def handler(args: dict[str, Any]) -> Any:
        return args["text"]

    out = await hooks.wrap_tool_execute(
        object(),
        call=SimpleNamespace(tool_name="echo"),
        tool_def=SimpleNamespace(name="echo"),
        args={"text": "hi"},
        handler=handler,
    )
    assert out == "HI!"


async def test_wrap_tool_short_circuit_denies() -> None:
    class Denier(BaseAgentMiddleware):
        async def wrap_tool_call(self, ctx: Any, name: str, call_next: Any) -> Any:
            return "denied"

    hooks = AgentMiddlewareCapability([Denier()]).hooks()
    called = False

    async def handler(args: Any) -> Any:
        nonlocal called
        called = True
        return "ran"

    out = await hooks.wrap_tool_execute(
        object(),
        call=SimpleNamespace(tool_name="t"),
        tool_def=SimpleNamespace(name="t"),
        args={},
        handler=handler,
    )
    assert out == "denied"
    assert called is False


async def test_ctx_state_is_shared_across_hooks() -> None:
    class Enricher(BaseAgentMiddleware):
        async def wrap_model_call(self, ctx: AgentCallContext, call_next: Any) -> Any:
            ctx.state["seen"] = True
            return await call_next()

    class Reader(BaseAgentMiddleware):
        def __init__(self) -> None:
            self.seen: Any = None

        async def after_model(self, ctx: AgentCallContext, response: Any) -> Any:
            self.seen = ctx.state.get("seen")
            return response

    reader = Reader()
    hooks = AgentMiddlewareCapability([Enricher(), reader]).hooks()

    async def handler(request_context: Any) -> Any:
        return request_context

    await hooks.wrap_model_request(object(), request_context="R", handler=handler)
    assert reader.seen is True


def test_middleware_runs_inside_agent(runtime: Runtime) -> None:
    seen: list[tuple[str, str]] = []

    class Recorder(BaseAgentMiddleware):
        async def before_tool(self, ctx: Any, name: str, args: Any) -> Any:
            seen.append(("before", name))
            return args

        async def after_tool(self, ctx: Any, name: str, result: Any) -> Any:
            seen.append(("after", name))
            return result

    agent = (
        Agent.make("mw", settings=runtime.settings)
        .instructions("x")
        .tool(echo)
        .output(str)
        .model(FunctionModel(_tool_model))
        .agent_middleware(Recorder())
        .build()
    )
    result = agent.run_sync("say hi")
    assert result.output == "done"
    assert ("before", "echo") in seen
    assert ("after", "echo") in seen
