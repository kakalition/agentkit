"""Proactive memory nudges.

A nudge periodically scans the recent conversation and queues any durable facts
or preferences it finds as **proposed** memories for review — it never writes to
memory directly. It is off by default (``memory_nudge_every = 0``); the ``free``
posture is the natural place to enable it.
"""

from __future__ import annotations

from typing import Any

__all__ = ["register_memory_nudges"]


def register_memory_nudges(app: Any, *, every: int | None = None) -> Any:
    """Register a ``turn.end`` listener that proposes memories every ``every`` turns.

    Returns the listener (or ``None`` when the cadence is non-positive). The
    cadence defaults to the ``memory_nudge_every`` setting; it is counted per
    conversation.
    """
    settings = app.settings
    cadence = int(every if every is not None else getattr(settings, "memory_nudge_every", 0) or 0)
    if cadence <= 0:
        return None
    counts: dict[str, int] = {}

    async def on_turn_end(event: Any) -> None:
        conversation_id = _field(event, "conversation_id")
        if not conversation_id:
            return
        counts[conversation_id] = counts.get(conversation_id, 0) + 1
        if counts[conversation_id] % cadence:
            return
        from agentkit.learning import propose_memories

        async with app.repositories() as repos:
            await propose_memories(
                repos,
                model=getattr(app, "_model", None),
                conversation_id=conversation_id,
                settings=settings,
            )

    app.on("turn.end", on_turn_end)
    return on_turn_end


def _field(event: Any, name: str) -> Any:
    if hasattr(event, "get"):
        return event.get(name)
    return getattr(event, name, None)
