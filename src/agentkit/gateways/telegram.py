"""Telegram helpers: Markdown rendering + inline approval broker."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from aiogram import Bot
from aiogram.types import (
    BufferedInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MessageEntity,
)
from telegramify_markdown import File as TGFile
from telegramify_markdown import Photo as TGPhoto
from telegramify_markdown import Text as TGText
from telegramify_markdown import telegramify

from agentkit.deps import ApprovalRequest

MAX_MESSAGE_LEN = 4096
MIN_FILE_LINES = 200
APPROVAL_TIMEOUT = 300.0


def is_allowed(allowed_chat_ids: list[int], chat_id: int) -> bool:
    return not allowed_chat_ids or chat_id in allowed_chat_ids


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
