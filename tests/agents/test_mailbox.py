from __future__ import annotations

import asyncio

from agentkit.agents.handle import AgentHandle
from agentkit.agents.mailbox import Mailbox
from agentkit.agents.registry import AgentRegistry
from agentkit.foundation.events import Dispatcher


class EchoAgent:
    def __init__(self, output: str = "reply") -> None:
        self.output = output

    async def run(self, prompt, *, deps=None, usage=None, model=None, **kwargs):
        return type("Result", (), {"output": f"{self.output}: {prompt}"})()


def _registry(*names: str) -> AgentRegistry:
    registry = AgentRegistry()
    for name in names:
        registry.register(AgentHandle.local(EchoAgent(), name=name))
    return registry


async def test_send_and_receive_in_process():
    registry = _registry("researcher")
    mailbox = Mailbox(registry)
    received: list[str] = []

    async def handler(message: str) -> None:
        received.append(message)

    mailbox.subscribe("researcher", handler)
    assert await mailbox.send("researcher", "hello") is True
    await asyncio.sleep(0)  # let the fire-and-forget subscriber run
    assert received == ["hello"]
    assert await mailbox.receive("researcher") == "hello"


async def test_send_unknown_agent_returns_false():
    mailbox = Mailbox(_registry())
    assert await mailbox.send("ghost", "hi") is False


async def test_ask_returns_reply_and_never_raises():
    registry = _registry("researcher")
    mailbox = Mailbox(registry)
    assert (await mailbox.ask("researcher", "q")).endswith("q")
    assert "no such agent" in await mailbox.ask("ghost", "q")


class ExplodingAgent:
    async def run(self, *args, **kwargs):
        raise RuntimeError("boom")


async def test_ask_swallows_agent_failure():
    registry = AgentRegistry()
    registry.register(AgentHandle.local(ExplodingAgent(), name="bad"))
    mailbox = Mailbox(registry)
    result = await mailbox.ask("bad", "q")
    assert "failed" in result


async def test_broadcast_gathers_all_replies():
    registry = _registry("a", "b")
    mailbox = Mailbox(registry)
    results = await mailbox.broadcast("standup")
    assert set(results) == {"a", "b"}
    assert results["a"].endswith("standup")


async def test_durable_send_uses_dbos_when_available(monkeypatch):
    registry = _registry("researcher")
    mailbox = Mailbox(registry, durable=True)
    sent: list[tuple] = []

    class FakeDBOS:
        @staticmethod
        def send(destination_id, message, topic=None):
            sent.append((destination_id, message, topic))

    import agentkit.durability as durability

    monkeypatch.setattr(durability, "DBOS", FakeDBOS)
    await mailbox.send("researcher", "durable hello")
    assert sent and sent[0][0] == "researcher"
    assert sent[0][2] == "researcher"
    assert sent[0][1]["message"] == "durable hello"


async def test_mailbox_emits_agent_message_events():
    events = Dispatcher()
    seen: list[str] = []
    events.listen("agent.message", lambda e: seen.append(e.get("kind")))
    registry = _registry("a")
    mailbox = Mailbox(registry, events=events)
    await mailbox.send("a", "hi")
    await mailbox.ask("a", "q")
    await mailbox.broadcast("all")
    assert seen[0] == "send"
    assert "ask" in seen
    assert "broadcast" in seen
