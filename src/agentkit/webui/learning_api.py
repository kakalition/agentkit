"""Learning review inbox: inspect and approve/reject proposed lessons."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from agentkit.learning import LESSON_KIND, approve_lesson, reject_lesson
from agentkit.runtime import repositories
from agentkit.webui.context import WebUIContext, get_context

router = APIRouter(tags=["learning"])


def _lesson_view(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "content": row.content,
        "status": row.status,
        "kind": row.kind,
        "importance": row.importance,
        "source_conversation_id": row.source_conversation_id,
        "created_at": getattr(row, "created_at", None),
    }


@router.get("/lessons")
async def list_lessons(
    status: str = Query("proposed"),
    limit: int = Query(100, ge=1, le=500),
    ctx: WebUIContext = Depends(get_context),
) -> dict[str, Any]:
    wanted = None if status == "all" else status
    async with repositories(ctx.runtime) as repos:
        rows = await repos.memories.list(limit=limit, kind=LESSON_KIND, status=wanted)
    rows.sort(key=lambda row: (row.id or 0))
    return {"lessons": [_lesson_view(row) for row in rows]}


@router.post("/lessons/{lesson_id}/approve")
async def approve(
    lesson_id: int, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    async with repositories(ctx.runtime) as repos:
        ok = await approve_lesson(repos, lesson_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"no lesson #{lesson_id}")
    return {"id": lesson_id, "status": "active"}


@router.post("/lessons/{lesson_id}/reject")
async def reject(lesson_id: int, ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    async with repositories(ctx.runtime) as repos:
        ok = await reject_lesson(repos, lesson_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"no lesson #{lesson_id}")
    return {"id": lesson_id, "status": "rejected"}
