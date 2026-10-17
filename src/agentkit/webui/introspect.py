"""Read-only introspection endpoints: conversations, usage, audit, A2A tasks."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from agentkit.session import deserialize_messages
from agentkit.webui.context import WebUIContext, get_context

router = APIRouter(tags=["introspect"])


def _drivers_view(app: Any) -> dict[str, Any]:
    """Active driver per subsystem kind (empty when no app is bound)."""
    if app is None:
        return {}
    drivers = getattr(app, "drivers", None)
    if not callable(drivers):
        return {}
    try:
        return drivers()
    except Exception:  # pragma: no cover - never break introspection
        return {}


def _extensions_view(app: Any) -> list[dict[str, Any]]:
    """Registered extensions (empty on failure)."""
    try:
        from agentkit.extensions import EXTENSIONS

        return EXTENSIONS.describe()
    except Exception:  # pragma: no cover - never break introspection
        return []


def _specs_view(app: Any) -> dict[str, list[str]]:
    """Registered spec kinds (empty on failure)."""
    try:
        from agentkit.specs import SPECS

        return {kind: [] for kind in SPECS.kinds()}
    except Exception:  # pragma: no cover - never break introspection
        return {}


def _panels_view() -> list[dict[str, Any]]:
    """Registered Studio panels (empty on failure)."""
    try:
        from agentkit.extensions.panels import PANELS

        return [panel.to_dict() for panel in PANELS.list()]
    except Exception:  # pragma: no cover - never break introspection
        return []


def _posture_view(settings: Any, app: Any = None) -> dict[str, Any]:
    """The active posture and the layers its profile derives."""
    from agentkit.posture import resolve_posture

    name = getattr(app, "_posture", None) or getattr(settings, "agent_posture", "hybrid")
    try:
        profile = resolve_posture(name)
    except ValueError:  # pragma: no cover - defensive
        profile = None
    return {
        "name": str(name),
        "layers": dict(profile.layers) if profile is not None else {},
        "preamble": bool(profile.preamble) if profile is not None else False,
    }


def stack_view(settings: Any, app: Any = None) -> dict[str, Any]:
    """A read-only summary of the enabled capability stack (".full()" observability)."""
    from agentkit.model_providers import supported_prefixes
    from agentkit.teams import TEAMS
    from agentkit.toolkits import TOOLKITS, enabled_toolkits

    return {
        "posture": _posture_view(settings, app),
        "teams": sorted(TEAMS),
        "model_name": settings.model_name,
        "model_providers": supported_prefixes(),
        "drivers": _drivers_view(app),
        "extensions": _extensions_view(app),
        "specs": _specs_view(app),
        "panels": _panels_view(),
        "runs": {"enabled": bool(getattr(settings, "run_trace_enabled", True))},
        "checkpoints": {
            "enabled": bool(getattr(settings, "checkpoints_enabled", False)),
            "retention": int(getattr(settings, "checkpoint_retention", 50) or 50),
        },
        "memory": {
            "enabled": settings.memory_enabled,
            "embedding_backend": settings.memory_embedding_backend,
        },
        "vector_store": {
            "driver": str(getattr(settings, "vector_store_driver", "repository")),
        },
        "working_memory": {
            "enabled": bool(getattr(settings, "working_memory_enabled", False)),
            "driver": str(getattr(settings, "working_memory_driver", "memory")),
        },
        "datasets": {
            "driver": str(getattr(settings, "dataset_driver", "repository")),
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
            "require_review": getattr(settings, "learning_require_review", True),
            "eval_gate": getattr(settings, "learning_eval_gate", False),
        },
        "auth": {
            "enabled": bool(getattr(settings, "auth_enabled", False)),
            "jwks": bool(getattr(settings, "auth_jwks_url", None)),
            "required_roles": list(getattr(settings, "auth_required_roles", []) or []),
        },
        "credentials": {"enabled": bool(getattr(settings, "credentials_enabled", False))},
        "rate_limit": {
            "enabled": bool(getattr(settings, "rate_limit_enabled", False)),
            "per_minute": getattr(settings, "rate_limit_per_minute", 60),
            "tool_per_minute": getattr(settings, "rate_limit_tool_per_minute", 0),
        },
        "interfaces": {
            "openai_api": bool(getattr(settings, "openai_api_enabled", False)),
            "webhooks": bool(getattr(settings, "webhooks_enabled", False)),
        },
        "guardrails": {
            "enabled": bool(getattr(settings, "guardrails_enabled", False)),
            "wrap_untrusted": bool(getattr(settings, "guardrails_wrap_untrusted", False)),
        },
        "resilience": {
            "model_fallbacks": list(getattr(settings, "model_fallbacks", []) or []),
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


@router.get("/search")
async def search_history(
    q: str = Query(..., min_length=1, description="The text to search for."),
    limit: int = Query(20, ge=1, le=100),
    ctx: WebUIContext = Depends(get_context),
) -> dict[str, Any]:
    """Indexed cross-session search over past messages (``search_driver``)."""
    from agentkit.runtime import repositories
    from agentkit.search import ScanSearchIndex

    index = getattr(ctx.app, "search", None) or ScanSearchIndex()
    async with repositories(ctx.runtime) as repos:
        hits = await index.search(repos, q, limit=limit)
    return {
        "query": q,
        "hits": [{"conversation_id": h.conversation_id, "text": h.text} for h in hits],
    }


@router.get("/teams")
async def list_teams(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    """Registered multi-agent teams (name, runner kind, and roster)."""
    from agentkit.teams import TEAMS

    teams = [
        {"name": spec.name, "kind": spec.kind, "roster": sorted(spec.roster)}
        for spec in sorted(TEAMS.values(), key=lambda spec: spec.name)
    ]
    return {"teams": teams}


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
                "cache_read_tokens": row.cache_read_tokens,
                "context_tokens": row.context_tokens,
                "context_window": row.context_window,
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
