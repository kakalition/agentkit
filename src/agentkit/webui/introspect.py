"""Read-only introspection endpoints: conversations, usage, audit, A2A tasks."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from agentkit.session import deserialize_messages
from agentkit.webui.context import WebUIContext, get_context

router = APIRouter(tags=["introspect"])


def stack_view(settings: Any, app: Any = None) -> dict[str, Any]:
    """A read-only summary of the enabled capability stack (".full()" observability)."""
    from agentkit.model_providers import supported_prefixes
    from agentkit.toolkits import TOOLKITS, enabled_toolkits

    return {
        "model_name": settings.model_name,
        "model_providers": supported_prefixes(),
        "memory": {
            "enabled": settings.memory_enabled,
            "embedding_backend": settings.memory_embedding_backend,
        },
        "skills": {"enabled": settings.skills_enabled, "dir": settings.skills_dir},
        "approvals": settings.approvals_enabled,
        "subagents": {
            "enabled": settings.subagents_enabled,
            "durable_mailbox": settings.mailbox_durable,
            "max_handoffs": settings.max_handoffs,
        },
        "channels": {
            "telegram": bool(settings.telegram_bot_token),
            "slack": bool(settings.slack_bot_token and settings.slack_app_token),
            "email": bool(settings.email_imap_host and settings.email_smtp_host),
            "discord": bool(settings.discord_bot_token),
        },
        "interop": {
            "a2a": {"host": settings.a2a_host, "port": settings.a2a_port},
            "peers_file": settings.peers_file,
            "mcp": {"host": settings.mcp_host, "port": settings.mcp_port},
        },
        "queue": {"enabled": settings.queue_enabled, "default": settings.queue_default},
        "native_tools": {
            "enabled": sorted(enabled_toolkits(settings)),
            "flags": {name: bool(getattr(settings, flag, True)) for name, flag in TOOLKITS.items()},
            "models": sorted(getattr(app, "_agent_models", {}) or {}),
            "tasks": list(getattr(app, "_agent_tasks", []) or []),
            "jobs": sorted(getattr(app, "_agent_jobs", {}) or {}),
        },
        "learning": {
            "enabled": getattr(settings, "learning_enabled", True),
            "reflect_cron": getattr(settings, "learning_reflect_cron", "0 4 * * *"),
            "skill_threshold": getattr(settings, "learning_skill_threshold", 3),
            "auto_skills": getattr(settings, "learning_auto_skills", False),
            "max_lessons": getattr(settings, "learning_max_lessons", 50),
        },
    }


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
async def list_conversations(
    limit: int = Query(50, ge=1, le=500), ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    from agentkit.runtime import repositories

    async with repositories(ctx.runtime) as repos:
        rows = await repos.conversations.list(limit=limit)
        conversations = [
            _conversation_view(c, len(await repos.messages.list(c.id))) for c in rows
        ]
        return {"conversations": conversations}


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    from agentkit.runtime import repositories

    async with repositories(ctx.runtime) as repos:
        conversation = await repos.conversations.get(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        count = len(await repos.messages.list(conversation_id))
        return _conversation_view(conversation, count)


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    from agentkit.runtime import repositories

    async with repositories(ctx.runtime) as repos:
        payloads = [m.payload for m in await repos.messages.list(conversation_id)]
    return {"conversation_id": conversation_id, "messages": messages_view(payloads)}


@router.delete("/conversations/{conversation_id}/messages")
async def clear_messages(
    conversation_id: str, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    from agentkit.runtime import repositories

    async with repositories(ctx.runtime) as repos:
        await repos.messages.clear(conversation_id)
    return {"conversation_id": conversation_id, "cleared": True}


@router.get("/usage")
async def get_usage(
    limit: int = Query(100, ge=1, le=1000), ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    from agentkit.runtime import repositories

    async with repositories(ctx.runtime) as repos:
        totals = await repos.usage.totals()
        rows = await repos.usage.list(limit=limit)
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
            for row in rows
        ]
    return {"totals": totals, "recent": recent}


@router.get("/audit")
async def get_audit(
    limit: int = Query(200, ge=1, le=1000), ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    from agentkit.runtime import repositories

    async with repositories(ctx.runtime) as repos:
        entries = await repos.audit.entries(limit=limit)
    return {"entries": [_audit_view(e) for e in entries]}


@router.get("/audit/verify")
async def verify_audit(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    from agentkit.runtime import repositories

    async with repositories(ctx.runtime) as repos:
        return {"ok": await repos.audit.verify()}


@router.get("/a2a")
async def list_a2a(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    from agentkit.runtime import repositories

    async with repositories(ctx.runtime) as repos:
        return {"tasks": [_a2a_view(r) for r in await repos.a2a.list()]}


@router.get("/a2a/{task_id}")
async def get_a2a(task_id: str, ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    from agentkit.runtime import repositories

    async with repositories(ctx.runtime) as repos:
        record = await repos.a2a.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="task not found")
        return _a2a_view(record, include_payload=True)
