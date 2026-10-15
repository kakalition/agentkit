"""Owner data lifecycle endpoints: export (safe) and forget (opt-in, explicit)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from agentkit.data import export_owner, forget_owner
from agentkit.runtime import repositories
from agentkit.webui.context import WebUIContext, get_actor, get_context

router = APIRouter(tags=["data"])


@router.get("/data/export")
async def export_data(
    request: Request, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    if not getattr(ctx.settings, "data_export_enabled", True):
        raise HTTPException(status_code=403, detail="data export is disabled")
    actor = get_actor(request)
    async with repositories(ctx.runtime, actor.owner_id) as repos:
        return await export_owner(repos)


@router.post("/data/forget")
async def forget_data(
    request: Request,
    confirm: bool = False,
    ctx: WebUIContext = Depends(get_context),
) -> dict[str, Any]:
    """Erase the owner's data. Dry-run unless ``?confirm=true``; opt-in only."""
    if not getattr(ctx.settings, "data_forget_enabled", False):
        raise HTTPException(status_code=403, detail="data forget is disabled (set DATA_FORGET_ENABLED)")
    actor = get_actor(request)
    async with repositories(ctx.runtime, actor.owner_id) as repos:
        return await forget_owner(repos, dry_run=not confirm)
