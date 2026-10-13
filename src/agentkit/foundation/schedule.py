"""Fluent scheduling — Laravel's ``Schedule`` for durable agent jobs.

    app.schedule("digest").dailyAt("08:00")
    app.schedule("check_reminders").everyMinute()
    app.schedule("welcome").at(datetime(2030, 1, 1, 9, 0))

Declare schedules in a provider's ``register``/``boot``; the app applies them
(persisting durable jobs) at the end of ``boot()``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

__all__ = ["ScheduleBuilder"]


class ScheduleBuilder:
    """A chainable schedule definition for one task."""

    def __init__(
        self,
        task: str,
        *,
        name: str | None = None,
        args: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> None:
        self._spec: dict[str, Any] = {
            "name": name or f"schedule:{task}",
            "task": task,
            "args": args or {},
            "enabled": enabled,
        }

    # -- metadata -------------------------------------------------------
    def name(self, value: str) -> ScheduleBuilder:
        self._spec["name"] = value
        return self

    def args(self, **values: Any) -> ScheduleBuilder:
        self._spec["args"] = {**self._spec.get("args", {}), **values}
        return self

    def enabled(self, value: bool = True) -> ScheduleBuilder:
        self._spec["enabled"] = value
        return self

    def disabled(self) -> ScheduleBuilder:
        return self.enabled(False)

    def timezone(self, value: str) -> ScheduleBuilder:
        self._spec["timezone"] = value
        return self

    def description(self, value: str) -> ScheduleBuilder:
        self._spec["description"] = value
        return self

    def when(self, predicate: Any) -> ScheduleBuilder:
        self._spec["when_predicate"] = predicate
        return self

    def without_overlapping(self) -> ScheduleBuilder:
        self._spec["without_overlapping"] = True
        return self

    def on_one_server(self) -> ScheduleBuilder:
        self._spec["on_one_server"] = True
        return self

    def run_in_background(self) -> ScheduleBuilder:
        self._spec["run_in_background"] = True
        return self

    # -- cron frequencies ----------------------------------------------
    def cron(self, expression: str) -> ScheduleBuilder:
        self._spec.pop("when", None)
        self._spec["cron"] = expression
        return self

    def every_second(self) -> ScheduleBuilder:  # pragma: no cover - cron granularity is 1m
        raise ValueError("agentkit schedules are cron minute-granular; use every_minute()")

    def every_minute(self) -> ScheduleBuilder:
        return self.cron("* * * * *")

    def every_five_minutes(self) -> ScheduleBuilder:
        return self.cron("*/5 * * * *")

    def every_ten_minutes(self) -> ScheduleBuilder:
        return self.cron("*/10 * * * *")

    def every_fifteen_minutes(self) -> ScheduleBuilder:
        return self.cron("*/15 * * * *")

    def every_thirty_minutes(self) -> ScheduleBuilder:
        return self.cron("*/30 * * * *")

    def hourly(self, minute: int = 0) -> ScheduleBuilder:
        return self.cron(f"{minute} * * * *")

    def daily(self, hour: int = 0, minute: int = 0) -> ScheduleBuilder:
        return self.cron(f"{minute} {hour} * * *")

    def daily_at(self, time: str) -> ScheduleBuilder:
        hour, minute = _parse_clock(time)
        return self.daily(hour, minute)

    def weekly(self, day: int = 0, hour: int = 0, minute: int = 0) -> ScheduleBuilder:
        return self.cron(f"{minute} {hour} * * {day}")

    def weekly_on(self, day: int, time: str = "00:00") -> ScheduleBuilder:
        hour, minute = _parse_clock(time)
        return self.weekly(day, hour, minute)

    def monthly(self, day: int = 1, hour: int = 0, minute: int = 0) -> ScheduleBuilder:
        return self.cron(f"{minute} {hour} {day} * *")

    def monthly_on(self, day: int, time: str = "00:00") -> ScheduleBuilder:
        hour, minute = _parse_clock(time)
        return self.monthly(day, hour, minute)

    # -- one-off --------------------------------------------------------
    def at(self, when: str | datetime) -> ScheduleBuilder:
        self._spec.pop("cron", None)
        self._spec["when"] = when.isoformat() if isinstance(when, datetime) else when
        return self

    def once_at(self, when: str | datetime) -> ScheduleBuilder:
        return self.at(when)

    # -- output ---------------------------------------------------------
    def build(self) -> dict[str, Any]:
        return dict(self._spec)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Schedule({self._spec.get('name')!r}, {self._spec.get('cron') or self._spec.get('when')})"


def _parse_clock(value: str) -> tuple[int, int]:
    hour, _, minute = value.partition(":")
    return int(hour), int(minute or 0)
