from __future__ import annotations

from pathlib import Path

from agentkit import AgentRegistry
from agentkit.agents.handle import AgentHandle
from agentkit.config import AgentSettings
from agentkit.foundation.agent import Agent


class EchoAgent:
    async def run(self, prompt, *, deps=None, usage=None, model=None, **kwargs):  # pragma: no cover
        return type("Result", (), {"output": prompt})()


def _settings(tmp_path: Path, **overrides) -> AgentSettings:
    return AgentSettings(
        agent_home=tmp_path, memory_embedding_backend="hash", **overrides
    )


def test_full_adds_the_agent_stack(tmp_path: Path):
    settings = _settings(tmp_path)
    builder = Agent.make("a").instructions("x").output(str).full(settings=settings)
    agent = builder.build(settings=settings)
    tools = set(agent._function_toolset.tools.keys())
    assert {"remember", "recall", "forget_memory"} <= tools
    assert "ask_user" in tools  # HITL clarify
    assert len(builder.policies) == 1  # safety policy applied once


def test_full_is_idempotent(tmp_path: Path):
    settings = _settings(tmp_path)
    builder = (
        Agent.make("a")
        .instructions("x")
        .output(str)
        .full(settings=settings)
        .full(settings=settings)
    )
    assert len(builder.policies) == 1
    assert builder._instruction_parts == ["x"]
    assert builder._full_layers  # layers tracked so a second call is a no-op


def test_full_respects_disabled_settings(tmp_path: Path):
    settings = _settings(
        tmp_path, memory_enabled=False, skills_enabled=False, approvals_enabled=False
    )
    agent = (
        Agent.make("a").instructions("x").output(str).full(settings=settings).build(settings=settings)
    )
    tools = set(agent._function_toolset.tools.keys())
    assert "remember" not in tools
    assert "ask_user" not in tools


def test_full_attaches_knowledge_when_given(tmp_path: Path):
    settings = _settings(tmp_path)
    doc = tmp_path / "notes.md"
    doc.write_text("The capital of France is Paris.", encoding="utf-8")
    agent = (
        Agent.make("a")
        .instructions("x")
        .output(str)
        .full(knowledge=doc, settings=settings)
        .build(settings=settings)
    )
    assert "search_knowledge" in set(agent._function_toolset.tools.keys())


def test_full_attaches_peer_tools_when_subagents_enabled(tmp_path: Path):
    settings = _settings(tmp_path, subagents_enabled=True)
    registry = AgentRegistry()
    registry.register(AgentHandle.local(EchoAgent(), name="peer"))
    builder = (
        Agent.make("a")
        .instructions("x")
        .output(str)
        .agents(registry)
        .full(settings=settings)
    )
    agent = builder.build(settings=settings)
    tools = set(agent._function_toolset.tools.keys())
    assert {"send_to", "ask_agent", "broadcast", "list_agents", "handoff_to"} <= tools


def test_subagent_and_handoff_to_builders(tmp_path: Path):
    settings = _settings(tmp_path)
    agent = (
        Agent.make("a")
        .instructions("x")
        .output(str)
        .subagent(EchoAgent(), name="peer")
        .handoff_to()
        .build(settings=settings)
    )
    tools = set(agent._function_toolset.tools.keys())
    assert "handoff_to" in tools
