"""Telegram helpers: Markdown rendering, turn UX + inline approval broker."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, TypeVar

from aiogram import Bot
from aiogram.types import (
    BufferedInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    MessageEntity,
    ReactionTypeEmoji,
)
from telegramify_markdown import File as TGFile
from telegramify_markdown import Photo as TGPhoto
from telegramify_markdown import Text as TGText
from telegramify_markdown import telegramify

from agentkit.deps import ApprovalRequest
from agentkit.gateways.live_status import (
    DEFAULT_STATUS_INTERVAL_S,
    DEFAULT_TYPING_INTERVAL_S,
    idle_phrase,
    typing_keepalive,
)

MAX_MESSAGE_LEN = 4096
MIN_FILE_LINES = 200
APPROVAL_TIMEOUT = 300.0
SEEN_REACTION = "👀"

T = TypeVar("T")


def is_allowed(allowed_chat_ids: list[int], chat_id: int) -> bool:
    return not allowed_chat_ids or chat_id in allowed_chat_ids


async def react_seen(
    message: Message, emoji: str = SEEN_REACTION, *, enabled: bool = True
) -> None:
    """Acknowledge an incoming user message with an emoji reaction (best-effort)."""
    if not enabled:
        return
    with contextlib.suppress(Exception):
        await message.react([ReactionTypeEmoji(emoji=emoji)])


async def run_turn(
    factory: Callable[[], Awaitable[T]],
    *,
    bot: Bot,
    chat_id: int,
    live_status: bool = True,
    typing: bool = True,
    phrase_interval_s: float = DEFAULT_STATUS_INTERVAL_S,
    typing_interval_s: float = DEFAULT_TYPING_INTERVAL_S,
    phrases: Sequence[str] | None = None,
) -> T:
    """Run one chat turn with an ever-changing status bubble + typing indicator.

    A placeholder message is posted and edited to a fresh phrase every
    ``phrase_interval_s`` while ``factory`` runs, so the chat never looks idle.
    The bubble is deleted once the turn returns (or raises). ``live_status`` and
    ``typing`` toggle each behaviour; both are best-effort and never break the
    turn.
    """
    stop = asyncio.Event()
    tasks: list[asyncio.Task[None]] = []
    status_message: Message | None = None
    started = time.monotonic()

    def _status_text(index: int) -> str:
        elapsed = time.monotonic() - started
        return f"{idle_phrase(index, phrases)} ({elapsed:.0f}s)"

    async def _typing() -> None:
        with contextlib.suppress(Exception):
            await bot.send_chat_action(chat_id=chat_id, action="typing")

    if typing:
        await _typing()
        tasks.append(
            asyncio.create_task(
                typing_keepalive(_typing, interval_s=typing_interval_s, stop=stop)
            )
        )

    if live_status:
        with contextlib.suppress(Exception):
            status_message = await bot.send_message(chat_id, _status_text(0))
        if status_message is not None:
            message_id = status_message.message_id

            async def _rotate() -> None:
                index = 1
                while not stop.is_set():
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=phrase_interval_s)
                        return
                    except TimeoutError:
                        pass
                    with contextlib.suppress(Exception):
                        await bot.edit_message_text(
                            text=_status_text(index), chat_id=chat_id, message_id=message_id
                        )
                    index += 1

            tasks.append(asyncio.create_task(_rotate()))

    try:
        return await factory()
    finally:
        stop.set()
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if status_message is not None:
            with contextlib.suppress(Exception):
                await bot.delete_message(chat_id=chat_id, message_id=status_message.message_id)


def _tg_entities(entities: list[Any]) -> list[MessageEntity] | None:
    if not entities:
        return None
    mapped: list[MessageEntity] = []
    for entity in entities:
        data: dict[str, Any] = {
            "type": entity.type,
            "offset": entity.offset,
            "length": entity.length,
        }
        for field in ("url", "language", "custom_emoji_id", "unix_time", "date_time_format"):
            value = getattr(entity, field, None)
            if value is not None:
                data[field] = value
        mapped.append(MessageEntity(**data))
    return mapped


async def send_markdown(bot: Bot, chat_id: int, text: str, **kwargs: Any) -> None:
    """Render Markdown to Telegram entities (telegramify-markdown) and send.

    Falls back to plain text if Telegram rejects the rendered entities.
    """
    rendered = await telegramify(
        text or "(no reply)",
        render_mermaid=False,
        min_file_lines=MIN_FILE_LINES,
        max_message_length=MAX_MESSAGE_LEN,
    )
    for item in rendered:
        try:
            if isinstance(item, TGText):
                await bot.send_message(
                    chat_id, item.text, entities=_tg_entities(item.entities), **kwargs
                )
            elif isinstance(item, TGPhoto):
                await bot.send_photo(
                    chat_id,
                    BufferedInputFile(item.file_data, filename=item.file_name),
                    caption=item.caption_text,
                    caption_entities=_tg_entities(item.caption_entities),
                    **kwargs,
                )
            elif isinstance(item, TGFile):
                await bot.send_document(
                    chat_id,
                    BufferedInputFile(item.file_data, filename=item.file_name),
                    caption=item.caption_text,
                    caption_entities=_tg_entities(item.caption_entities),
                    **kwargs,
                )
        except Exception:  # pragma: no cover - defensive
            plain = getattr(item, "text", None) or getattr(item, "caption_text", "")
            with contextlib.suppress(Exception):
                await bot.send_message(chat_id, plain or "(reply)", **kwargs)


class ApprovalBroker:
    """Resolve pending tool approvals from Telegram inline-button callbacks."""

    def __init__(self, *, timeout: float = APPROVAL_TIMEOUT) -> None:
        self._pending: dict[str, asyncio.Future[bool]] = {}
        self._timeout = timeout

    async def ask(
        self, bot: Bot, chat_id: int, requests: list[ApprovalRequest]
    ) -> dict[str, bool]:
        loop = asyncio.get_running_loop()
        futures: dict[str, asyncio.Future[bool]] = {}
        for request in requests:
            future: asyncio.Future[bool] = loop.create_future()
            self._pending[request.tool_call_id] = future
            futures[request.tool_call_id] = future
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Approve", callback_data=f"approve:{request.tool_call_id}"
                        ),
                        InlineKeyboardButton(
                            text="❌ Deny", callback_data=f"deny:{request.tool_call_id}"
                        ),
                    ]
                ]
            )
            await send_markdown(
                bot,
                chat_id,
                f"Approve **{request.tool_name}**?\n\n```json\n{request.args}\n```",
                reply_markup=keyboard,
            )
        decisions: dict[str, bool] = {}
        for call_id, future in futures.items():
            try:
                decisions[call_id] = await asyncio.wait_for(future, timeout=self._timeout)
            except TimeoutError:
                decisions[call_id] = False
        return decisions

    def resolve(self, tool_call_id: str, value: bool) -> bool:
        future = self._pending.pop(tool_call_id, None)
        if future is not None and not future.done():
            future.set_result(value)
            return True
        return False
