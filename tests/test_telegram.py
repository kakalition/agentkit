from __future__ import annotations

import asyncio

from agentkit.gateways.telegram import (
    ApprovalBroker,
    is_allowed,
    react_seen,
    run_turn,
    send_markdown,
)


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


async def test_react_seen_sets_eyes_reaction():
    class FakeMessage:
        def __init__(self) -> None:
            self.reactions: list = []

        async def react(self, reaction, **kwargs):  # noqa: ANN001
            self.reactions = list(reaction)

    message = FakeMessage()
    await react_seen(message)  # type: ignore[arg-type]
    assert len(message.reactions) == 1
    assert message.reactions[0].emoji == "👀"


async def test_react_seen_disabled_is_noop():
    class FakeMessage:
        def __init__(self) -> None:
            self.reactions: list = []

        async def react(self, reaction, **kwargs):  # noqa: ANN001
            self.reactions = list(reaction)

    message = FakeMessage()
    await react_seen(message, enabled=False)  # type: ignore[arg-type]
    assert message.reactions == []


class FakeTurnBot:
    """Minimal aiogram Bot surface used by ``run_turn``."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.edits: list[tuple[int, str]] = []
        self.deleted: list[int] = []
        self.actions: list[tuple[int, str]] = []
        self._next_id = 1

    async def send_message(self, chat_id, text, **kwargs):  # noqa: ANN001
        message_id = self._next_id
        self._next_id += 1
        self.sent.append((chat_id, text))

        class _Sent:
            pass

        sent = _Sent()
        sent.message_id = message_id  # type: ignore[attr-defined]
        return sent

    async def edit_message_text(self, text, chat_id=None, message_id=None, **kwargs):  # noqa: ANN001
        self.edits.append((message_id, text))

    async def delete_message(self, chat_id, message_id):  # noqa: ANN001
        self.deleted.append(message_id)

    async def send_chat_action(self, chat_id, action):  # noqa: ANN001
        self.actions.append((chat_id, action))


async def test_run_turn_rotates_and_cleans_up_status():
    bot = FakeTurnBot()

    async def factory() -> str:
        await asyncio.sleep(0.06)
        return "done"

    result = await run_turn(
        factory,
        bot=bot,  # type: ignore[arg-type]
        chat_id=7,
        phrase_interval_s=0.01,
        typing_interval_s=0.01,
    )
    assert result == "done"
    assert bot.sent, "expected a status bubble"
    assert bot.edits, "expected the status bubble to be edited"
    assert bot.deleted == [1], "expected the status bubble to be removed"
    assert bot.actions, "expected a typing indicator"
    texts = [text for _, text in bot.sent] + [text for _, text in bot.edits]
    assert len(set(texts)) > 1, "status text should keep changing"


async def test_run_turn_disabled_sends_nothing():
    bot = FakeTurnBot()

    async def factory() -> int:
        return 1

    assert (
        await run_turn(factory, bot=bot, chat_id=1, live_status=False, typing=False)  # type: ignore[arg-type]
        == 1
    )
    assert not bot.sent and not bot.edits and not bot.deleted and not bot.actions


async def test_approval_broker_resolve():
    broker = ApprovalBroker()
    loop = asyncio.get_running_loop()
    future: asyncio.Future[bool] = loop.create_future()
    broker._pending["c1"] = future
    assert broker.resolve("c1", True) is True
    assert await future is True
    assert broker.resolve("missing", False) is False
