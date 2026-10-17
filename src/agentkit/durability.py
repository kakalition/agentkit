"""Durable execution on DBOS Transact (local SQLite system database).

Infrastructure only: init/launch, queues, schedules, and re-exports of the DBOS
decorators. Applications define their own ``@DBOS.workflow`` / ``@DBOS.step``
functions at module level (DBOS requires it).
"""

from __future__ import annotations

import threading
from typing import Any
from uuid import uuid4

from dbos import DBOS, DBOSClient, DBOSConfig, SetWorkflowID

from agentkit._sync import run_sync
from agentkit.config import AgentSettings, get_settings
from agentkit.contracts.durability import Durability
from agentkit.errors import ConfigurationError
from agentkit.support import Driver, register_driver
from agentkit.support.kinds import DriverKind, DurabilityDriver
from agentkit.support.manager import Manager

__all__ = [
    "DBOS",
    "DBOSClient",
    "DBOSDurability",
    "Durability",
    "DurabilityManager",
    "SetWorkflowID",
    "TemporalDurability",
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
class DbosDurabilityDriver(Driver):
    def build(self) -> DBOSDurability:
        app = self.app
        return DBOSDurability(app)


def _require_temporalio() -> Any:
    """Lazily import ``temporalio`` or fail with the optional-extra message."""
    try:
        import temporalio
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ConfigurationError(
            "the temporal durability driver needs the 'temporalio' package "
            "(pip install agentkit[temporal])"
        ) from exc
    return temporalio


def _workflow_name(func: Any) -> str:
    """The fully-qualified name Temporal submits/schedules a workflow by."""
    module = getattr(func, "__module__", "") or ""
    qualname = getattr(func, "__qualname__", None) or getattr(func, "__name__", None)
    name = str(qualname) if qualname else str(func)
    return f"{module}.{name}" if module else name


def _temporal_schedule(name: str, task_queue: str, spec: dict[str, Any]) -> Any:
    """Build a Temporal ``Schedule`` for ``spec`` (``cron`` + optional timezone)."""
    from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleSpec

    action = ScheduleActionStartWorkflow(
        spec["workflow"],
        spec.get("args"),
        id=f"agentkit-schedule:{name}",
        task_queue=task_queue,
    )
    cron = spec.get("cron")
    return Schedule(
        action=action,
        spec=ScheduleSpec(
            cron_expressions=[str(cron)] if cron else [],
            time_zone_name=str(spec.get("timezone")) if spec.get("timezone") else None,
        ),
    )


class TemporalDurability:
    """Durable execution on Temporal (opt-in ``durability_driver=temporal``).

    ``enqueue`` submits a workflow by its fully-qualified name, so the target
    worker must have registered that workflow class (``temporalio.workflow.defn``)
    on the task queue — agentkit's DBOS-style decorators do not register a
    workflow with a Temporal worker. Schedules map to Temporal schedules by name.
    """

    def __init__(self, app: Any = None, *, settings: AgentSettings | None = None) -> None:
        self.app = app
        self.settings = settings or getattr(app, "settings", None) or get_settings()
        self._client: Any = None
        self._queues: dict[str, dict[str, Any]] = {}
        self._schedules: dict[str, dict[str, Any]] = {}
        self._launched = False

    @property
    def address(self) -> str:
        return str(getattr(self.settings, "temporal_address", "localhost:7233"))

    @property
    def namespace(self) -> str:
        return str(getattr(self.settings, "temporal_namespace", "default"))

    @property
    def task_queue(self) -> str:
        return str(getattr(self.settings, "temporal_task_queue", "agentkit"))

    @property
    def client(self) -> Any:
        """The connected async client (connected lazily on first use)."""
        if self._client is None:
            _require_temporalio()
            from temporalio.client import Client

            self._client = run_sync(Client.connect(self.address, namespace=self.namespace))
        return self._client

    def init(
        self,
        settings: AgentSettings | None = None,
        *,
        launch: bool = True,
        queues: Any = None,
    ) -> TemporalDurability:
        if settings is not None:
            self.settings = settings
        items = queues.items() if isinstance(queues, dict) else [(q, {}) for q in (queues or [])]
        for name, options in items:
            self.register_queue(name, **options)
        if launch and not self._launched:
            _ = self.client  # connect; workers are started by the app (class docstring)
            self._launched = True
        return self

    def register_queue(self, name: str, **options: Any) -> Any:
        self._queues[str(name)] = dict(options)
        return name

    def enqueue(self, queue: str, func: Any, *args: Any, **kwargs: Any) -> str:
        workflow_id = kwargs.pop("workflow_id", None) or kwargs.pop("id", None)
        name = _workflow_name(func)
        resolved_queue = str(queue or self.task_queue)
        if not args:
            payload: Any = None
        elif len(args) == 1:
            payload = args[0]
        else:
            payload = list(args)
        resolved_id = str(workflow_id or f"{resolved_queue}:{name}:{uuid4().hex}")

        async def _start() -> Any:
            return await self.client.start_workflow(
                name, payload, id=resolved_id, task_queue=resolved_queue, **kwargs
            )

        handle = run_sync(_start())
        return str(getattr(handle, "id", None) or resolved_id)

    def apply_schedules(self, schedules: list[dict[str, Any]]) -> None:
        for spec in schedules:
            name = str(spec.get("schedule_name") or spec.get("name") or "")
            if not name:
                continue
            self._schedules[name] = {
                "workflow": _workflow_name(spec.get("workflow_fn")),
                "cron": spec.get("schedule") or spec.get("cron"),
                "timezone": spec.get("cron_timezone") or spec.get("timezone"),
                "args": spec.get("args"),
            }
        if not self._schedules:
            return

        async def _apply() -> None:
            client = self.client
            for name, spec in self._schedules.items():
                schedule = _temporal_schedule(name, self.task_queue, spec)
                handle = client.get_schedule_handle(name)
                try:
                    await handle.describe()
                except Exception:
                    await client.create_schedule(name, schedule)
                else:
                    await handle.update(lambda _, _schedule=schedule: _schedule)

        run_sync(_apply())

    def list_schedules(self) -> list[dict[str, Any]]:
        """The schedules applied through this driver (name + cron + timezone)."""
        return [
            {"name": name, "cron": spec.get("cron"), "timezone": spec.get("timezone")}
            for name, spec in self._schedules.items()
        ]


@register_driver(DriverKind.DURABILITY, DurabilityDriver.TEMPORAL)
class TemporalDurabilityDriver(Driver):
    def build(self) -> TemporalDurability:
        app = self.app
        return TemporalDurability(app)


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
