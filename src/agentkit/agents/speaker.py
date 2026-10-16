"""Speaker-selection strategies for group chats (``speaker_driver``).

Each strategy answers "who speaks next?" for a roster + transcript. ``round_robin``
is the default; ``selector`` asks the model; ``moderator``/``all``/``manual`` cover
the other shapes.
"""

from __future__ import annotations

from typing import Any

from agentkit.contracts.speaker import SpeakerStrategy
from agentkit.support import register_driver
from agentkit.support.kinds import DriverKind, SpeakerDriver
from agentkit.support.manager import Manager

__all__ = [
    "AllSpeaker",
    "ManualSpeaker",
    "ModeratorSpeaker",
    "RoundRobinSpeaker",
    "SelectorSpeaker",
    "SpeakerManager",
    "SpeakerStrategy",
]


class RoundRobinSpeaker:
    """Rotate through the roster, one speaker per turn."""

    def __init__(self) -> None:
        self._cursor = 0

    async def select(
        self, roster: list[str], transcript: list[dict[str, str]], *, context: Any = None
    ) -> list[str]:
        if not roster:
            return []
        name = roster[self._cursor % len(roster)]
        self._cursor += 1
        return [name]


class ModeratorSpeaker:
    """Always ask a designated moderator (the first roster entry by default)."""

    def __init__(self, moderator: str | None = None) -> None:
        self.moderator = moderator

    async def select(
        self, roster: list[str], transcript: list[dict[str, str]], *, context: Any = None
    ) -> list[str]:
        if not roster:
            return []
        if self.moderator and self.moderator in roster:
            return [self.moderator]
        return [roster[0]]


class AllSpeaker:
    """Ask everyone in the roster."""

    async def select(
        self, roster: list[str], transcript: list[dict[str, str]], *, context: Any = None
    ) -> list[str]:
        return list(roster)


class ManualSpeaker:
    """Follow an explicit, repeating order of speakers."""

    def __init__(self, order: list[str] | None = None) -> None:
        self.order = list(order or [])
        self._cursor = 0

    async def select(
        self, roster: list[str], transcript: list[dict[str, str]], *, context: Any = None
    ) -> list[str]:
        if not self.order:
            return []
        name = self.order[self._cursor % len(self.order)]
        self._cursor += 1
        return [name] if name in roster else []


class SelectorSpeaker:
    """Ask the model to pick the next speaker (falls back to the first entry)."""

    def __init__(self, model: Any = None) -> None:
        self.model = model

    async def select(
        self, roster: list[str], transcript: list[dict[str, str]], *, context: Any = None
    ) -> list[str]:
        if not roster:
            return []
        model = self.model or getattr(getattr(context, "deps", None), "model", None)
        if model is None:
            return roster[:1]
        try:
            from pydantic_ai import Agent

            picker: Agent[Any, str] = Agent(
                model,
                output_type=str,
                instructions=(
                    "You are choosing the next speaker in a group chat. Reply with "
                    "exactly one name from the roster, and nothing else."
                ),
            )
            lines = [f"Roster: {', '.join(roster)}", "Transcript:"]
            lines.extend(f"{turn['speaker']}: {turn['text']}" for turn in transcript[-8:])
            lines.append("Next speaker:")
            result = await picker.run("\n".join(lines))
            choice = (getattr(result, "output", "") or "").strip().lower()
            for name in roster:
                if name.lower() == choice or name.lower() in choice:
                    return [name]
        except Exception:  # pragma: no cover - model/selector best effort
            pass
        return roster[:1]


class SpeakerManager(Manager):
    """Resolves the configured speaker strategy (``speaker_driver``, default ``round_robin``)."""

    kind = DriverKind.SPEAKER
    default_driver = SpeakerDriver.ROUND_ROBIN


@register_driver(DriverKind.SPEAKER, SpeakerDriver.ROUND_ROBIN)
def _round_robin_speaker(app: Any) -> RoundRobinSpeaker:
    return RoundRobinSpeaker()


@register_driver(DriverKind.SPEAKER, SpeakerDriver.MODERATOR)
def _moderator_speaker(app: Any) -> ModeratorSpeaker:
    return ModeratorSpeaker()


@register_driver(DriverKind.SPEAKER, SpeakerDriver.ALL)
def _all_speaker(app: Any) -> AllSpeaker:
    return AllSpeaker()


@register_driver(DriverKind.SPEAKER, SpeakerDriver.SELECTOR)
def _selector_speaker(app: Any) -> SelectorSpeaker:
    return SelectorSpeaker()


@register_driver(DriverKind.SPEAKER, SpeakerDriver.MANUAL)
def _manual_speaker(app: Any) -> ManualSpeaker:
    return ManualSpeaker()
