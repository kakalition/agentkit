from __future__ import annotations

from types import SimpleNamespace

import pytest

from agentkit.gateways.discord import DiscordGateway
from agentkit.gateways.slack import SlackGateway


class FakeApp:
    settings = SimpleNamespace(agent_name="chan")

    async def answer(self, conversation_id, text):  # pragma: no cover - unused here
        return SimpleNamespace(output=text)


class FakeSlackClient:
    def __init__(self) -> None:
        self.posts: list[dict] = []

    def chat_postMessage(self, **payload):
        self.posts.append(payload)
        return {"ok": True}


class FakeDiscordChannel:
    def __init__(self) -> None:
        self.id = 42
        self.messages: list[str] = []

    async def send(self, text):
        self.messages.append(text)
        return SimpleNamespace(id=1000)


def test_slack_conversation_mapping_and_send():
    pytest.importorskip("slack_sdk")
    client = FakeSlackClient()
    gateway = SlackGateway(FakeApp(), settings=SimpleNamespace(), client=client)
    assert gateway.conversation_id(("C1", "1.2")) == "slack:C1:1.2"
    assert gateway.conversation_id(("C1", "")) == "slack:C1:"


async def test_slack_send_posts_to_client():
    pytest.importorskip("slack_sdk")
    client = FakeSlackClient()
    gateway = SlackGateway(FakeApp(), settings=SimpleNamespace(), client=client)
    await gateway.send("slack:C9:1.5", "hi")
    assert client.posts == [{"channel": "C9", "text": "hi", "thread_ts": "1.5"}]


async def test_discord_send_uses_registered_channel():
    pytest.importorskip("discord")
    channel = FakeDiscordChannel()
    gateway = DiscordGateway(FakeApp(), settings=SimpleNamespace())
    gateway._channels["discord:42"] = channel
    await gateway.send("discord:42", "hello")
    assert channel.messages == ["hello"]
