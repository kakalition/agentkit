"""WS3.5 — model fallback chains."""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent as PydanticAgent
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.function import FunctionModel

from agentkit.config import build_model
from agentkit.runtime import Runtime


def _boom(messages: Any, info: Any) -> ModelResponse:  # noqa: ANN001, ARG001
    raise ModelAPIError("primary", "primary is down")


def _ok(messages: Any, info: Any) -> ModelResponse:  # noqa: ANN001, ARG001
    return ModelResponse(parts=[TextPart("secondary")])


async def test_fallback_model_advances_on_error() -> None:
    model = FallbackModel(FunctionModel(_boom), FunctionModel(_ok))
    agent: PydanticAgent[Any, str] = PydanticAgent(model, output_type=str)
    result = await agent.run("hi")
    assert result.output == "secondary"


async def test_build_model_wraps_fallbacks(runtime: Runtime, monkeypatch: Any) -> None:
    from agentkit import model_providers

    models = {"primary": FunctionModel(_boom), "backup": FunctionModel(_ok)}
    monkeypatch.setattr(
        model_providers, "resolve_model", lambda name, settings=None: models[name]
    )
    settings = runtime.settings.model_copy(
        update={"model_name": "primary", "model_fallbacks": ["backup"]}
    )
    model = build_model(settings)
    assert isinstance(model, FallbackModel)
    agent: PydanticAgent[Any, str] = PydanticAgent(model, output_type=str)
    result = await agent.run("hi")
    assert result.output == "secondary"


def test_build_model_without_fallbacks_is_unchanged(runtime: Runtime, monkeypatch: Any) -> None:
    from agentkit import model_providers

    primary = FunctionModel(_ok)
    monkeypatch.setattr(model_providers, "resolve_model", lambda name, settings=None: primary)
    model = build_model(runtime.settings)
    assert model is primary


async def test_chat_result_records_model_used(runtime: Runtime) -> None:
    from agentkit import App
    from agentkit.foundation.agent import Agent

    app = App(name="fb", settings=runtime.settings, discover=False)
    app._runtime = runtime
    app._model = FallbackModel(FunctionModel(_boom), FunctionModel(_ok))
    app.agent(Agent.make("fb").instructions("x").output(str))
    app.boot()
    result = await app.run("hi")
    assert result.output == "secondary"
    assert result.model
