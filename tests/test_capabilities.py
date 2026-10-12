from __future__ import annotations

from agentkit import Agent, Sandbox


def test_web_and_reasoning_capability_shortcuts_build():
    agent = (
        Agent.make("cap")
        .instructions("be helpful")
        .web_search()
        .web_fetch()
        .thinking(effort="medium")
        .caching()
        .tool_search()
        .output(str)
        .build()
    )
    assert agent is not None
    assert agent.name == "cap"


def test_sandbox_capability_shortcut(tmp_path):
    agent = Agent.make("cap").instructions("i").sandbox(tmp_path).output(str).build()
    assert agent is not None


def test_workspace_and_sandbox_alias(tmp_path):
    box = Sandbox(tmp_path)
    agent = Agent.make("cap").instructions("i").workspace(sandbox=box).output(str).build()
    assert agent is not None


def test_workspace_requires_root():
    try:
        Agent.make("cap").workspace()
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
