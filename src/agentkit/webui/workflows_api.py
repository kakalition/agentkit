"""Durable workflow inspection/management (read via a standalone DBOS client)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from agentkit import durability
from agentkit.webui.context import WebUIContext, get_context

router = APIRouter(tags=["workflows"])

_FAILED = ["ERROR", "MAX_RECOVERY_ATTEMPTS_EXCEEDED"]


def _wf_view(workflow: Any, *, full: bool = False) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": getattr(workflow, "workflow_id", None),
        "name": getattr(workflow, "name", None),
        "status": getattr(workflow, "status", None),
        "queue": getattr(workflow, "queue_name", None),
        "created_at": getattr(workflow, "created_at", None),
        "updated_at": getattr(workflow, "updated_at", None),
        "completed_at": getattr(workflow, "completed_at", None),
        "error": _stringify_error(getattr(workflow, "error", None)),
    }
    if full:
        view["input"] = _jsonable(getattr(workflow, "input", None))
        view["output"] = _jsonable(getattr(workflow, "output", None))
    return view


def _stringify_error(error: Any) -> str | None:
    if error is None:
        return None
    return str(error)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool, list, dict)):
        return value
    return str(value)


def _client(ctx: WebUIContext):
    try:
        return durability.client(ctx.settings)
    except Exception as exc:  # pragma: no cover - DBOS system db unavailable
        raise HTTPException(status_code=503, detail=f"workflow store unavailable: {exc}") from exc


@router.get("/workflows")
def list_workflows(
    status: str | None = Query(None, description="Filter by status, e.g. ERROR."),
    queue: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    ctx: WebUIContext = Depends(get_context),
) -> dict[str, Any]:
    client = _client(ctx)
    try:
        rows = client.list_workflows(
            status=status or None, queue_name=queue or None, limit=limit, sort_desc=True
        )
    except Exception as exc:  # pragma: no cover - missing tables on first run
        return {"workflows": [], "error": str(exc)}
    return {"workflows": [_wf_view(w) for w in rows]}


@router.get("/workflows/failed")
def list_failed(
    limit: int = Query(50, ge=1, le=500), ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    client = _client(ctx)
    try:
        rows = client.list_workflows(status=_FAILED, limit=limit, sort_desc=True)
    except Exception as exc:  # pragma: no cover
        return {"workflows": [], "error": str(exc)}
    return {"workflows": [_wf_view(w) for w in rows]}


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str, ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    client = _client(ctx)
    try:
        workflow = client.retrieve_workflow(workflow_id).get_status()
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"workflow not found: {exc}") from exc
    return _wf_view(workflow, full=True)


@router.post("/workflows/{workflow_id}/cancel")
def cancel_workflow(workflow_id: str, ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    client = _client(ctx)
    try:
        client.cancel_workflow(workflow_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": workflow_id, "cancelled": True}


@router.post("/workflows/{workflow_id}/resume")
def resume_workflow(workflow_id: str, ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    client = _client(ctx)
    try:
        client.resume_workflow(workflow_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": workflow_id, "resumed": True}
