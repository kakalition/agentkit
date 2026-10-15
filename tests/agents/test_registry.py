from __future__ import annotations

from agentkit.agents.handle import AgentHandle
from agentkit.agents.registry import AgentRegistry


class FakeAgent:
    def __init__(self, output: str = "ok", name: str = "") -> None:
        self.output = output
        if name:
            self.name = name
        self.calls: list[tuple[str, object]] = []

    async def run(self, prompt, *, deps=None, usage=None, model=None, **kwargs):
        self.calls.append((prompt, deps))
        return type("Result", (), {"output": self.output})()


class FakeA2AClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def call_agent(self, url: str, message: str, *, context_id=None) -> str:
        self.calls.append((url, message))
        return f"remote:{message}"


def test_registry_resolve_by_name_and_capability():
    registry = AgentRegistry()
    researcher = FakeAgent(name="researcher")
    registry.register(AgentHandle.local(researcher, capabilities=["search", "summarize"]))
    registry.register(AgentHandle.local(FakeAgent(), name="writer"))

    assert registry.get("researcher") is not None
    assert registry.resolve("researcher").name == "researcher"
    assert registry.resolve("search").name == "researcher"
    assert {handle.name for handle in registry.capable("summarize")} == {"researcher"}
    assert registry.resolve("nope") is None
    assert registry.names() == ["researcher", "writer"]


async def test_local_handle_invokes_agent_forwarding_deps():
    agent = FakeAgent(output="hello")
    handle = AgentHandle.local(agent, name="greeter", capabilities=["greet"])

    class Ctx:
        deps = object()

    assert await handle.invoke(Ctx(), "hi") == "hello"
    assert agent.calls and agent.calls[0][0] == "hi"


async def test_remote_handle_uses_a2a_client():
    client = FakeA2AClient()
    handle = AgentHandle.remote("peer", "http://peer/a2a", client=client)
    assert handle.is_remote is True
    assert await handle.invoke(None, "ping") == "remote:ping"
    assert client.calls == [("http://peer/a2a", "ping")]


async def test_remote_handle_without_client():
    handle = AgentHandle.remote("peer", "http://peer/a2a")
    assert "not configured" in await handle.invoke(None, "ping")
