"""SOUL.md persona read/write."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agentkit.soul import load_soul, soul_path
from agentkit.webui.context import WebUIContext, get_context

router = APIRouter(tags=["persona"])


class SoulBody(BaseModel):
    text: str


@router.get("/soul")
def get_soul(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    path = soul_path(ctx.settings)
    return {
        "path": str(path),
        "text": load_soul(ctx.settings),
        "exists": path.exists(),
    }


@router.put("/soul")
def put_soul(body: SoulBody, ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    path = soul_path(ctx.settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.text, encoding="utf-8")
    return {"path": str(path), "saved": True}
