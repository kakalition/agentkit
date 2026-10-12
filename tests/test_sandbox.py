from __future__ import annotations

import sys

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agentkit import Agent, App, Sandbox, SandboxError
from agentkit.runtime import Runtime


async def test_sandbox_read_write_list(tmp_path):
    box = Sandbox(tmp_path)
    assert await box.write("sub/note.txt", "hello") == "sub/note.txt"
    assert await box.read("sub/note.txt") == "hello"
    assert await box.exists("sub/note.txt") is True
    assert await box.list(".") == ["sub"]
    assert await box.list("sub") == ["sub/note.txt"]
    with pytest.raises((FileNotFoundError, SandboxError)):
        await box.read("missing.txt")


async def test_sandbox_confines_paths(tmp_path):
    box = Sandbox(tmp_path)
    with pytest.raises((FileNotFoundError, SandboxError, ValueError)):
        await box.read("../escape.txt")


async def test_sandbox_read_only(tmp_path):
    box = Sandbox(tmp_path, read_only=True)
    with pytest.raises(SandboxError):
        await box.write("x.txt", "nope")


async def test_sandbox_run_command(tmp_path):
    box = Sandbox(tmp_path)
    result = await box.run([sys.executable, "-c", "print('hi')"])
    assert result.exit_code == 0
    assert "hi" in result.stdout

    failing = await box.run([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert failing.exit_code == 3


async def test_builder_workspace_tools(tmp_path, runtime: Runtime):
    box = Sandbox(tmp_path)
    app = App(name="ws", settings=runtime.settings, discover=False)
    app._runtime = runtime

    def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        for message in messages:
            for part in getattr(message, "parts", []):
                if isinstance(part, ToolReturnPart):
                    return ModelResponse(parts=[TextPart(str(part.content))])
        return ModelResponse(
            parts=[ToolCallPart("write_file", {"path": "a.txt", "content": "data"})]
        )

    app._model = FunctionModel(model_fn)
    agent = Agent.make("ws").instructions("x").workspace(box).output(str).build()
    tools = set(agent._function_toolset.tools.keys())
    assert {"read_file", "write_file", "list_files", "run_command"} <= tools

    app.agent(agent)
    app.boot()
    result = await app.run("save data")
    assert result.tool_calls == ["write_file"]
    assert (tmp_path / "a.txt").read_text() == "data"
