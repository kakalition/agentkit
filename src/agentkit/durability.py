"""Durable execution on DBOS Transact (local SQLite system database).

This module provides the *infrastructure* (init/launch, queues, schedules) and
re-exports DBOS decorators. Applications define their own ``@DBOS.workflow`` /
``@DBOS.step`` functions — DBOS requires them to be module-level.
"""

from __future__ import annotations

import threading
from typing import Any

from dbos import DBOS, DBOSConfig

from agentkit.config import AgentSettings, get_settings

_lock = threading.Lock()
_initialized = False
_launched = False


def system_database_url(settings: AgentSettings) -> str:
    return f"sqlite:///{settings.agent_home / 'dbos.sqlite'}"


def init(settings: AgentSettings | None = None, *, launch: bool = True) -> type[DBOS]:
    """Configure and launch DBOS once per process (idempotent)."""
    global _initialized, _launched
    settings = settings or get_settings()
    settings.ensure_dirs()
    with _lock:
        if not _initialized:
            DBOS(config=DBOSConfig(name=settings.agent_name, system_database_url=system_database_url(settings)))
            _initialized = True
        if launch and not _launched:
            DBOS.launch()
            _launched = True
    return DBOS


def register_queue(name: str, **kwargs: Any) -> Any:
    return DBOS.register_queue(name, **kwargs)


def enqueue(queue: str, func: Any, *args: Any, **kwargs: Any) -> str:
    handle = DBOS.enqueue_workflow(queue, func, *args, **kwargs)
    return handle.get_workflow_id()


def apply_schedules(schedules: list[dict[str, Any]]) -> None:
    DBOS.apply_schedules(schedules)  # type: ignore[arg-type]


def list_schedules() -> list[dict[str, Any]]:
    result = []
    for schedule in DBOS.list_schedules():
        get = schedule.get if isinstance(schedule, dict) else lambda k, s=schedule: getattr(s, k, None)
        result.append(
            {
                "name": get("schedule_name"),
                "cron": get("schedule"),
                "timezone": get("cron_timezone"),
            }
        )
    return result
