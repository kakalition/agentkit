"""Global helpers — the Laravel-style convenience functions.

These resolve against the *current* app, so they read like Laravel::

    from agentkit import app, config, dispatch, event, cache, storage

    config("app.greeting", "Hello")
    storage().put("notes.txt", "hi")          # or storage("local")
    await dispatch(SyncNotes())
    event("note.saved", note_id=1)

They are thin wrappers over the app container; prefer explicit dependencies inside
tools and services (``ctx.deps`` / ``self.app``).
"""

from __future__ import annotations

import os
from typing import Any

from agentkit.foundation.facade import current_app
from agentkit.logging import get_logger

__all__ = [
    "app",
    "authorize",
    "cache",
    "can",
    "config",
    "dispatch",
    "env",
    "event",
    "logger",
    "notify",
    "policy",
    "queue",
    "report",
    "resolve",
    "storage",
    "tool_policy",
]


def app(name: Any = None) -> Any:
    """The current ``App``, or a binding resolved from it."""
    current = current_app()
    return current if name is None else current.make(name)


def resolve(name: Any) -> Any:
    """Resolve a binding from the current app's container."""
    return current_app().make(name)


def env(key: str, default: Any = None) -> Any:
    """Read an environment variable (falls back to ``default``)."""
    return os.environ.get(key, default)


def config(key: str, default: Any = None) -> Any:
    """Read configuration with dotted access: ``config("app.greeting")``.

    Looks in the app's registered config sections first, then the settings object.
    """
    current = current_app()
    section, _, field = key.partition(".")
    if section in current._config_schemas:  # noqa: SLF001 - framework helper
        resolved = current.config(section)
        if not field:
            return resolved
        return getattr(resolved, field, default)
    value: Any = current.settings
    for part in key.split("."):
        value = getattr(value, part, None)
        if value is None:
            return default
    return value


def cache() -> Any:
    """The current app's cache store."""
    return current_app().cache


def storage(disk: str | None = None) -> Any:
    """The current app's storage (or a named disk)."""
    store = current_app().storage
    return store.disk(disk) if disk else store


def queue() -> Any:
    """The current app's job queue."""
    return current_app().queue


def notify(notification: Any, **kwargs: Any) -> Any:
    """Send a notification through the current app."""
    return current_app().notify(notification, **kwargs)


def event(name: str, **payload: Any) -> list[Any]:
    """Dispatch an event on the current app."""
    return current_app().events.dispatch(name, **payload)


async def dispatch(job: Any, **kwargs: Any) -> Any:
    """Dispatch a job on the current app (``await dispatch(job)``)."""
    return await current_app().dispatch(job, **kwargs)


def logger(name: str = "agentkit") -> Any:
    """A structured logger."""
    return get_logger(name)


def report(exception: BaseException) -> None:
    """Report an exception to the log (Laravel's ``report``)."""
    get_logger("agentkit").exception("unhandled: %s", exception)


def can(ability: str, *arguments: Any, actor: Any = None) -> bool:
    """Whether the current actor may perform ``ability`` (``Gate.allows``)."""
    return bool(current_app().gate.allows(ability, *arguments, actor=actor))


def authorize(ability: str, *arguments: Any, actor: Any = None) -> bool:
    """Authorize ``ability`` or raise ``PermissionDenied`` (``Gate.authorize``)."""
    return bool(current_app().gate.authorize(ability, *arguments, actor=actor))


def policy(spec: Any, policy_class: Any = None) -> Any:
    """Register a ``Policy`` class (by its ``model`` or class name) on the Gate."""
    gate = current_app().gate
    return gate.policy(spec, policy_class)


def tool_policy(policy: Any) -> Any:
    """Install a tool-RBAC policy on the current app's Gate."""
    return current_app().gate.tool_policy(policy)
