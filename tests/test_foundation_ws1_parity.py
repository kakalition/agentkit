"""WS1.4 — parity & cleanup: stream/resume middleware, +Turn ctx, bug fixes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from agentkit import App, Middleware
from agentkit.agents.tools import _self_name
from agentkit.errors import ConfigurationError
from agentkit.foundation.agent import Agent as _Agent
from agentkit.gateways.base import GatewayError
from agentkit.runtime import Runtime


class Recorder(Middleware):
    def __init__(self, seen: list[str]) -> None:
        self.seen = seen

    async def handle(self, turn: Any, call_next: Any) -> Any:
        self.seen.append(getattr(turn, "conversation_id", "?"))
        result = await call_next()
        self.seen.append("done")
        return result


def _stream_model(chunks: list[str]) -> FunctionModel:
    def stream_fn(messages: Any, info: Any) -> Any:  # noqa: ANN001, ARG001
        async def gen() -> Any:
            for chunk in chunks:
                yield chunk

        return gen()

    def model_fn(messages: Any, info: Any) -> ModelResponse:  # noqa: ANN001, ARG001
        return ModelResponse(parts=[TextPart("".join(chunks))])

    return FunctionModel(function=model_fn, stream_function=stream_fn)


def _app(runtime: Runtime, *, resolver: Any = None) -> App:
    app = App(name="ws1", settings=runtime.settings, discover=False)
    app._runtime = runtime
    model = _stream_model(["o", "k"])
    app._model = model
    app.agent(_Agent.make("ws1").instructions("x").output(str))
    if resolver is not None:
        app.model_resolver(lambda context: resolver(context) or model)
    app.boot()
    return app


async def test_stream_runs_turn_middleware(runtime: Runtime) -> None:
    app = _app(runtime)
    seen: list[str] = []
    app.middleware(Recorder(seen))
    events = [event async for event in app.stream("hi", conversation_id="cli:s")]
    assert seen == ["cli:s", "done"]
    assert events[-1].kind == "final"


async def test_stream_passes_turn_to_model_resolver(runtime: Runtime) -> None:
    contexts: list[Any] = []
    app = _app(runtime, resolver=lambda context: contexts.append(context) or None)
    async for _ in app.stream("hi", conversation_id="cli:s"):
        pass
    assert contexts
    assert contexts[0].conversation_id == "cli:s"


async def test_resume_runs_turn_middleware(runtime: Runtime) -> None:
    app = _app(runtime)
    seen: list[str] = []
    app.middleware(Recorder(seen))
    await app.resume(None, conversation_id="cli:r")
    assert seen == ["cli:r", "done"]


def test_self_name_uses_run_context_agent() -> None:
    ctx = SimpleNamespace(deps=SimpleNamespace(extras={}), agent=SimpleNamespace(name="peer"))
    assert _self_name(ctx) == "peer"


def test_self_name_prefers_explicit_override() -> None:
    deps = SimpleNamespace(extras={"_agent_name": "override"})
    ctx = SimpleNamespace(deps=deps, agent=SimpleNamespace(name="peer"))
    assert _self_name(ctx) == "override"


def test_self_name_without_agent_is_none() -> None:
    ctx = SimpleNamespace(deps=SimpleNamespace(extras={}), agent=None)
    assert _self_name(ctx) is None


def test_gateway_error_is_configuration_error() -> None:
    assert issubclass(GatewayError, ConfigurationError)
    error = GatewayError("Slack needs the 'slack' extra")
    assert error.code == "gateway_error"
