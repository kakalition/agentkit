"""Read-only introspection endpoints: conversations, usage, audit, A2A tasks."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from agentkit.session import deserialize_messages
from agentkit.webui.context import WebUIContext, get_context

router = APIRouter(tags=["introspect"])


def _part_view(part: Any) -> dict[str, Any]:
    view: dict[str, Any] = {"kind": getattr(part, "part_kind", type(part).__name__)}
    tool_name = getattr(part, "tool_name", None)
    if tool_name:
        view["tool_name"] = tool_name
    content = getattr(part, "content", None)
    if content is not None:
        view["text"] = content if isinstance(content, str) else str(content)
    args = getattr(part, "args", None)
    if args is not None:
        view["args"] = args if isinstance(args, (dict, list)) else str(args)
    return view


def message_view(message: Any) -> dict[str, Any]:
    """Map a stored ``ModelMessage`` to a plain, tolerant dict."""
    kind = getattr(message, "kind", type(message).__name__)
    if kind == "response":
        role = "assistant"
    elif kind == "request":
        role = "user"
    else:
        role = kind
    return {"role": role, "kind": kind, "parts": [_part_view(p) for p in message.parts]}


def messages_view(payloads: list[str]) -> list[dict[str, Any]]:
    """Decode stored message payloads (via agentkit's codec) into view dicts."""
    try:
        messages = deserialize_messages(payloads)
    except Exception:  # pragma: no cover - tolerate corrupt rows
        return []
    return [message_view(message) for message in messages]


def _conversation_view(conversation: Any, count: int | None = None) -> dict[str, Any]:
    return {
        "id": conversation.id,
        "channel": conversation.channel,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
        "message_count": count,
    }


def _audit_view(entry: Any) -> dict[str, Any]:
    try:
        detail = json.loads(entry.detail or "{}")
    except ValueError:
        detail = {}
    return {
        "id": entry.id,
        "seq": entry.seq,
        "action": entry.action,
        "target": entry.target,
        "detail": detail,
        "actor": entry.actor,
        "created_at": entry.created_at.isoformat(),
    }


def _a2a_view(record: Any, *, include_payload: bool = False) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": record.id,
        "context_id": record.context_id,
        "state": record.state,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }
    if include_payload:
        try:
            view["payload"] = json.loads(record.payload or "{}")
        except ValueError:
            view["payload"] = record.payload
    return view


@router.get("/conversations")
def list_conversations(
    limit: int = Query(50, ge=1, le=500), ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    from agentkit.runtime import repositories

    with repositories(ctx.runtime) as repos:
        rows = repos.conversations.list(limit=limit)
        return {
            "conversations": [
                _conversation_view(c, len(repos.messages.list(c.id))) for c in rows
            ]
        }


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    from agentkit.runtime import repositories

    with repositories(ctx.runtime) as repos:
        conversation = repos.conversations.get(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        return _conversation_view(conversation, len(repos.messages.list(conversation_id)))


@router.get("/conversations/{conversation_id}/messages")
def get_messages(
    conversation_id: str, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    from agentkit.runtime import repositories

    with repositories(ctx.runtime) as repos:
        payloads = [m.payload for m in repos.messages.list(conversation_id)]
    return {"conversation_id": conversation_id, "messages": messages_view(payloads)}


@router.delete("/conversations/{conversation_id}/messages")
def clear_messages(
    conversation_id: str, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    from agentkit.runtime import repositories

    with repositories(ctx.runtime) as repos:
        repos.messages.clear(conversation_id)
    return {"conversation_id": conversation_id, "cleared": True}


@router.get("/usage")
def get_usage(
    limit: int = Query(100, ge=1, le=1000), ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    from agentkit.runtime import repositories

    with repositories(ctx.runtime) as repos:
        totals = repos.usage.totals()
        recent = [
            {
                "id": row.id,
                "conversation_id": row.conversation_id,
                "kind": row.kind,
                "model": row.model,
                "requests": row.requests,
                "input_tokens": row.input_tokens,
                "output_tokens": row.output_tokens,
                "total_tokens": row.total_tokens,
                "created_at": row.created_at.isoformat(),
            }
            for row in repos.usage.list(limit=limit)
        ]
    return {"totals": totals, "recent": recent}


@router.get("/audit")
def get_audit(
    limit: int = Query(200, ge=1, le=1000), ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    from agentkit.runtime import repositories

    with repositories(ctx.runtime) as repos:
        entries = repos.audit.entries(limit=limit)
    return {"entries": [_audit_view(e) for e in entries]}


@router.get("/audit/verify")
def verify_audit(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    from agentkit.runtime import repositories

    with repositories(ctx.runtime) as repos:
        return {"ok": repos.audit.verify()}


@router.get("/a2a")
def list_a2a(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    from agentkit.runtime import repositories

    with repositories(ctx.runtime) as repos:
        return {"tasks": [_a2a_view(r) for r in repos.a2a.list()]}


@router.get("/a2a/{task_id}")
def get_a2a(task_id: str, ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    from agentkit.runtime import repositories

    with repositories(ctx.runtime) as repos:
        record = repos.a2a.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="task not found")
        return _a2a_view(record, include_payload=True)
