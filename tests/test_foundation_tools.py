"""WS7 — class-based tools and toolkits."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import Agent as PydanticAgent
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from agentkit import Tool, Toolkit
from agentkit.toolkits import TOOLKIT_CLASSES, DatabaseToolkit, toolkit_for


class EchoTool(Tool):
    name = "echo"
    description = "Echo the text back."

    def handle(self, ctx: RunContext[Any], text: str) -> str:  # noqa: ARG002
        return f"echo:{text}"


class EchoToolkit(Toolkit):
    name = "echo"
    tools = [EchoTool]


def _model_fn(messages: list[Any], info: Any) -> ModelResponse:  # noqa: ARG001
    returned = any(
        isinstance(part, ToolReturnPart)
        for message in messages
        for part in getattr(message, "parts", [])
    )
    if not returned:
        return ModelResponse(parts=[ToolCallPart("echo", {"text": "hi"})])
    return ModelResponse(parts=[TextPart("done")])


def test_tool_class_installs_and_runs() -> None:
    agent: PydanticAgent[Any, Any] = PydanticAgent(FunctionModel(_model_fn), output_type=str)
    EchoTool().install(agent)
    result = agent.run_sync("say hi")
    assert result.output == "done"


def test_toolkit_installs_tools() -> None:
    agent: PydanticAgent[Any, Any] = PydanticAgent(FunctionModel(_model_fn), output_type=str)
    EchoToolkit().install(agent)
    result = agent.run_sync("say hi")
    assert result.output == "done"


def test_tool_derives_name_and_description() -> None:
    tool = EchoTool()
    options = tool.tool_options()
    assert options["name"] == "echo"
    assert options["description"] == "Echo the text back."
    assert tool.tool_name() == "echo"


def test_toolkit_resolves_tool_classes() -> None:
    toolkit = EchoToolkit()
    resolved = toolkit.tool_objects()
    assert len(resolved) == 1
    assert isinstance(resolved[0], EchoTool)


def test_builtin_toolkit_classes() -> None:
    assert set(TOOLKIT_CLASSES) == {
        "database",
        "scheduler",
        "queue",
        "notifications",
        "history",
        "usage",
        "knowledge_admin",
        "skills_admin",
    }
    assert toolkit_for("database") is DatabaseToolkit
    with pytest.raises(KeyError):
        toolkit_for("nope")


def test_option_overrides() -> None:
    tool = EchoTool(requires_approval=True, retries=2)
    options = tool.tool_options()
    assert options["requires_approval"] is True
    assert options["retries"] == 2


def test_tool_group_alias() -> None:
    from agentkit import ToolGroup

    assert ToolGroup is Toolkit
