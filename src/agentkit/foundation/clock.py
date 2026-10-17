"""A tiny clock seam so tests can travel in time (``freeze_time``).

New foundation code reads ``now()`` instead of ``datetime.now(UTC)`` directly, so
``freeze_time`` / ``travel`` can shift it::

    from agentkit.testing import freeze_time
    from datetime import datetime, UTC

    with freeze_time(datetime(2030, 1, 1, tzinfo=UTC)):
        await Note.create(...)   # timestamps land in 2030

Time travel is process-local and best-effort: modules that predate this seam still
call ``datetime.now`` directly.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

__all__ = ["freeze_time", "now", "travel", "travel_back"]

_frozen: datetime | None = None


def now() -> datetime:
    """The current time (or the frozen time when traveling)."""
    return _frozen if _frozen is not None else datetime.now(UTC)


@contextlib.contextmanager
def freeze_time(when: datetime) -> Iterator[datetime]:
    """Freeze :func:`now` at ``when`` for the duration of the block."""
    global _frozen
    previous = _frozen
    _frozen = when
    try:
        yield when
    finally:
        _frozen = previous


@contextlib.contextmanager
def travel(*, days: float = 0, seconds: float = 0, hours: float = 0, minutes: float = 0) -> Iterator[datetime]:
    """Advance the clock from :func:`now` by the given span for the block."""
    delta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    with freeze_time(now() + delta) as when:
        yield when


def travel_back() -> None:
    """Clear any frozen time."""
    global _frozen
    _frozen = None
