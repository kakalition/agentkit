"""T2 — repository-backed mailbox spool (cross-process at-least-once delivery)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from agentkit.agents.handle import AgentHandle
from agentkit.agents.mailbox import Mailbox, MemorySpool, RepositoryMailboxSpool
from agentkit.agents.registry import AgentRegistry
from agentkit.foundation.application import App
from agentkit.foundation.facade import using
from agentkit.runtime import Runtime, repositories


def _app(runtime: Runtime, **updates: Any) -> App:
    settings = runtime.settings.model_copy(update=updates) if updates else runtime.settings
    app = App(name="mailbox", settings=settings, discover=False)
    app._runtime = runtime
    return app


def _registry(*names: str) -> AgentRegistry:
    registry = AgentRegistry()
    for name in names:
        registry.register(AgentHandle.local(SimpleNamespace(name=name), name=name))
    return registry


async def test_mailbox_repo_roundtrip_across_scopes(runtime: Runtime) -> None:
    async with repositories(runtime) as first:
        await first.mailbox.append("b", "ping", "a")

    # a fresh session (simulated restart) sees the committed spool
    async with repositories(runtime) as second:
        assert await second.mailbox.peek("b") == ["ping"]
        assert await second.mailbox.count("b") == 1
        assert await second.mailbox.drain("b") == ["ping"]

    async with repositories(runtime) as third:
        assert await third.mailbox.drain("b") == []


async def test_repository_spool_drains_across_mailboxes(runtime: Runtime) -> None:
    app = _app(runtime)
    registry = _registry("b")
    with using(app):
        first = Mailbox(registry, durable=True, spool=RepositoryMailboxSpool(app))
        assert await first.send("b", "ping") is True
        # a fresh mailbox over the same repository spool (a "restart") drains it
        second = Mailbox(registry, durable=True, spool=RepositoryMailboxSpool(app))
        assert await second.receive("b") == "ping"


async def test_repository_spool_replay_peeks_then_drains(runtime: Runtime) -> None:
    app = _app(runtime)
    registry = _registry("b")
    with using(app):
        mailbox = Mailbox(registry, durable=True, spool=RepositoryMailboxSpool(app))
        await mailbox.send("b", "one")
        assert await mailbox.replay("b") == ["one"]
        restarted = Mailbox(registry, durable=True, spool=RepositoryMailboxSpool(app))
        assert await restarted.receive("b") == "one"
        assert await restarted.replay("b") == []


async def test_default_spool_stays_in_process(runtime: Runtime) -> None:
    registry = _registry("b")
    mailbox = Mailbox(registry, durable=True)
    assert isinstance(mailbox.spool, MemorySpool)
    assert await mailbox.send("b", "hi") is True
    restarted = Mailbox(registry, durable=True)  # process-wide default spool
    assert await restarted.receive("b") == "hi"
