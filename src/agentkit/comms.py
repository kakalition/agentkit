"""Agent communication topologies (contract + drivers).

A *topology* routes messages between named agents. ``mailbox`` (the existing
:class:`~agentkit.agents.mailbox.Mailbox`) is the default driver; the others are
alternative shapes selected with ``comms_driver`` or registered with
``app.extend("comms", name, factory)``.

Every topology offers ``send(to, message)`` (point-to-point) and
``broadcast(message)`` (fan-out). Handlers are registered per name with
``register(name, async handling)``; a topology can also wrap an
:class:`~agentkit.agents.registry.AgentRegistry` for real agents.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from agentkit.contracts.comms import Topology
from agentkit.support import register_driver
from agentkit.support.kinds import CommsDriver, DriverKind
from agentkit.support.manager import Manager

__all__ = [
    "BlackboardTopology",
    "BroadcastTopology",
    "CommsManager",
    "GroupChatSpeaker",
    "GroupChatTopology",
    "HandoffTopology",
    "HierarchyTopology",
    "HubTopology",
    "MailboxTopology",
    "MeshTopology",
    "OutboxTopology",
    "PipelineTopology",
    "PubSubTopology",
    "SwarmTopology",
    "Topology",
]

Handler = Callable[[str], Awaitable[Any]]


class GroupChatSpeaker(StrEnum):
    """How a :class:`GroupChatTopology` picks who answers."""

    ROUND_ROBIN = "round_robin"
    MODERATOR = "moderator"
    ALL = "all"


class TopologyBase:
    """Shared plumbing for topologies: a handler map and fan-out helper."""

    def __init__(self, registry: Any = None, *, events: Any = None) -> None:
        if registry is None:
            from agentkit.agents.registry import AgentRegistry

            registry = AgentRegistry()
        self.registry = registry
        self.events = events
        self.handlers: dict[str, Handler] = {}

    def register(self, name: str, handler: Handler) -> TopologyBase:
        self.handlers[name] = handler
        return self

    async def _deliver(self, name: str, message: str) -> Any:
        handler = self.handlers.get(name)
        if handler is None:
            return f"no such handler {name!r}"
        return await handler(message)

    def _targets(self, to: list[str] | None = None) -> list[str]:
        return list(to) if to is not None else list(self.handlers)

    async def send(self, to: str, message: str, *, sender: str | None = None) -> bool:
        if to not in self.handlers:
            return False
        await self._deliver(to, message)
        return True

    async def broadcast(
        self, message: str, *, to: list[str] | None = None, sender: str | None = None
    ) -> dict[str, Any]:
        targets = self._targets(to)
        results = await asyncio.gather(*(self._deliver(name, message) for name in targets))
        return dict(zip(targets, results, strict=True))


class MailboxTopology(TopologyBase):
    """The default topology: name-addressed delivery (wraps ``Mailbox``)."""

    def __init__(self, registry: Any = None, *, events: Any = None, durable: bool = False) -> None:
        super().__init__(registry, events=events)
        from agentkit.agents.mailbox import Mailbox

        self.mailbox = Mailbox(self.registry, durable=durable, events=events)

    def _sync_subscribers(self) -> None:
        for name, handler in self.handlers.items():
            self.mailbox.subscribe(name, handler)

    async def send(self, to: str, message: str, *, sender: str | None = None) -> bool:
        self._sync_subscribers()
        return await self.mailbox.send(to, message, sender=sender)

    async def broadcast(
        self, message: str, *, to: list[str] | None = None, sender: str | None = None
    ) -> dict[str, Any]:
        self._sync_subscribers()
        return await self.mailbox.broadcast(message, to=to, sender=sender)


class BroadcastTopology(TopologyBase):
    """Fan-out: every message goes to every handler."""

    async def send(self, to: str, message: str, *, sender: str | None = None) -> bool:
        await self.broadcast(message, sender=sender)
        return True


class SwarmTopology(BroadcastTopology):
    """Broadcast-and-collect: like broadcast, but returns every reply."""


class PipelineTopology(TopologyBase):
    """Sequential stages: a broadcast flows output of one stage into the next."""

    def __init__(self, registry: Any = None, *, stages: list[str] | None = None) -> None:
        super().__init__(registry)
        self.stages = list(stages or [])

    async def broadcast(
        self, message: str, *, to: list[str] | None = None, sender: str | None = None
    ) -> dict[str, Any]:
        results: dict[str, Any] = {}
        payload: Any = message
        for stage in (to or self.stages):
            payload = await self._deliver(stage, str(payload))
            results[stage] = payload
        return results


class HandoffTopology(PipelineTopology):
    """A single-step transfer: the message is handed to one handler and answered."""


class HubTopology(TopologyBase):
    """Central hub: every message is routed through one hub handler."""

    def __init__(self, registry: Any = None, *, hub: str = "hub") -> None:
        super().__init__(registry)
        self.hub = hub

    async def send(self, to: str, message: str, *, sender: str | None = None) -> bool:
        return await super().send(self.hub, message, sender=sender)

    async def broadcast(
        self, message: str, *, to: list[str] | None = None, sender: str | None = None
    ) -> dict[str, Any]:
        reply = await self._deliver(self.hub, message)
        return {self.hub: reply}


class MeshTopology(MailboxTopology):
    """Peer-to-peer: direct delivery between any two registered agents."""


class HierarchyTopology(TopologyBase):
    """Parent/child routing: messages flow to a designated parent handler."""

    def __init__(self, registry: Any = None, *, parent: str = "parent") -> None:
        super().__init__(registry)
        self.parent = parent

    async def send(self, to: str, message: str, *, sender: str | None = None) -> bool:
        return await super().send(self.parent, message, sender=sender)


class OutboxTopology(TopologyBase):
    """Append-only outbox: messages are recorded, not delivered."""

    def __init__(self, registry: Any = None) -> None:
        super().__init__(registry)
        self.outbox: list[tuple[str, str]] = []

    async def send(self, to: str, message: str, *, sender: str | None = None) -> bool:
        self.outbox.append((to, message))
        return True

    async def broadcast(
        self, message: str, *, to: list[str] | None = None, sender: str | None = None
    ) -> dict[str, Any]:
        for name in self._targets(to):
            self.outbox.append((name, message))
        return {"outbox": len(self.outbox)}


class BlackboardTopology(TopologyBase):
    """A shared board: messages are posted to channels all agents can read."""

    def __init__(self, registry: Any = None) -> None:
        super().__init__(registry)
        self.board: dict[str, list[str]] = {}

    async def send(self, to: str, message: str, *, sender: str | None = None) -> bool:
        self.board.setdefault(to, []).append(message)
        return True

    async def broadcast(
        self, message: str, *, to: list[str] | None = None, sender: str | None = None
    ) -> dict[str, Any]:
        for name in self._targets(to) or ["shared"]:
            self.board.setdefault(name, []).append(message)
        return {name: list(notes) for name, notes in self.board.items()}


class PubSubTopology(TopologyBase):
    """Topic publish/subscribe: ``send(topic, message)`` notifies subscribers."""

    def __init__(self, registry: Any = None) -> None:
        super().__init__(registry)
        self.topics: dict[str, list[str]] = {}

    def subscribe(self, topic: str, name: str) -> PubSubTopology:
        self.topics.setdefault(topic, []).append(name)
        return self

    async def send(self, to: str, message: str, *, sender: str | None = None) -> bool:
        subscribers = self.topics.get(to, [])
        for name in subscribers:
            await self._deliver(name, message)
        return bool(subscribers)

    async def broadcast(
        self, message: str, *, to: list[str] | None = None, sender: str | None = None
    ) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for topic, subscribers in self.topics.items():
            results[topic] = await asyncio.gather(*(self._deliver(name, message) for name in subscribers))
        return results


class GroupChatTopology(TopologyBase):
    """A group chat: a speaker strategy picks who answers each broadcast.

    ``round_robin`` (default) rotates through the roster, ``moderator`` always
    asks a designated moderator, and ``all`` asks everyone and collects replies.
    """

    def __init__(
        self,
        registry: Any = None,
        *,
        participants: list[str] | None = None,
        speaker: GroupChatSpeaker = GroupChatSpeaker.ROUND_ROBIN,
        moderator: str | None = None,
    ) -> None:
        super().__init__(registry)
        self.participants = list(participants or [])
        self.speaker = speaker
        self.moderator = moderator
        self._cursor = 0

    def _roster(self) -> list[str]:
        return self.participants or list(self.handlers)

    async def broadcast(
        self, message: str, *, to: list[str] | None = None, sender: str | None = None
    ) -> dict[str, Any]:
        roster = to or self._roster()
        if not roster:
            return {}
        if self.speaker == GroupChatSpeaker.ALL:
            results = await asyncio.gather(*(self._deliver(name, message) for name in roster))
            return dict(zip(roster, results, strict=True))
        if self.speaker == GroupChatSpeaker.MODERATOR:
            speaker = self.moderator or roster[0]
        else:  # round_robin
            speaker = roster[self._cursor % len(roster)]
            self._cursor += 1
        return {speaker: await self._deliver(speaker, message)}


class CommsManager(Manager):
    """Resolves the configured comms topology (``comms_driver``, default ``mailbox``)."""

    kind = DriverKind.COMMS
    default_driver = CommsDriver.MAILBOX


def _topology_events(app: Any) -> Any:
    return getattr(app, "events", None)


@register_driver(DriverKind.COMMS, CommsDriver.MAILBOX)
def _mailbox_topology_driver(app: Any) -> MailboxTopology:
    return MailboxTopology(events=_topology_events(app))


@register_driver(DriverKind.COMMS, CommsDriver.BROADCAST)
def _broadcast_topology_driver(app: Any) -> BroadcastTopology:
    return BroadcastTopology(events=_topology_events(app))


@register_driver(DriverKind.COMMS, CommsDriver.SWARM)
def _swarm_topology_driver(app: Any) -> SwarmTopology:
    return SwarmTopology(events=_topology_events(app))


@register_driver(DriverKind.COMMS, CommsDriver.PIPELINE)
def _pipeline_topology_driver(app: Any) -> PipelineTopology:
    return PipelineTopology()


@register_driver(DriverKind.COMMS, CommsDriver.HANDOFF)
def _handoff_topology_driver(app: Any) -> HandoffTopology:
    return HandoffTopology()


@register_driver(DriverKind.COMMS, CommsDriver.HUB)
def _hub_topology_driver(app: Any) -> HubTopology:
    return HubTopology()


@register_driver(DriverKind.COMMS, CommsDriver.MESH)
def _mesh_topology_driver(app: Any) -> MeshTopology:
    return MeshTopology(events=_topology_events(app))


@register_driver(DriverKind.COMMS, CommsDriver.HIERARCHY)
def _hierarchy_topology_driver(app: Any) -> HierarchyTopology:
    return HierarchyTopology()


@register_driver(DriverKind.COMMS, CommsDriver.OUTBOX)
def _outbox_topology_driver(app: Any) -> OutboxTopology:
    return OutboxTopology()


@register_driver(DriverKind.COMMS, CommsDriver.BLACKBOARD)
def _blackboard_topology_driver(app: Any) -> BlackboardTopology:
    return BlackboardTopology()


@register_driver(DriverKind.COMMS, CommsDriver.PUBSUB)
def _pubsub_topology_driver(app: Any) -> PubSubTopology:
    return PubSubTopology()


@register_driver(DriverKind.COMMS, CommsDriver.GROUPCHAT)
def _groupchat_topology_driver(app: Any) -> GroupChatTopology:
    return GroupChatTopology()
