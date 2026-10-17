"""WS2.3 — multi-agent durability and topology semantics."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from agentkit.agents.handle import AgentHandle
from agentkit.agents.handoff import handoff
from agentkit.agents.mailbox import Mailbox, MemorySpool
from agentkit.agents.registry import AgentRegistry
from agentkit.comms import (
    GroupChatSpeaker,
    GroupChatTopology,
    HandoffTopology,
    MeshTopology,
    PipelineTopology,
    SwarmTopology,
)


def _recorder(name: str, seen: dict[str, list[str]]) -> Any:
    async def handler(message: str) -> str:
        seen.setdefault(name, []).append(message)
        return f"{name}:{message}"

    return handler


async def test_durable_mailbox_survives_restart() -> None:
    spool = MemorySpool()
    registry = AgentRegistry()
    registry.register(AgentHandle.local(SimpleNamespace(name="b"), name="b"))
    first = Mailbox(registry, durable=True, spool=spool)
    assert await first.send("b", "ping") is True

    # simulate a restart: a fresh mailbox over the same spool
    second = Mailbox(registry, durable=True, spool=spool)
    assert await second.receive("b") == "ping"


async def test_durable_mailbox_replay_and_redelivery() -> None:
    spool = MemorySpool()
    registry = AgentRegistry()
    registry.register(AgentHandle.local(SimpleNamespace(name="b"), name="b"))
    mailbox = Mailbox(registry, durable=True, spool=spool)
    await mailbox.send("b", "one")
    assert await mailbox.replay("b") == ["one"]
    # at-least-once: a fresh mailbox over the same spool redelivers, draining it
    restarted = Mailbox(registry, durable=True, spool=spool)
    assert await restarted.receive("b") == "one"
    assert await restarted.replay("b") == []


async def test_swarm_send_targets_member_then_broadcasts() -> None:
    seen: dict[str, list[str]] = {}
    topology = SwarmTopology()
    for name in ("a", "b"):
        topology.register(name, _recorder(name, seen))
    assert await topology.send("a", "hi") is True
    assert seen["a"] == ["hi"]
    await topology.send("nobody", "fan")
    assert seen["a"] == ["hi", "fan"]
    assert seen["b"] == ["fan"]


async def test_mesh_links_restrict_delivery() -> None:
    seen: dict[str, list[str]] = {}
    topology = MeshTopology(links=[("a", "b")])
    for name in ("a", "b", "c"):
        topology.register(name, _recorder(name, seen))
    assert await topology.send("b", "hi", sender="a") is True
    assert await topology.send("c", "hi", sender="a") is False


async def test_handoff_delivers_to_single_target() -> None:
    seen: dict[str, list[str]] = {}
    topology = HandoffTopology()
    for name in ("a", "b"):
        topology.register(name, _recorder(name, seen))
    result = await topology.broadcast("go")
    assert list(result) == ["a"]
    assert "b" not in seen


async def test_pipeline_chains_stages() -> None:
    seen: dict[str, list[str]] = {}

    topology = PipelineTopology(stages=["a", "b"])
    for name in ("a", "b"):
        topology.register(name, _recorder(name, seen))
    result = await topology.broadcast("go")
    assert result["a"] == "a:go"
    assert result["b"] == "b:a:go"


async def test_groupchat_send_is_speaker_aware() -> None:
    seen: dict[str, list[str]] = {}
    topology = GroupChatTopology(participants=["a", "b"])
    for name in ("a", "b"):
        topology.register(name, _recorder(name, seen))
    # a direct address reaches the named participant (and does not advance rotation)
    assert await topology.send("a", "direct") is True
    assert seen["a"] == ["direct"]
    # an unknown address is routed by the speaker strategy (round-robin)
    assert await topology.send("group", "chat") is True
    assert seen["a"] == ["direct", "chat"]
    assert await topology.send("group", "again") is True
    assert seen["b"] == ["again"]


async def test_groupchat_moderator_and_all() -> None:
    seen: dict[str, list[str]] = {}
    topology = GroupChatTopology(
        participants=["a", "b"], speaker=GroupChatSpeaker.MODERATOR, moderator="b"
    )
    for name in ("a", "b"):
        topology.register(name, _recorder(name, seen))
    await topology.broadcast("q")
    assert seen == {"b": ["q"]}

    seen2: dict[str, list[str]] = {}
    all_topology = GroupChatTopology(participants=["a", "b"], speaker=GroupChatSpeaker.ALL)
    for name in ("a", "b"):
        all_topology.register(name, _recorder(name, seen2))
    await all_topology.broadcast("q")
    assert set(seen2) == {"a", "b"}


async def test_remote_handoff_uses_client() -> None:
    calls: list[tuple[str, str]] = []

    class StubClient:
        async def call_agent(self, url: str, task: str) -> str:
            calls.append((url, task))
            return "remote reply"

    handle = AgentHandle.remote("peer", "http://peer/a2a", client=StubClient())
    registry = AgentRegistry()
    registry.register(handle)
    output = await handoff("peer", ctx=None, deps=None, registry=registry, brief="do it")
    assert output == "remote reply"
    assert calls == [("http://peer/a2a", "do it")]
