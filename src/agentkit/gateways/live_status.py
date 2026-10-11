"""Live turn progress for chat channels.

While the model works, a status bubble is edited every few seconds with a new
persona-like phrase so the chat never looks idle. Phrases are drawn from a large
shuffled deck, so the same line rarely repeats.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress

DEFAULT_STATUS_INTERVAL_S = 2.5
DEFAULT_TYPING_INTERVAL_S = 4.0


class PhraseDeck:
    """Endless, non-repeating shuffled sequence over actions × objects × emoji."""

    def __init__(
        self,
        actions: Sequence[str],
        objects: Sequence[str],
        emojis: Sequence[str],
        *,
        template: str = "{emoji} {action} {object}…",
        seed: int | None = None,
    ) -> None:
        self._actions = tuple(actions)
        self._objects = tuple(objects)
        self._emojis = tuple(emojis)
        self._template = template
        self._count = len(self._actions) * len(self._objects) * len(self._emojis)
        self._rng = random.Random(seed)
        self._deck: list[int] = []

    @property
    def size(self) -> int:
        return self._count

    def next(self) -> str:
        if self._count == 0:
            return "thinking…"
        if not self._deck:
            self._deck = list(range(self._count))
            self._rng.shuffle(self._deck)
        idx = self._deck.pop()
        per_action = len(self._objects)
        per_emoji = len(self._actions) * per_action
        emoji = idx // per_emoji
        rest = idx % per_emoji
        action = rest // per_action
        obj = rest % per_action
        return self._template.format(
            emoji=self._emojis[emoji], action=self._actions[action], object=self._objects[obj]
        )


_THINK_ACTIONS = (
    "mulling over",
    "scrolling through",
    "turning over",
    "sifting through",
    "noodling on",
    "poking at",
    "sketching out",
    "untangling",
    "weighing up",
    "lining up",
    "chewing on",
    "rummaging through",
    "piecing together",
    "double-checking",
    "tracing",
    "simmering on",
    "gathering",
    "polishing",
    "re-reading",
    "squinting at",
    "tidying up",
    "revisiting",
    "threading together",
    "mapping out",
    "puzzling over",
    "smoothing out",
    "shuffling",
    "plucking at",
    "brewing",
    "unpacking",
)
_THINK_OBJECTS = (
    "the details",
    "that thought",
    "the moving parts",
    "the fine print",
    "the pieces",
    "the options",
    "the angles",
    "the threads",
    "the possibilities",
    "the wording",
    "the next step",
    "the edges",
    "the plan",
    "the numbers",
    "the loose ends",
    "the shape of it",
    "the trade-offs",
    "the timing",
    "the bigger picture",
    "the small stuff",
    "the breadcrumbs",
    "the why",
    "the how",
    "the whole thing",
    "a few ideas",
    "the quiet parts",
    "the half-formed bits",
    "the shape of the answer",
)
_THINK_EMOJI = (
    "🧠",
    "✨",
    "🤔",
    "🌀",
    "📝",
    "🔍",
    "🧩",
    "💭",
    "🌿",
    "⚙️",
    "🪄",
    "📚",
    "🗺️",
    "🕰️",
    "🫧",
    "🧵",
    "🛠️",
    "🔮",
    "🌟",
    "☕",
    "🍃",
    "🧭",
    "🪶",
    "🎨",
    "🧮",
    "📎",
    "🌤️",
    "🪴",
    "🫖",
    "🧊",
    "🕯️",
    "🎧",
    "💡",
    "🔖",
    "🧷",
    "📐",
    "🧪",
    "🌈",
    "🫐",
    "🌸",
    "🧸",
    "🎐",
    "🪁",
)

_THINK_DECK = PhraseDeck(_THINK_ACTIONS, _THINK_OBJECTS, _THINK_EMOJI)


def thinking_phrase() -> str:
    return _THINK_DECK.next()


def idle_phrase(index: int = 0, phrases: Sequence[str] | None = None) -> str:
    """A creative thinking line. Explicit ``phrases`` are indexed modulo; the
    default pool is a large shuffled deck."""
    if phrases is not None:
        pool = tuple(phrases)
        if pool:
            return pool[index % len(pool)]
    return thinking_phrase()


async def typing_keepalive(
    send: Callable[[], Awaitable[None]],
    *,
    interval_s: float = DEFAULT_TYPING_INTERVAL_S,
    stop: asyncio.Event | None = None,
) -> None:
    """Refresh a chat 'typing' indicator while a turn runs."""
    stop = stop or asyncio.Event()
    while not stop.is_set():
        with suppress(Exception):
            await send()
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_s)
            return
        except TimeoutError:
            continue
