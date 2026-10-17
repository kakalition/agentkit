"""WS3.4 — thread-scoped working memory."""

from __future__ import annotations

from typing import Any

from pydantic_ai.messages import (
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel

from agentkit import Agent, App
from agentkit.runtime import Runtime
from agentkit.working_memory import InMemoryWorkingMemory


async def test_in_memory_isolation_between_namespaces() -> None:
    store = InMemoryWorkingMemory()
    await store.set("thread-a", "plan", "one")
    assert await store.get("thread-a", "plan") == "one"
    assert await store.get("thread-b", "plan") is None
    assert await store.list("thread-a") == {"plan": "one"}
    assert await store.forget("thread-a", "plan") is True
    assert await store.forget("thread-a", "plan") is False
    await store.set("thread-a", "x", "1")
    assert await store.clear("thread-a") == 1


def test_capability_registers_tools(runtime: Runtime) -> None:
    agent = Agent.make("wm", settings=runtime.settings).instructions("x").working_memory().output(str).build()
    names = set(agent._function_toolset.tools.keys())
    assert {"memory_set", "memory_get", "memory_list", "memory_forget"} <= names


def _set_model() -> FunctionModel:
    def fn(messages: Any, info: Any) -> ModelResponse:  # noqa: ANN001, ARG001
        returned = any(
            isinstance(part, (ToolReturnPart, RetryPromptPart))
            for message in messages
            for part in getattr(message, "parts", [])
        )
        if returned:
            return ModelResponse(parts=[TextPart("done")])
        return ModelResponse(parts=[ToolCallPart("memory_set", {"key": "plan", "value": "x"})])

    return FunctionModel(fn)


async def test_repository_driver_persists_across_turns(runtime: Runtime) -> None:
    settings = runtime.settings.model_copy(
        update={"working_memory_enabled": True, "working_memory_driver": "repository"}
    )
    app = App(name="wm", settings=settings, discover=False)
    app._runtime = runtime
    app._model = _set_model()
    app.agent(Agent.make("wm").instructions("x").working_memory().output(str))
    app.boot()
    await app.run("go", conversation_id="cli:wm")

    async with app.repositories() as repos:
        assert await repos.working_memory.get("cli:wm", "plan") == "x"
