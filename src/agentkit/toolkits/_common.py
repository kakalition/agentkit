"""Shared helpers for the native toolkits.

Tools read the *live* run context so they always see the current session, owner,
and app-level allow-lists (``ctx.deps.repos``, ``ctx.deps.settings``, and
``ctx.deps.extras["app"]``).
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "app_of",
    "emit_event",
    "repos_of",
    "resolve_allow_list",
    "resolve_list",
    "settings_of",
]


def app_of(ctx: Any) -> Any | None:
    """The current app, seeded into ``deps.extras`` by :meth:`App.deps`."""
    deps = getattr(ctx, "deps", None)
    extras = getattr(deps, "extras", None) or {}
    return extras.get("app")


def repos_of(ctx: Any) -> Any:
    return getattr(getattr(ctx, "deps", None), "repos", None)


def settings_of(ctx: Any) -> Any:
    return getattr(getattr(ctx, "deps", None), "settings", None)


def resolve_allow_list(ctx: Any, fallback: Any, attr: str) -> dict[str, Any]:
    """Merge a builder-provided mapping with the app-level allow-list."""
    merged: dict[str, Any] = dict(fallback or {})
    app = app_of(ctx)
    if app is not None:
        extra = getattr(app, attr, None)
        if extra:
            merged.update(extra)
    return merged


def resolve_list(ctx: Any, fallback: Any, attr: str) -> list[str]:
    """The app-level list allow-list, else the builder-provided one."""
    app = app_of(ctx)
    if app is not None:
        extra = getattr(app, attr, None)
        if extra:
            return list(extra)
    return list(fallback or [])


async def emit_event(event: str, **payload: Any) -> None:
    """Emit a lifecycle event; observer failures never break the tool."""
    from agentkit.foundation.facade import emit

    await emit(event, **payload)
