"""The realtime-voice contract — a duplex audio/text session.

A realtime session connects to a speech-to-speech or streaming provider, accepts
audio/text input, and yields events (transcripts, audio deltas, tool calls) until
closed. ``PydanticAIRealtime`` wraps PydanticAI's realtime integration (optional
extra); ``LoopbackRealtime`` is an in-process implementation for tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

__all__ = ["RealtimeSession"]


@runtime_checkable
class RealtimeSession(Protocol):
    """A duplex realtime voice/text session."""

    async def connect(self) -> None: ...

    async def send_audio(self, chunk: bytes) -> None: ...

    async def send_text(self, text: str) -> None: ...

    def stream_events(self) -> AsyncIterator[Any]: ...

    async def interrupt(self) -> None: ...

    async def close(self) -> None: ...
