"""Scheduler CRUD endpoints (delegating to :mod:`agentkit.scheduler`)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentkit import scheduler
from agentkit.webui.context import WebUIContext, get_context

router = APIRouter(tags=["scheduler"])


class ScheduleCreate(BaseModel):
    name: str
    kind: Literal["cron", "once"] = "cron"
    task: str
    schedule: str | None = None
    at: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class SchedulePatch(BaseModel):
    enabled: bool | None = None
    schedule: str | None = None
    at: str | None = None
    args: dict[str, Any] | None = None


def _known_tasks() -> list[str]:
    return sorted(scheduler.TASKS)


def _require_task(task: str) -> None:
    if scheduler.TASKS and task not in scheduler.TASKS:
        raise HTTPException(
            status_code=400,
            detail={"message": f"unknown task {task!r}", "tasks": _known_tasks()},
        )


@router.get("/schedules")
async def list_schedules(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    return {"jobs": await scheduler.list_jobs(), "tasks": _known_tasks()}


@router.post("/schedules", status_code=201)
async def create_schedule(
    body: ScheduleCreate, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    _require_task(body.task)
    try:
        if body.kind == "cron":
            if not body.schedule:
                raise HTTPException(status_code=400, detail="a cron expression is required")
            await scheduler.schedule_cron(
                body.name, body.schedule, body.task, args=body.args, enabled=body.enabled
            )
        else:
            when = body.at or body.schedule
            if not when:
                raise HTTPException(status_code=400, detail="a datetime is required")
            datetime.fromisoformat(when)
            await scheduler.schedule_once(body.name, when, body.task, args=body.args)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"name": body.name, "created": True}


@router.patch("/schedules/{name}")
async def patch_schedule(
    name: str, body: SchedulePatch, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    existing = {job["name"]: job for job in await scheduler.list_jobs()}.get(name)
    if existing is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    if body.schedule or body.at:
        _require_task(existing["task"])
        try:
            if body.schedule:
                await scheduler.schedule_cron(
                    name, body.schedule, existing["task"], args=body.args or existing["args"]
                )
            else:
                datetime.fromisoformat(str(body.at))
                await scheduler.schedule_once(
                    name, str(body.at), existing["task"], args=body.args or existing["args"]
                )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.enabled is not None:
        await scheduler.set_enabled(name, body.enabled)
    return {"name": name, "updated": True}


@router.delete("/schedules/{name}")
async def delete_schedule(name: str, ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    if not await scheduler.remove_job(name):
        raise HTTPException(status_code=404, detail="schedule not found")
    return {"name": name, "removed": True}
