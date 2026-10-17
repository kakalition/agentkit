"""Realtime voice drivers — a PydanticAI-backed session or an in-memory loopback.

``LoopbackRealtime`` is a deterministic, dependency-free duplex session used by
tests and the default ``realtime_driver=loopback``. ``PydanticAIRealtime`` wraps
PydanticAI's realtime integration and lazy-imports it on connect, raising
:class:`~agentkit.errors.ConfigurationError` naming the ``realtime`` extra when
absent (construction stays import-safe).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from agentkit.contracts.realtime import RealtimeSession
from agentkit.errors import ConfigurationError
from agentkit.support import Driver, register_driver
from agentkit.support.kinds import DriverKind, RealtimeDriver
from agentkit.support.manager import Manager

__all__ = [
    "LoopbackRealtime",
    "PydanticAIRealtime",
    "RealtimeManager",
    "RealtimeSession",
]


def _missing_extra(extra: str) -> ConfigurationError:
    return ConfigurationError(
        f"this realtime driver needs the {extra!r} extra (pip install agentkit[{extra}])"
    )


class LoopbackRealtime:
    """An in-memory duplex session: echoes input events until closed."""

    def __init__(self, *, model: str | None = None) -> None:
        self.model = model
        self.connected = False
        self.closed = False
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.interruptions = 0

    async def connect(self) -> None:
        self.connected = True
        await self._queue.put({"type": "connected", "model": self.model})

    async def send_audio(self, chunk: bytes) -> None:
        await self._queue.put({"type": "audio", "bytes": len(chunk)})

    async def send_text(self, text: str) -> None:
        await self._queue.put({"type": "text", "text": text})
        await self._queue.put({"type": "transcript", "text": text})

    async def stream_events(self) -> AsyncIterator[dict[str, Any]]:
        while not self.closed:
            event = await self._queue.get()
            yield event
            if event.get("type") == "closed":
                break

    async def interrupt(self) -> None:
        self.interruptions += 1
        await self._queue.put({"type": "interrupted"})

    async def close(self) -> None:
        self.closed = True
        await self._queue.put({"type": "closed"})


class PydanticAIRealtime:
    """A realtime session backed by PydanticAI (optional ``realtime`` extra)."""

    def __init__(self, *, model: str | None = None, agent: Any = None) -> None:
        self.model = model
        self.agent = agent
        self._session: Any = None

    async def connect(self) -> None:
        try:
            import pydantic_ai.realtime  # noqa: F401
        except ImportError as exc:  # pragma: no cover - exercised only with the extra
            raise _missing_extra("realtime") from exc
        if self.agent is None:
            try:
                from pydantic_ai import Agent as PydanticAgent

                self.agent = PydanticAgent(self.model or "openai:gpt-4o-realtime-preview")
            except Exception as exc:  # pragma: no cover - defensive
                raise _missing_extra("realtime") from exc
        self._session = self.agent  # the realtime loop is driven via stream_events

    async def send_audio(self, chunk: bytes) -> None:
        session = self._require()
        await _maybe(session, "send_audio", chunk)

    async def send_text(self, text: str) -> None:
        session = self._require()
        await _maybe(session, "send_text", text)

    async def stream_events(self) -> AsyncIterator[Any]:
        session = self._require()
        stream = getattr(session, "stream_events", None)
        if stream is None:  # pragma: no cover - provider shape varies
            return
        async for event in stream():
            yield event

    async def interrupt(self) -> None:
        session = self._require()
        await _maybe(session, "interrupt")

    async def close(self) -> None:
        if self._session is not None:
            await _maybe(self._session, "close")
        self._session = None

    def _require(self) -> Any:
        if self._session is None:
            raise ConfigurationError("realtime session is not connected; call connect() first")
        return self._session


async def _maybe(target: Any, method: str, *args: Any) -> None:
    function = getattr(target, method, None)
    if function is None:
        return
    result = function(*args)
    if asyncio.iscoroutine(result):
        await result


class RealtimeManager(Manager):
    """Resolves the configured realtime driver (``realtime_driver``)."""

    kind = DriverKind.REALTIME
    default_driver = RealtimeDriver.LOOPBACK

    def create_loopback_driver(self, app: Any) -> LoopbackRealtime:
        return LoopbackRealtime(model=getattr(app.settings, "realtime_model", None))

    def create_pydantic_ai_driver(self, app: Any) -> PydanticAIRealtime:
        return PydanticAIRealtime(model=getattr(app.settings, "realtime_model", None))


@register_driver(DriverKind.REALTIME, RealtimeDriver.LOOPBACK)
class LoopbackRealtimeDriver(Driver):
    def build(self) -> LoopbackRealtime:
        app = self.app
        return LoopbackRealtime(model=getattr(app.settings, "realtime_model", None))
@register_driver(DriverKind.REALTIME, RealtimeDriver.PYDANTIC_AI)
class PydanticRealtimeDriver(Driver):
    def build(self) -> PydanticAIRealtime:
        app = self.app
        return PydanticAIRealtime(model=getattr(app.settings, "realtime_model", None))
