"""Trajectory export + compression for training and evaluation datasets.

A *trajectory* is a normalized, JSON-serializable view of a conversation: the
system prompt (once) and an ordered list of steps (user / assistant / tool_call /
tool_result). :func:`export_trajectory` builds one; :func:`iter_trajectories`
streams one per stored conversation; :func:`compress_messages` elides large tool
returns (faithfully, keeping head+tail) so exports stay small.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

__all__ = [
    "DEFAULT_MAX_CHARS",
    "compress_content",
    "compress_messages",
    "export_trajectory",
    "iter_trajectories",
    "render_jsonl",
]

DEFAULT_MAX_CHARS = 400
_ELISION = "\n…[{n} chars elided]…\n"


def compress_content(text: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Elide the middle of ``text`` to at most ``max_chars`` (head + tail kept)."""
    if not isinstance(text, str) or len(text) <= max_chars:
        return text
    head = max_chars // 2
    tail = max_chars - head
    return text[:head] + _ELISION.format(n=len(text) - max_chars) + text[-tail:]


def export_trajectory(
    messages: list[ModelMessage],
    *,
    system_prompt: str | None = None,
    compress: bool = False,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict[str, Any]:
    """Normalize a conversation into a ``{system_prompt, steps}`` trajectory."""
    steps: list[dict[str, Any]] = []
    for message in messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, SystemPromptPart):
                if system_prompt is None:
                    system_prompt = part.content
            elif isinstance(part, UserPromptPart):
                steps.append({"role": "user", "content": part.content})
            elif isinstance(part, TextPart):
                steps.append({"role": "assistant", "content": part.content})
            elif isinstance(part, ToolCallPart):
                steps.append({"role": "tool_call", "tool": part.tool_name, "args": part.args})
            elif isinstance(part, ToolReturnPart):
                content = (
                    part.content
                    if isinstance(part.content, str)
                    else json.dumps(part.content, default=str)
                )
                if compress:
                    content = compress_content(content, max_chars=max_chars)
                steps.append({"role": "tool_result", "tool": part.tool_name, "content": content})
    return {"system_prompt": system_prompt, "steps": steps, "count": len(steps)}


def compress_messages(payloads: list[str], *, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """Elide large tool returns in serialized messages, re-serializing the rest."""
    from agentkit.session import deserialize_messages, serialize_message

    out: list[str] = []
    for payload in payloads:
        for message in deserialize_messages([payload]):
            for part in getattr(message, "parts", []):
                if isinstance(part, ToolReturnPart) and isinstance(part.content, str):
                    part.content = compress_content(part.content, max_chars=max_chars)
            out.append(serialize_message(message))
    return out


async def iter_trajectories(
    repos: Any,
    *,
    limit_conversations: int = 50,
    limit_messages: int = 200,
    compress: bool = False,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> AsyncIterator[dict[str, Any]]:
    """Yield an exported trajectory for each stored conversation (best-effort)."""
    from agentkit.session import deserialize_messages

    for conversation in await repos.conversations.list(limit=limit_conversations):
        rows = await repos.messages.list(conversation.id, limit=limit_messages)
        messages = deserialize_messages([row.payload for row in rows])
        if not messages:
            continue
        trajectory = export_trajectory(messages, compress=compress, max_chars=max_chars)
        trajectory["conversation_id"] = conversation.id
        yield trajectory


def render_jsonl(trajectories: Iterable[dict[str, Any]]) -> str:
    """Render trajectories as newline-delimited JSON."""
    return "\n".join(json.dumps(item, ensure_ascii=False, default=str) for item in trajectories)
