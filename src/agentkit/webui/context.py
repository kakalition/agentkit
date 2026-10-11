"""Shared request context for the web UI backend.

The FastAPI app is built once by :func:`agentkit.webui.app.build_webui_app` and
holds a :class:`WebUIContext` on ``app.state``. Routers pull it out with the
:func:`get_context` dependency.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Request

from agentkit.config import AgentSettings
from agentkit.runtime import Runtime
from agentkit.session import ChatResult

# A chat turn: ``(conversation_id, text) -> ChatResult``. Agents provide this so
# the UI runs the same :class:`~agentkit.session.ChatRunner` path as the CLI.
Answer = Callable[[str, str], Awaitable[ChatResult]]


@dataclass
class WebUIContext:
    runtime: Runtime
    settings: AgentSettings
    answer: Answer | None = None


def get_context(request: Request) -> WebUIContext:
    return request.app.state.webui  # type: ignore[no-any-return]


def context_of(app: Any) -> WebUIContext:
    return app.state.webui
