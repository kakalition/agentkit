from __future__ import annotations

from pathlib import Path

from pydantic_ai.messages import ModelRequest, ToolReturnPart

from agentkit.config import AgentSettings
from agentkit.foundation.agent import Agent
from agentkit.offload import offload_messages


def _tool_message(content: str, call_id: str = "c1") -> ModelRequest:
    return ModelRequest(parts=[ToolReturnPart(tool_name="t", content=content, tool_call_id=call_id)])


def test_offload_roundtrip(tmp_path: Path):
    big = "x" * 8000
    message = _tool_message(big)
    count = offload_messages([message], root=tmp_path, conversation_id="cli:c", threshold_tokens=100)
    assert count == 1
    preview = message.parts[0].content  # type: ignore[union-attr]
    assert isinstance(preview, str) and "offloaded to" in preview
    files = list((tmp_path / "offload" / "cli_c").glob("*.txt"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == big


def test_offload_below_threshold_passthrough(tmp_path: Path):
    message = _tool_message("hello")
    assert offload_messages([message], root=tmp_path, conversation_id="c", threshold_tokens=1000) == 0
    assert message.parts[0].content == "hello"  # type: ignore[union-attr]


def test_offload_disabled_is_noop(tmp_path: Path):
    message = _tool_message("y" * 8000)
    assert offload_messages([message], root=tmp_path, conversation_id="c", threshold_tokens=0) == 0


def test_read_artifact_tool_attached_when_enabled(tmp_path: Path):
    settings = AgentSettings(
        agent_home=tmp_path,
        memory_embedding_backend="hash",
        tool_output_offload_threshold=100,
    )
    built = Agent.make("a").instructions("x").output(str).full(settings=settings).build(
        settings=settings
    )
    assert "read_artifact" in set(built._function_toolset.tools.keys())


def test_read_artifact_tool_absent_by_default(tmp_path: Path):
    settings = AgentSettings(agent_home=tmp_path, memory_embedding_backend="hash")
    built = Agent.make("a").instructions("x").output(str).full(settings=settings).build(
        settings=settings
    )
    assert "read_artifact" not in set(built._function_toolset.tools.keys())
