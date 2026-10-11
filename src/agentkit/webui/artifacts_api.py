"""List and download files under the agent's artifacts directory."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from agentkit.webui.context import WebUIContext, get_context

router = APIRouter(tags=["artifacts"])


def _artifact_view(base: Path, path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": path.relative_to(base).as_posix(),
        "name": path.name,
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
    }


def _safe_target(base: Path, relative: str) -> Path:
    root = base.resolve()
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise HTTPException(status_code=400, detail="path escapes the artifacts directory")
    return target


@router.get("/artifacts")
def list_artifacts(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    base = ctx.settings.artifacts_dir
    if not base.is_dir():
        return {"artifacts": [], "root": str(base)}
    files = [p for p in sorted(base.rglob("*")) if p.is_file()]
    return {"artifacts": [_artifact_view(base, p) for p in files], "root": str(base)}


@router.get("/artifacts/{path:path}")
def download_artifact(path: str, ctx: WebUIContext = Depends(get_context)) -> FileResponse:
    target = _safe_target(ctx.settings.artifacts_dir, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(target, filename=target.name)
