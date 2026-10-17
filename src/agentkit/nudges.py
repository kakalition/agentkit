"""Proactive memory nudges.

A nudge periodically scans the recent conversation and queues any durable facts
or preferences it finds as **proposed** memories for review — it never writes to
memory directly. It is off by default (``memory_nudge_every = 0``); the ``free``
posture is the natural place to enable it.
"""

from __future__ import annotations

from typing import Any

from agentkit.foundation.events import Listener

__all__ = ["register_memory_nudges"]


class MemoryNudgeListener(Listener):
    """A ``turn.end`` listener that proposes memories every ``cadence`` turns."""

    event = "turn.end"

    def __init__(self, app: Any, *, cadence: int) -> None:
        self.app = app
        self.settings = app.settings
        self.cadence = cadence
        self.counts: dict[str, int] = {}

    async def handle(self, event: Any) -> None:
        conversation_id = _field(event, "conversation_id")
        if not conversation_id:
            return
        self.counts[conversation_id] = self.counts.get(conversation_id, 0) + 1
        if self.counts[conversation_id] % self.cadence:
            return
        from agentkit.learning import propose_memories

        async with self.app.repositories() as repos:
            await propose_memories(
                repos,
                model=getattr(self.app, "_model", None),
                conversation_id=conversation_id,
                settings=self.settings,
            )


def register_memory_nudges(app: Any, *, every: int | None = None) -> Any:
    """Register a ``turn.end`` listener that proposes memories every ``every`` turns.

    Returns the :class:`MemoryNudgeListener` (or ``None`` when the cadence is
    non-positive). The cadence defaults to the ``memory_nudge_every`` setting; it
    is counted per conversation.
    """
    cadence = int(every if every is not None else getattr(app.settings, "memory_nudge_every", 0) or 0)
    if cadence <= 0:
        return None
    listener = MemoryNudgeListener(app, cadence=cadence)
    app.listeners([listener])
    return listener


def _field(event: Any, name: str) -> Any:
    if hasattr(event, "get"):
        return event.get(name)
    return getattr(event, name, None)
