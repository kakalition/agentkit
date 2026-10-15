from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agentkit.deps import ApprovalRequest
from agentkit.gateways.base import Gateway, GatewayError


class FakeApp:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(agent_name="fake")
        self.calls: list[tuple[str, str]] = []

    async def answer(self, conversation_id: str, text: str) -> object:
        self.calls.append((conversation_id, text))
        return SimpleNamespace(output=text.upper())


class FakeGateway(Gateway):
    name = "fake"

    def __init__(self, app=None, **kwargs) -> None:
        super().__init__(app, **kwargs)
        self.sent: list[tuple[str, str]] = []
        self.started = False
        self.prompts: list[ApprovalRequest] = []

    async def start(self) -> None:
        self.started = True

    async def send(self, conversation_id: str, text: str) -> None:
        self.sent.append((conversation_id, text))

    async def prompt_approval(self, external_id, request) -> None:
        self.prompts.append(request)
        await self.send(self.conversation_id(external_id), f"approve {request.tool_name}")


def test_is_allowed_and_conversation_mapping():
    gateway = FakeGateway(allowed_channel_ids=[1, 2])
    assert gateway.is_allowed(1) is True
    assert gateway.is_allowed(3) is False
    assert gateway.conversation_id(1) == "fake:1"
    assert gateway.conversation_id(1) is gateway.conversation_id(1)


async def test_run_turn_through_app_answer():
    app = FakeApp()
    gateway = FakeGateway(app)
    result = await gateway.run_turn(7, "hi")
    assert result.output == "HI"
    assert app.calls == [("fake:7", "hi")]


async def test_run_turn_blocked_by_allow_list():
    app = FakeApp()
    gateway = FakeGateway(app, allowed_channel_ids=[1])
    assert await gateway.run_turn(9, "hi") is None
    assert app.calls == []


async def test_run_turn_without_app_raises():
    gateway = FakeGateway(None)
    with pytest.raises(GatewayError):
        await gateway.run_turn(1, "hi")


async def test_reply_uses_conversation_id():
    gateway = FakeGateway(FakeApp())
    await gateway.reply(3, "hello")
    assert gateway.sent == [("fake:3", "hello")]


async def test_ask_approval_resolves_and_times_out():
    gateway = FakeGateway(FakeApp(), timeout=0.2)
    request = ApprovalRequest(tool_call_id="c1", tool_name="delete", args={})

    async def approve() -> None:
        await asyncio.sleep(0.02)
        assert gateway.resolve_approval("c1", True) is True

    task = asyncio.create_task(gateway.ask_approval(5, [request]))
    await approve()
    decisions = await task
    assert decisions == {"c1": True}
    assert gateway.prompts == [request]
    assert gateway.sent and gateway.sent[0][1] == "approve delete"

    # An unresolved request denies on timeout.
    timeout_request = ApprovalRequest(tool_call_id="c2", tool_name="x", args={})
    assert await gateway.ask_approval(5, [timeout_request]) == {"c2": False}
    assert gateway.resolve_approval("missing", True) is False


async def test_service_wraps_start():
    gateway = FakeGateway(FakeApp())
    service = gateway.service()
    assert service.name == "fake"
    await asyncio.to_thread(service.run)
    assert gateway.started is True
