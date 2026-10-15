"""Durable execution on DBOS Transact (local SQLite system database).

Infrastructure only: init/launch, queues, schedules, and re-exports of the DBOS
decorators. Applications define their own ``@DBOS.workflow`` / ``@DBOS.step``
functions at module level (DBOS requires it).
"""

from __future__ import annotations

import threading
from typing import Any

from dbos import DBOS, DBOSClient, DBOSConfig, SetWorkflowID

from agentkit.config import AgentSettings, get_settings
from agentkit.contracts.durability import Durability
from agentkit.errors import ConfigurationError
from agentkit.support import register_driver
from agentkit.support.kinds import DriverKind, DurabilityDriver
from agentkit.support.manager import Manager

__all__ = [
    "DBOS",
    "DBOSClient",
    "DBOSDurability",
    "Durability",
    "DurabilityManager",
    "SetWorkflowID",
    "workflow",
    "step",
    "init",
    "register_queue",
    "enqueue",
    "apply_schedules",
    "list_schedules",
    "failed_workflows",
    # durable primitives
    "sleep",
    # workflow management
    "list_workflows",
    "get_workflow",
    "cancel_workflow",
    "resume_workflow",
    "client",
]

# Decorators (re-exported so apps use DBOS through agentkit).
workflow = DBOS.workflow
step = DBOS.step

_lock = threading.Lock()
_initialized = False
_launched = False
_queues: set[str] = set()


def system_database_url(settings: AgentSettings) -> str:
    return f"sqlite:///{settings.home / 'dbos.sqlite'}"


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


# --------------------------------------------------------------------------
# Durable primitives (thin pass-throughs to DBOS)
# --------------------------------------------------------------------------


def sleep(seconds: float) -> None:
    """Durable timer: survives restarts (used inside workflows)."""
    DBOS.sleep(seconds)


# --------------------------------------------------------------------------
# Workflow management
# --------------------------------------------------------------------------


def list_workflows(**kwargs: Any) -> list[Any]:
    return DBOS.list_workflows(**kwargs)


def get_workflow(workflow_id: str) -> Any:
    return DBOS.retrieve_workflow(workflow_id).get_status()


def cancel_workflow(workflow_id: str, *, cancel_children: bool = False) -> None:
    DBOS.cancel_workflow(workflow_id, cancel_children=cancel_children)


def resume_workflow(workflow_id: str, *, queue_name: str | None = None) -> Any:
    return DBOS.resume_workflow(workflow_id, queue_name=queue_name)


def client(settings: AgentSettings | None = None) -> DBOSClient:
    """A standalone DBOS client (inspect/enqueue without launching a worker)."""
    settings = settings or get_settings()
    settings.ensure_dirs()
    return DBOSClient(system_database_url=system_database_url(settings))


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


class DBOSDurability:
    """The default durability driver: DBOS Transact (see the module functions)."""

    def __init__(self, app: Any = None) -> None:
        self.app = app

    def init(
        self,
        settings: AgentSettings | None = None,
        *,
        launch: bool = True,
        queues: Any = None,
    ) -> Any:
        return init(settings, launch=launch, queues=queues)

    def register_queue(self, name: str, **options: Any) -> Any:
        return register_queue(name, **options)

    def enqueue(self, queue: str, func: Any, *args: Any, **kwargs: Any) -> str:
        return enqueue(queue, func, *args, **kwargs)

    def apply_schedules(self, schedules: list[dict[str, Any]]) -> None:
        apply_schedules(schedules)


class DurabilityManager(Manager):
    """Resolves the configured durability driver (``durability_driver``, default ``dbos``)."""

    kind = DriverKind.DURABILITY
    default_driver = DurabilityDriver.DBOS


@register_driver(DriverKind.DURABILITY, DurabilityDriver.DBOS)
def _dbos_durability_driver(app: Any) -> DBOSDurability:
    return DBOSDurability(app)


@register_driver(DriverKind.DURABILITY, DurabilityDriver.TEMPORAL)
def _temporal_durability_driver(app: Any) -> Any:
    try:
        import temporalio  # noqa: F401
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ConfigurationError(
            "the temporal durability driver needs the 'temporalio' package "
            "(pip install agentkit[temporal])"
        ) from exc
    raise ConfigurationError("the temporal durability driver is not implemented yet")


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
