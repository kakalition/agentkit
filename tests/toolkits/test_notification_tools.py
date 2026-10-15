from __future__ import annotations

from types import SimpleNamespace

from agentkit import Agent
from agentkit.deps import Deps


def _fn(agent, name):
    return agent._function_toolset.tools[name].function


def _ctx(deps: Deps) -> SimpleNamespace:
    return SimpleNamespace(deps=deps)


def _agent():
    return Agent.make("n").instructions("x").notifications().output(str).build()


def test_notification_approval_flags():
    agent = _agent()
    assert agent._function_toolset.tools["notify"].requires_approval is True
    assert agent._function_toolset.tools["notify_me"].requires_approval is False


async def test_notify_me_writes_to_conversation(repos, deps: Deps):
    deps.extras["conversation_id"] = "cli:test"
    agent = _agent()
    assert await _fn(agent, "notify_me")(_ctx(deps), "hello there") == "noted"
    rows = await repos.messages.list("cli:test")
    assert len(rows) == 1
    assert "hello there" in rows[0].payload


async def test_notify_log_channel(repos, deps: Deps):
    agent = _agent()
    out = await _fn(agent, "notify")(_ctx(deps), "ping", ["log"])
    assert out == "notified via log"


async def test_notify_unavailable_channel(repos, deps: Deps):
    agent = _agent()
    out = await _fn(agent, "notify")(_ctx(deps), "ping", ["carrier-pigeon"])
    assert out == "(no channel delivered)"
