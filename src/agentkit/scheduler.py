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

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from croniter import croniter
from dbos import DBOS, SetWorkflowID

from agentkit import durability
from agentkit.config import AgentSettings, get_settings
from agentkit.db.repositories import Repositories
from agentkit.runtime import Runtime, build_runtime, repositories

TASKS: dict[str, Callable[..., Any]] = {}
TICK_SCHEDULE_NAME = "agentkit-scheduler-tick"
WORKER_QUEUE = "agentkit"
_runtime: Runtime | None = None


def task(name: str):
    """Register a callable under ``name`` so it can be scheduled."""

    def decorator(function: Callable[..., Any]) -> Callable[..., Any]:
        TASKS[name] = function
        return function

    return decorator


def invoke_task(task_name: str, args_json: str = "{}") -> Any:
    function = TASKS.get(task_name)
    if function is None:
        raise ValueError(f"no task registered as {task_name!r}")
    return function(**json.loads(args_json or "{}"))


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


def _load_due(now_iso: str) -> list[dict[str, str]]:
    now = datetime.fromisoformat(now_iso)
    with repositories(_require_runtime()) as repos:
        jobs = repos.schedules.list(enabled_only=True)
        return [
            {"name": d.name, "task": d.task, "args": d.args_json, "run_key": d.run_key}
            for d in due_jobs(jobs, now)
        ]


def _record_run(name: str) -> None:
    with repositories(_require_runtime()) as repos:
        repos.schedules.record_run(name)


_load_due_step = DBOS.step()(_load_due)
_record_run_step = DBOS.step()(_record_run)


@DBOS.step(retries_allowed=True, max_attempts=3, backoff_rate=2.0)
def _invoke_step(task_name: str, args_json: str) -> Any:
    return invoke_task(task_name, args_json)


@DBOS.workflow()
def run_job(task_name: str, args_json: str) -> Any:
    """Durable run of one registered task."""
    return _invoke_step(task_name, args_json)


@DBOS.workflow()
def tick() -> list[str]:
    """Enqueues all jobs due at the current minute (exactly once per run key)."""
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


def schedule_cron(
    name: str, cron: str, task_name: str, *, args: dict[str, Any] | None = None, enabled: bool = True
) -> None:
    """Add or update a recurring job."""
    croniter(cron)  # validate the expression
    with repositories(_require_runtime()) as repos:
        repos.schedules.upsert(
            name, kind="cron", schedule=cron, task=task_name, args=json.dumps(args or {}), enabled=enabled
        )


def schedule_once(
    name: str, when: datetime | str, task_name: str, *, args: dict[str, Any] | None = None
) -> None:
    """Add or update a one-off job that fires at/after ``when``."""
    moment = when if isinstance(when, datetime) else datetime.fromisoformat(str(when))
    with repositories(_require_runtime()) as repos:
        repos.schedules.upsert(
            name, kind="once", schedule=moment.isoformat(), task=task_name, args=json.dumps(args or {})
        )


def list_jobs() -> list[dict[str, Any]]:
    with repositories(_require_runtime()) as repos:
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
            for job in repos.schedules.list()
        ]


def remove_job(name: str) -> bool:
    with repositories(_require_runtime()) as repos:
        return repos.schedules.remove(name)


def run_due_now(now: datetime | None = None) -> list[str]:
    """Run due jobs inline (non-durable). Handy for tests and a CLI catch-up."""
    now = now or datetime.now(UTC)
    with repositories(_require_runtime()) as repos:
        due = due_jobs(repos.schedules.list(enabled_only=True), now)
        for item in due:
            invoke_task(item.task, item.args_json)
            repos.schedules.record_run(item.name)
    return [item.name for item in due]
