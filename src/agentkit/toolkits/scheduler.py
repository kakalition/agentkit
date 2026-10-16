"""Native scheduler toolkit: schedule/cancel/run durable tasks on demand.

Tasks are restricted to the app's allow-list (``App.agent_tasks([...])`` or
``Agent.scheduler(tasks=[...])``), cron expressions are validated with
``croniter``, and the CRUD is owner-scoped through ``ctx.deps.repos.schedules``.
"""

from __future__ import annotations

import contextlib
import json
from datetime import datetime
from typing import Any

from croniter import croniter
from pydantic_ai import RunContext

from agentkit.deps import Deps
from agentkit.toolkits._common import actor_label, emit_event, repos_of, resolve_list

__all__ = ["attach_scheduler"]


def _job_view(job: Any) -> dict[str, Any]:
    return {
        "name": job.name,
        "kind": job.kind,
        "schedule": job.schedule,
        "task": job.task,
        "args": json.loads(job.args or "{}"),
        "enabled": job.enabled,
        "last_run": job.last_run.isoformat() if job.last_run else None,
        "run_count": job.run_count,
    }


def attach_scheduler(
    agent: Any, tasks: list[str] | None = None, *, flag: str = "scheduler_tools_enabled"
) -> Any:
    """Register the scheduler tools on a built PydanticAI agent (idempotent)."""
    if getattr(agent, "_agentkit_scheduler_attached", False):
        return agent
    fallback = list(tasks or [])

    def _allowed(ctx: RunContext[Deps]) -> list[str]:
        return resolve_list(ctx, fallback, "_agent_tasks")

    @agent.tool(requires_approval=True)
    async def schedule_task(
        ctx: RunContext[Deps],
        name: str,
        task: str,
        cron: str | None = None,
        at: str | None = None,
        args: dict[str, Any] | None = None,
        deliver_to: str | None = None,
    ) -> str:
        """Create or update a durable schedule (requires approval).

        Args:
            name: A unique name for the schedule.
            task: The registered task name to run (from the app allow-list).
            cron: A 5-field cron expression for a recurring schedule.
            at: An ISO-8601 datetime for a one-off schedule (instead of cron).
            args: Keyword arguments passed to the task.
            deliver_to: Conversation id to send the result to (default: this chat).
        """
        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        allowed = _allowed(ctx)
        if allowed and task not in allowed:
            return f"ERROR: task {task!r} is not allowed; choose from {', '.join(allowed)}"
        if bool(cron) == bool(at):
            return "ERROR: provide exactly one of cron or at"
        payload = dict(args or {})
        target = deliver_to or ctx.deps.conversation_id
        if target:
            payload["_deliver_to"] = target
        encoded = json.dumps(payload)
        if cron:
            try:
                croniter(cron)
            except (ValueError, KeyError) as exc:
                return f"ERROR: invalid cron {cron!r}: {exc}"
            await repos.schedules.upsert(
                name, kind="cron", schedule=cron, task=task, args=encoded
            )
        else:
            moment = datetime.fromisoformat(str(at))
            await repos.schedules.upsert(
                name, kind="once", schedule=moment.isoformat(), task=task, args=encoded
            )
        with contextlib.suppress(Exception):  # audit must not break a tool
            await repos.audit.append(
                "schedule.upsert",
                target=name,
                detail={"task": task},
                actor=actor_label(ctx) or repos.owner_id,
            )
        await emit_event("schedule.upsert", name=name, task=task)
        return f"scheduled {name!r} -> {task}"

    @agent.tool(requires_approval=True)
    async def schedule_natural(
        ctx: RunContext[Deps],
        when: str,
        task: str,
        name: str | None = None,
        deliver_to: str | None = None,
    ) -> str:
        """Schedule a task from a natural-language time (requires approval).

        Args:
            when: e.g. "every day at 9am", "every monday at 8:30", "in 2 hours".
            task: The registered task name to run.
            name: Optional schedule name (default: task + a short time hash).
            deliver_to: Conversation id to send the result to (default: this chat).
        """
        from agentkit.scheduling_nl import parse_when

        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        allowed = _allowed(ctx)
        if allowed and task not in allowed:
            return f"ERROR: task {task!r} is not allowed; choose from {', '.join(allowed)}"
        parsed = parse_when(when)
        if parsed is None:
            return f"ERROR: could not understand {when!r}; try 'every day at 9am' or 'in 2 hours'"
        resolved = name or f"{task}-{abs(hash(when)) % 100000}"
        target = deliver_to or ctx.deps.conversation_id
        payload = {"_deliver_to": target} if target else {}
        encoded = json.dumps(payload)
        if parsed.kind == "cron":
            await repos.schedules.upsert(
                resolved, kind="cron", schedule=parsed.schedule, task=task, args=encoded
            )
        else:
            await repos.schedules.upsert(
                resolved,
                kind="once",
                schedule=(parsed.at or datetime.now()).isoformat(),
                task=task,
                args=encoded,
            )
        await emit_event("schedule.upsert", name=resolved, task=task)
        return f"scheduled {resolved!r} -> {task} ({parsed.describe()})"

    @agent.tool
    async def list_schedules(ctx: RunContext[Deps]) -> str:
        """List the durable schedules owned by this agent."""
        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        rows = await repos.schedules.list()
        if not rows:
            return "(no schedules)"
        return json.dumps([_job_view(job) for job in rows], default=str)

    @agent.tool
    async def get_schedule(ctx: RunContext[Deps], name: str) -> str:
        """Show one schedule by name.

        Args:
            name: The schedule name.
        """
        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        job = await repos.schedules.get(name)
        return json.dumps(_job_view(job), default=str) if job is not None else "(not found)"

    @agent.tool
    async def cancel_schedule(ctx: RunContext[Deps], name: str, delete: bool = False) -> str:
        """Disable (or delete) a schedule.

        Args:
            name: The schedule name.
            delete: When true remove the schedule; otherwise disable it.
        """
        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        if delete:
            ok = await repos.schedules.remove(name)
            action = "removed"
        else:
            ok = await repos.schedules.set_enabled(name, False)
            action = "disabled"
        return f"{action} {name!r}" if ok else "(not found)"

    @agent.tool(requires_approval=True)
    async def run_schedule_now(ctx: RunContext[Deps], name: str) -> str:
        """Run a scheduled task immediately (requires approval).

        Args:
            name: The schedule name to run now.
        """
        from agentkit.scheduler import invoke_task

        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        job = await repos.schedules.get(name)
        if job is None:
            return "(not found)"
        allowed = _allowed(ctx)
        if allowed and job.task not in allowed:
            return f"ERROR: task {job.task!r} is not allowed"
        payload = json.loads(job.args or "{}")
        if not isinstance(payload, dict):
            payload = {}
        target = ctx.deps.conversation_id
        if target:
            payload["_deliver_to"] = target
        await invoke_task(job.task, json.dumps(payload))
        await repos.schedules.record_run(name)
        await emit_event("schedule.run", name=name, task=job.task)
        return f"ran {name!r} ({job.task})"

    agent._agentkit_scheduler_attached = True  # type: ignore[attr-defined]
    return agent
