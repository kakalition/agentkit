"""Natural-language scheduling — a small, deterministic time parser.

Turns phrases like "every day at 9am", "every monday at 8:30", "in 2 hours", or
"tomorrow at 8am" into a cron expression or a one-off datetime. It is deliberately
conservative: anything it cannot parse returns ``None`` so the caller can ask the
model (or the user) to be more specific.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

__all__ = ["NaturalSchedule", "parse_when"]

_DAY_NAMES = {
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
    "sunday": 0,
}
_IN = re.compile(r"in (\d+)\s*(minute|hour|day|week)s?")
_EVERY_N = re.compile(r"every (\d+)\s*(minute|hour)s?")


@dataclass
class NaturalSchedule:
    """A parsed schedule: ``kind`` is ``cron`` (with ``schedule``) or ``once``."""

    kind: str
    schedule: str | None = None
    at: datetime | None = None

    def describe(self) -> str:
        if self.kind == "cron":
            return f"cron {self.schedule}"
        return f"once at {self.at.isoformat() if self.at else '?'}"


def _parse_clock(text: str) -> tuple[int, int] | None:
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if match is None:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3)
    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def parse_when(text: str, *, now: datetime | None = None) -> NaturalSchedule | None:
    """Parse a natural-language time into a :class:`NaturalSchedule` (or ``None``)."""
    phrase = (text or "").strip().lower()
    if not phrase:
        return None
    moment = now or datetime.now()

    match = _IN.search(phrase)
    if match:
        count, unit = int(match.group(1)), match.group(2)
        delta = {
            "minute": timedelta(minutes=count),
            "hour": timedelta(hours=count),
            "day": timedelta(days=count),
            "week": timedelta(weeks=count),
        }[unit]
        return NaturalSchedule("once", at=moment + delta)

    match = _EVERY_N.search(phrase)
    if match:
        count, unit = int(match.group(1)), match.group(2)
        if unit == "minute":
            return NaturalSchedule("cron", schedule=f"*/{count} * * * *")
        return NaturalSchedule("cron", schedule=f"0 */{count} * * *")

    clock = _parse_clock(phrase)
    if clock is None:
        return None
    hour, minute = clock

    weekday = next((value for name, value in _DAY_NAMES.items() if name in phrase), None)
    if weekday is not None:
        return NaturalSchedule("cron", schedule=f"{minute} {hour} * * {weekday}")

    if "tomorrow" in phrase:
        at = (moment + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        return NaturalSchedule("once", at=at)
    if "today" in phrase:
        at = moment.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return NaturalSchedule("once", at=at)
    if "every" in phrase or "daily" in phrase:
        return NaturalSchedule("cron", schedule=f"{minute} {hour} * * *")
    return None
