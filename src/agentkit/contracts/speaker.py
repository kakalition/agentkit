"""The speaker-selection contract for group chats.

A :class:`SpeakerStrategy` decides which participant(s) speak next given the
roster and the transcript so far. Strategies are resolved by
:class:`agentkit.support.Manager` for the ``speaker`` kind (``speaker_driver``).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["SpeakerStrategy"]


@runtime_checkable
class SpeakerStrategy(Protocol):
    """Pick the next speaker(s) from a roster."""

    async def select(
        self,
        roster: list[str],
        transcript: list[dict[str, str]],
        *,
        context: Any = None,
    ) -> list[str]:
        """Return the next speaker(s), or ``[]`` to end the conversation."""
        ...
