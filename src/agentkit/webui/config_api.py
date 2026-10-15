"""Non-secret settings view with masked credentials."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends

from agentkit.soul import soul_path
from agentkit.webui.context import WebUIContext, get_context

router = APIRouter(tags=["config"])

SECRET_FIELDS = (
    "openai_api_key",
    "anthropic_api_key",
    "google_api_key",
    "groq_api_key",
    "mistral_api_key",
    "libsql_auth_token",
    "telegram_bot_token",
    "slack_bot_token",
    "slack_app_token",
    "discord_bot_token",
    "email_imap_password",
    "libsql_url",
)
_MASK = "***"


def mask_secret(value: Any) -> Any:
    return _MASK if value else value


def mask_url(url: str | None) -> str | None:
    """Strip credentials (user:pass@) from a URL."""
    if not url:
        return url
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return url
    host = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))


def config_view(settings: Any) -> dict[str, Any]:
    data = settings.model_dump(mode="json")
    for field in SECRET_FIELDS:
        if data.get(field):
            data[field] = _MASK
    if data.get("database_url"):
        data["database_url"] = mask_url(data["database_url"])
    data["resolved_database_url"] = mask_url(settings.resolved_database_url)
    data["db_path"] = str(settings.db_path)
    data["artifacts_dir"] = str(settings.artifacts_dir)
    data["logs_dir"] = str(settings.logs_dir)
    data["soul_path"] = str(soul_path(settings))
    return data


@router.get("/config")
def get_config(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    return {"config": config_view(ctx.settings)}


@router.get("/info")
def get_info(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    from agentkit import __version__
    from agentkit.foundation.facade import get_current_app
    from agentkit.webui.introspect import stack_view

    settings = ctx.settings
    return {
        "name": settings.agent_name,
        "version": __version__,
        "owner_id": settings.owner_id,
        "workspace_root": str(settings.workspace_root),
        "home": str(settings.home),
        "db_path": str(settings.db_path),
        "database_url": mask_url(settings.resolved_database_url),
        "model_name": settings.model_name,
        "stack": stack_view(settings, app=get_current_app()),
        "webui": {
            "enabled": settings.webui_enabled,
            "host": settings.webui_host,
            "port": settings.webui_port,
            "url": f"http://{settings.webui_host}:{settings.webui_port}",
        },
        "chat_enabled": ctx.answer is not None,
        "channels": {
            "telegram": bool(settings.telegram_bot_token),
            "a2a": {"host": settings.a2a_host, "port": settings.a2a_port},
            "mcp": {"host": settings.mcp_host, "port": settings.mcp_port},
        },
    }
