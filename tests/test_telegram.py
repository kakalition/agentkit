from __future__ import annotations

import asyncio

from agentkit.gateways.telegram import ApprovalBroker, is_allowed, send_markdown


class FakeBot:
    def __init__(self, fail_entities: bool = False) -> None:
        self.messages: list[tuple[str, dict]] = []
        self.fail_entities = fail_entities
        self._failed = False

    async def send_message(self, chat_id, text, **kwargs):
        if self.fail_entities and not self._failed and kwargs.get("entities"):
            self._failed = True
            raise RuntimeError("bad entities")
        self.messages.append((text, kwargs))

    async def send_photo(self, chat_id, photo, **kwargs):
        self.messages.append(("PHOTO", kwargs))

    async def send_document(self, chat_id, document, **kwargs):
        self.messages.append(("DOCUMENT", kwargs))


def test_is_allowed():
    assert is_allowed([], 5) is True
    assert is_allowed([1, 2], 2) is True
    assert is_allowed([1, 2], 3) is False


async def test_send_markdown_renders_bold():
    bot = FakeBot()
    await send_markdown(bot, 1, "**hello** world")  # type: ignore[arg-type]
    text, kwargs = bot.messages[0]
    assert "**" not in text and "hello world" in text
    assert any(entity.type == "bold" for entity in kwargs["entities"])


async def test_send_markdown_falls_back():
    bot = FakeBot(fail_entities=True)
    await send_markdown(bot, 1, "**bold** reply")  # type: ignore[arg-type]
    assert bot._failed is True
    assert any("bold reply" in text for text, _ in bot.messages)


async def test_approval_broker_resolve():
    broker = ApprovalBroker()
    loop = asyncio.get_running_loop()
    future: asyncio.Future[bool] = loop.create_future()
    broker._pending["c1"] = future
    assert broker.resolve("c1", True) is True
    assert await future is True
    assert broker.resolve("missing", False) is False
