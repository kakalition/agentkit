"""The scheduler contract — recurring and one-off job definitions."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

__all__ = ["SchedulerDriver"]


@runtime_checkable
class SchedulerDriver(Protocol):
    """Manage recurring/one-off schedules."""

    async def schedule_cron(
        self,
        name: str,
        cron: str,
        task_name: str,
        *,
        args: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> None: ...

    async def schedule_once(
        self,
        name: str,
        when: datetime | str,
        task_name: str,
        *,
        args: dict[str, Any] | None = None,
    ) -> None: ...

    async def list_jobs(self) -> list[dict[str, Any]]: ...

    async def set_enabled(self, name: str, enabled: bool) -> bool: ...

    async def remove_job(self, name: str) -> bool: ...

    async def run_due_now(self, now: datetime | None = None) -> list[str]: ...
