"""Durable execution on DBOS Transact (local SQLite system database).

Infrastructure only: init/launch, queues, schedules, and re-exports of the DBOS
decorators. Applications define their own ``@DBOS.workflow`` / ``@DBOS.step``
functions at module level (DBOS requires it).
"""

from __future__ import annotations

import threading
from typing import Any

from dbos import DBOS, DBOSConfig, SetWorkflowID

from agentkit.config import AgentSettings, get_settings

__all__ = [
    "DBOS",
    "SetWorkflowID",
    "init",
    "register_queue",
    "enqueue",
    "apply_schedules",
    "list_schedules",
    "failed_workflows",
]

_lock = threading.Lock()
_initialized = False
_launched = False
_queues: set[str] = set()


def system_database_url(settings: AgentSettings) -> str:
    return f"sqlite:///{settings.agent_home / 'dbos.sqlite'}"


def init(
    settings: AgentSettings | None = None,
    *,
    launch: bool = True,
    queues: list[str] | dict[str, dict[str, Any]] | None = None,
) -> type[DBOS]:
    """Configure and launch DBOS once per process, registering queues once.

    ``queues`` may be a list of names or a mapping of ``name -> options``
    (``worker_concurrency``, ``concurrency``, ``limiter``, ``polling_interval_sec``…).
    """
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
        items = queues.items() if isinstance(queues, dict) else [(q, {}) for q in (queues or [])]
        for name, options in items:
            if name not in _queues:
                DBOS.register_queue(name, **options)
                _queues.add(name)
    return DBOS


def failed_workflows(*, queue: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Recently failed workflows (a dead-letter view)."""
    workflows = DBOS.list_workflows(
        status=["ERROR", "MAX_RECOVERY_ATTEMPTS_EXCEEDED"],
        queue_name=queue,
        limit=limit,
        sort_desc=True,
    )
    return [
        {
            "id": w.workflow_id,
            "name": w.name,
            "status": w.status,
            "queue": w.queue_name,
            "error": w.error,
        }
        for w in workflows
    ]


def register_queue(name: str, **kwargs: Any) -> Any:
    if name not in _queues:
        DBOS.register_queue(name, **kwargs)
        _queues.add(name)
    return name


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
