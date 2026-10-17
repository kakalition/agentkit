"""Native queue toolkit: enqueue background work and inspect the queue.

``enqueue_task`` runs a registered (allow-listed) scheduler task as a durable
job through :class:`RunRegisteredTask`; ``enqueue_job`` dispatches an allow-listed
:class:`~agentkit.foundation.queue.Job` class. Enqueues honour ``queue_enabled``
(inline when the queue is off, otherwise pushed to a worker).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic_ai import RunContext

from agentkit.deps import Deps
from agentkit.foundation.queue import Job
from agentkit.toolkits._common import app_of, emit_event, resolve_allow_list, resolve_list

__all__ = ["RunRegisteredTask", "_attach_queue"]


class RunRegisteredTask(Job):
    """A queued job that invokes a registered scheduler task by name."""

    def __init__(self, task: str, args: dict[str, Any] | None = None) -> None:
        self.task = task
        self.args = dict(args or {})

    async def handle(self, app: Any) -> Any:
        from agentkit.scheduler import invoke_task

        return await invoke_task(self.task, json.dumps(self.args))


def _job_view(record: Any) -> dict[str, Any]:
    return {
        "id": record.id,
        "queue": record.queue,
        "job": record.job,
        "attempts": record.attempts,
        "error": record.error,
    }


def _attach_queue(
    agent: Any,
    jobs: dict[str, Any] | None = None,
    tasks: list[str] | None = None,
    *,
    flag: str = "queue_tools_enabled",
) -> Any:
    """Register the queue tools on a built PydanticAI agent (idempotent)."""
    if getattr(agent, "_agentkit_queue_attached", False):
        return agent
    fallback = dict(jobs or {})
    task_fallback = list(tasks or [])

    def _jobs(ctx: RunContext[Deps]) -> dict[str, Any]:
        return resolve_allow_list(ctx, fallback, "_agent_jobs")

    def _tasks(ctx: RunContext[Deps]) -> list[str]:
        return resolve_list(ctx, task_fallback, "_agent_tasks")

    @agent.tool(requires_approval=True)
    async def enqueue_task(
        ctx: RunContext[Deps],
        task: str,
        args: dict[str, Any] | None = None,
        delay: float = 0.0,
        queue: str | None = None,
    ) -> str:
        """Queue a registered task to run in the background (requires approval).

        Args:
            task: The registered task name (from the app allow-list).
            args: Keyword arguments passed to the task.
            delay: Seconds to wait before the job becomes available.
            queue: Optional queue name (default: the app's default queue).
        """
        app = app_of(ctx)
        if app is None:
            return "ERROR: no app bound"
        allowed = _tasks(ctx)
        if allowed and task not in allowed:
            return f"ERROR: task {task!r} is not allowed; choose from {', '.join(allowed)}"
        result = await app.dispatch(
            RunRegisteredTask(task, dict(args or {})), queue=queue
        )
        await emit_event("queue.enqueued", task=task)
        return f"queued {task!r} (id {result})" if isinstance(result, int) else f"ran {task!r}"

    @agent.tool(requires_approval=True)
    async def enqueue_job(
        ctx: RunContext[Deps],
        job: str,
        kwargs: dict[str, Any] | None = None,
        delay: float = 0.0,
        queue: str | None = None,
    ) -> str:
        """Queue an allow-listed Job class to run in the background (requires approval).

        Args:
            job: The allow-listed job name.
            kwargs: Constructor keyword arguments for the job.
            delay: Seconds to wait before the job becomes available.
            queue: Optional queue name (default: the app's default queue).
        """
        app = app_of(ctx)
        if app is None:
            return "ERROR: no app bound"
        registry = _jobs(ctx)
        job_class = registry.get(job)
        if job_class is None:
            known = ", ".join(sorted(registry)) or "(none)"
            return f"ERROR: unknown job {job!r}; available: {known}"
        instance = job_class(**dict(kwargs or {}))
        result = await app.dispatch(instance, queue=queue)
        await emit_event("queue.enqueued", job=job)
        return f"queued {job!r} (id {result})" if isinstance(result, int) else f"ran {job!r}"

    @agent.tool
    async def queue_status(ctx: RunContext[Deps], queue: str | None = None) -> str:
        """Show how many jobs are pending and failed.

        Args:
            queue: Optional queue name to restrict the pending count.
        """
        app = app_of(ctx)
        if app is None:
            return "ERROR: no app bound"
        pending = await app.queue.size(queue)
        failed = await app.queue.failed(limit=1000)
        return json.dumps({"pending": pending, "failed": len(failed)})

    @agent.tool
    async def list_failed_jobs(ctx: RunContext[Deps], limit: int = 20) -> str:
        """List failed jobs so they can be retried.

        Args:
            limit: Maximum jobs to list.
        """
        app = app_of(ctx)
        if app is None:
            return "ERROR: no app bound"
        rows = await app.queue.failed(limit=max(1, int(limit)))
        if not rows:
            return "(no failed jobs)"
        return json.dumps([_job_view(row) for row in rows], default=str)

    @agent.tool
    async def retry_job(ctx: RunContext[Deps], id: int) -> str:
        """Requeue a failed job by id.

        Args:
            id: The failed job id (from list_failed_jobs).
        """
        app = app_of(ctx)
        if app is None:
            return "ERROR: no app bound"
        return "requeued" if await app.queue.retry(id) else "(no such failed job)"

    agent._agentkit_queue_attached = True  # type: ignore[attr-defined]
    return agent
