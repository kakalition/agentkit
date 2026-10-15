"""Durable scheduler: recurring (cron) and one-off jobs, executed by DBOS.

Jobs are stored in the database; a single DBOS cron workflow (:func:`tick`,
every minute) enqueues due jobs as durable workflows with a deterministic
workflow id, so a job runs exactly once even across restarts.

Register a task with the decorator, then schedule it:

    @agentkit.scheduler.task("daily_digest")
    def daily_digest(*, period: str = "last-month") -> None:
        ...

    agentkit.scheduler.init_scheduler()
    agentkit.scheduler.schedule_cron("digest", "0 8 * * 1", "daily_digest", args={"period": "last-month"})
    agentkit.scheduler.schedule_once("reminder", "2026-11-01T09:00", "daily_digest")
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from croniter import croniter
from dbos import DBOS, SetWorkflowID

from agentkit import durability
from agentkit._sync import run_sync
from agentkit.config import AgentSettings, get_settings
from agentkit.db.repositories import Repositories
from agentkit.runtime import Runtime, build_runtime, repositories
from agentkit.support import register_driver
from agentkit.support.kinds import DriverKind, SchedulerDriver
from agentkit.support.manager import Manager

TASKS: dict[str, Callable[..., Any]] = {}
TICK_SCHEDULE_NAME = "agentkit-scheduler-tick"
WORKER_QUEUE = "agentkit"
_runtime: Runtime | None = None


def task(name: str):
    """Register a callable (sync or async) under ``name`` so it can be scheduled."""

    def decorator(function: Callable[..., Any]) -> Callable[..., Any]:
        TASKS[name] = function
        return function

    return decorator


async def invoke_task(task_name: str, args_json: str = "{}") -> Any:
    from agentkit import metrics

    function = TASKS.get(task_name)
    if function is None:
        raise ValueError(f"no task registered as {task_name!r}")
    try:
        result = function(**json.loads(args_json or "{}"))
        if inspect.isawaitable(result):
            result = await result
    except Exception:
        metrics.record_scheduler_run(task_name, "error")
        raise
    metrics.record_scheduler_run(task_name, "ok")
    return result


@dataclass
class DueJob:
    name: str
    task: str
    args_json: str
    run_key: str


def due_jobs(jobs: list[Any], now: datetime) -> list[DueJob]:
    """Pure function: which enabled jobs are due at ``now`` (minute granularity)."""
    due: list[DueJob] = []
    for job in jobs:
        if not job.enabled:
            continue
        if job.kind == "once":
            try:
                run_at = datetime.fromisoformat(job.schedule)
            except ValueError:
                continue
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=UTC)
            if run_at <= now:
                due.append(DueJob(job.name, job.task, job.args, run_at.isoformat()))
        else:
            try:
                matches = croniter.match(job.schedule, now)
            except (ValueError, KeyError):
                continue
            if matches:
                due.append(DueJob(job.name, job.task, job.args, now.strftime("%Y-%m-%dT%H:%M")))
    return due


# --------------------------------------------------------------------------
# DBOS execution path
# --------------------------------------------------------------------------


def _require_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        _runtime = build_runtime(get_settings())
    return _runtime


async def load_due(now_iso: str) -> list[dict[str, str]]:
    now = datetime.fromisoformat(now_iso)
    async with repositories(_require_runtime()) as repos:
        jobs = await repos.schedules.list(enabled_only=True)
        return [
            {"name": d.name, "task": d.task, "args": d.args_json, "run_key": d.run_key}
            for d in due_jobs(jobs, now)
        ]


async def record_run(name: str) -> None:
    async with repositories(_require_runtime()) as repos:
        await repos.schedules.record_run(name)


# DBOS steps stay sync (the durable seam) and drive the async data layer on a
# private loop, so DB work never runs on the caller's event loop.
def _load_due_step_fn(now_iso: str) -> list[dict[str, str]]:
    return run_sync(load_due(now_iso))


def _record_run_step_fn(name: str) -> None:
    run_sync(record_run(name))


_load_due_step = DBOS.step()(_load_due_step_fn)
_record_run_step = DBOS.step()(_record_run_step_fn)


@DBOS.step(retries_allowed=True, max_attempts=3, backoff_rate=2.0)
def _invoke_step(task_name: str, args_json: str) -> Any:
    return run_sync(invoke_task(task_name, args_json))


@DBOS.workflow()
def run_job(task_name: str, args_json: str) -> Any:
    """Durable run of one registered task."""
    return _invoke_step(task_name, args_json)


@DBOS.workflow()
def tick(scheduled_time: Any = None, context: Any = None) -> list[str]:
    """Enqueues all jobs due at the current minute (exactly once per run key).

    DBOS invokes scheduled workflows as ``fn(scheduled_time, context)``; the
    arguments are unused here because due-ness is computed from the clock.
    """
    due = _load_due_step(datetime.now(UTC).isoformat())
    fired: list[str] = []
    for item in due:
        with SetWorkflowID(f"job:{item['name']}:{item['run_key']}"):
            DBOS.start_workflow(run_job, item["task"], item["args"])
        _record_run_step(item["name"])
        fired.append(item["name"])
    return fired


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def configure(
    settings: AgentSettings | None = None,
    *,
    repos_factory: type[Repositories] = Repositories,
) -> Runtime:
    """Point the scheduler at a runtime (no DBOS launch); for CRUD/reads."""
    global _runtime
    _runtime = build_runtime(settings or get_settings(), repos_factory=repos_factory)
    return _runtime


def ensure_configured(
    settings: AgentSettings | None = None,
    *,
    repos_factory: type[Repositories] = Repositories,
) -> Runtime:
    """Configure the scheduler runtime **only if** none is set yet.

    Unlike :func:`configure`, this never clobbers a runtime already installed by
    ``init_scheduler`` in the same process — the in-process web UI reuses it.
    """
    global _runtime
    if _runtime is None:
        _runtime = build_runtime(settings or get_settings(), repos_factory=repos_factory)
    return _runtime


def init_scheduler(
    settings: AgentSettings | None = None,
    *,
    repos_factory: type[Repositories] = Repositories,
    tick_cron: str = "* * * * *",
) -> Runtime:
    """Launch DBOS, register the worker queue + the every-minute tick."""
    settings = settings or get_settings()
    durability.init(settings, queues=[WORKER_QUEUE])
    runtime = configure(settings, repos_factory=repos_factory)
    durability.apply_schedules(
        [{"schedule_name": TICK_SCHEDULE_NAME, "workflow_fn": tick, "schedule": tick_cron}]
    )
    return runtime


async def schedule_cron(
    name: str, cron: str, task_name: str, *, args: dict[str, Any] | None = None, enabled: bool = True
) -> None:
    """Add or update a recurring job."""
    croniter(cron)  # validate the expression
    async with repositories(_require_runtime()) as repos:
        await repos.schedules.upsert(
            name, kind="cron", schedule=cron, task=task_name, args=json.dumps(args or {}), enabled=enabled
        )


async def schedule_once(
    name: str, when: datetime | str, task_name: str, *, args: dict[str, Any] | None = None
) -> None:
    """Add or update a one-off job that fires at/after ``when``."""
    moment = when if isinstance(when, datetime) else datetime.fromisoformat(str(when))
    async with repositories(_require_runtime()) as repos:
        await repos.schedules.upsert(
            name, kind="once", schedule=moment.isoformat(), task=task_name, args=json.dumps(args or {})
        )


async def list_jobs() -> list[dict[str, Any]]:
    async with repositories(_require_runtime()) as repos:
        return [
            {
                "name": job.name,
                "kind": job.kind,
                "schedule": job.schedule,
                "task": job.task,
                "args": json.loads(job.args or "{}"),
                "enabled": job.enabled,
                "last_run": job.last_run.isoformat() if job.last_run else None,
                "run_count": job.run_count,
            }
            for job in await repos.schedules.list()
        ]


async def set_enabled(name: str, enabled: bool) -> bool:
    """Enable or disable a scheduled job (keeps its definition)."""
    async with repositories(_require_runtime()) as repos:
        return await repos.schedules.set_enabled(name, enabled)


async def remove_job(name: str) -> bool:
    async with repositories(_require_runtime()) as repos:
        return await repos.schedules.remove(name)


async def run_due_now(now: datetime | None = None) -> list[str]:
    """Run due jobs inline (non-durable). Handy for tests and a CLI catch-up."""
    now = now or datetime.now(UTC)
    async with repositories(_require_runtime()) as repos:
        due = due_jobs(await repos.schedules.list(enabled_only=True), now)
        for item in due:
            await invoke_task(item.task, item.args_json)
            await repos.schedules.record_run(item.name)
    return [item.name for item in due]


# --------------------------------------------------------------------------
# Drivers
# --------------------------------------------------------------------------


class DBOSCronScheduler:
    """The default scheduler driver: durable DBOS cron (see the module functions)."""

    def __init__(self, app: Any = None) -> None:
        self.app = app

    async def schedule_cron(
        self,
        name: str,
        cron: str,
        task_name: str,
        *,
        args: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> None:
        await schedule_cron(name, cron, task_name, args=args, enabled=enabled)

    async def schedule_once(
        self,
        name: str,
        when: datetime | str,
        task_name: str,
        *,
        args: dict[str, Any] | None = None,
    ) -> None:
        await schedule_once(name, when, task_name, args=args)

    async def list_jobs(self) -> list[dict[str, Any]]:
        return await list_jobs()

    async def set_enabled(self, name: str, enabled: bool) -> bool:
        return await set_enabled(name, enabled)

    async def remove_job(self, name: str) -> bool:
        return await remove_job(name)

    async def run_due_now(self, now: datetime | None = None) -> list[str]:
        return await run_due_now(now)


class _MemoryJob:
    def __init__(self, name: str, kind: str, schedule: str, task: str, args: str, enabled: bool) -> None:
        self.name = name
        self.kind = kind
        self.schedule = schedule
        self.task = task
        self.args = args
        self.enabled = enabled


class MemoryScheduler:
    """An in-process scheduler driver (no database, no DBOS)."""

    def __init__(self, app: Any = None) -> None:
        self.app = app
        self._jobs: dict[str, dict[str, Any]] = {}
        self._runs: dict[str, int] = {}

    async def schedule_cron(
        self,
        name: str,
        cron: str,
        task_name: str,
        *,
        args: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> None:
        croniter(cron)
        self._jobs[name] = {
            "name": name,
            "kind": "cron",
            "schedule": cron,
            "task": task_name,
            "args": json.dumps(args or {}),
            "enabled": enabled,
            "run_count": self._runs.get(name, 0),
        }

    async def schedule_once(
        self,
        name: str,
        when: datetime | str,
        task_name: str,
        *,
        args: dict[str, Any] | None = None,
    ) -> None:
        moment = when if isinstance(when, datetime) else datetime.fromisoformat(str(when))
        self._jobs[name] = {
            "name": name,
            "kind": "once",
            "schedule": moment.isoformat(),
            "task": task_name,
            "args": json.dumps(args or {}),
            "enabled": True,
            "run_count": self._runs.get(name, 0),
        }

    async def list_jobs(self) -> list[dict[str, Any]]:
        return [dict(job) for job in self._jobs.values()]

    async def set_enabled(self, name: str, enabled: bool) -> bool:
        job = self._jobs.get(name)
        if job is None:
            return False
        job["enabled"] = enabled
        return True

    async def remove_job(self, name: str) -> bool:
        return self._jobs.pop(name, None) is not None

    async def run_due_now(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now(UTC)
        jobs = [
            _MemoryJob(j["name"], j["kind"], j["schedule"], j["task"], j["args"], j["enabled"])
            for j in self._jobs.values()
        ]
        fired: list[str] = []
        for item in due_jobs(jobs, now):
            await invoke_task(item.task, item.args_json)
            self._runs[item.name] = self._runs.get(item.name, 0) + 1
            fired.append(item.name)
        return fired


class SchedulerManager(Manager):
    """Resolves the configured scheduler driver (``scheduler_driver``, default ``dbos``)."""

    kind = DriverKind.SCHEDULER
    default_driver = SchedulerDriver.DBOS


@register_driver(DriverKind.SCHEDULER, SchedulerDriver.DBOS)
def _dbos_scheduler_driver(app: Any) -> DBOSCronScheduler:
    return DBOSCronScheduler(app)


@register_driver(DriverKind.SCHEDULER, SchedulerDriver.MEMORY)
def _memory_scheduler_driver(app: Any) -> MemoryScheduler:
    return MemoryScheduler(app)
