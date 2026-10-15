"""Native toolkits: every agentkit capability as first-class, agent-callable tools.

Each module exposes an ``attach_<name>(agent, ...)`` that registers its tools on a
*built* PydanticAI agent (idempotent). :func:`attach_toolkits` attaches the
settings-enabled set — used by ``Agent.full()``/``Agent.native()``. Reachable
models/tasks/jobs stay deny-by-default (empty allow-lists) and writes require
approval, so enabling a toolkit is safe.
"""

from __future__ import annotations

from typing import Any

from agentkit.toolkits.database import attach_database
from agentkit.toolkits.history import attach_history
from agentkit.toolkits.knowledge_admin import attach_knowledge_admin
from agentkit.toolkits.notifications import attach_notifications
from agentkit.toolkits.queue import RunRegisteredTask, attach_queue
from agentkit.toolkits.scheduler import attach_scheduler
from agentkit.toolkits.skills_admin import attach_skill_authoring
from agentkit.toolkits.usage import attach_usage

__all__ = [
    "TOOLKITS",
    "RunRegisteredTask",
    "attach_database",
    "attach_history",
    "attach_knowledge_admin",
    "attach_notifications",
    "attach_queue",
    "attach_scheduler",
    "attach_skill_authoring",
    "attach_toolkit",
    "attach_toolkits",
    "attach_usage",
    "enabled_toolkits",
]

# Toolkit name -> the settings flag that enables it.
TOOLKITS: dict[str, str] = {
    "database": "db_tools_enabled",
    "scheduler": "scheduler_tools_enabled",
    "queue": "queue_tools_enabled",
    "notifications": "notification_tools_enabled",
    "history": "history_tools_enabled",
    "usage": "usage_tools_enabled",
    "knowledge_admin": "knowledge_admin_enabled",
    "skills_admin": "skill_authoring_enabled",
}


def enabled_toolkits(settings: Any = None) -> set[str]:
    """The toolkits whose settings flag is on (all, when there are no settings)."""
    if settings is None:
        return set(TOOLKITS)
    return {
        name
        for name, flag in TOOLKITS.items()
        if bool(getattr(settings, flag, True))
    }


def attach_toolkit(agent: Any, name: str, **options: Any) -> Any:
    """Attach one toolkit by name onto a built agent."""
    attach: Any = {
        "database": attach_database,
        "scheduler": attach_scheduler,
        "queue": attach_queue,
        "notifications": attach_notifications,
        "history": attach_history,
        "usage": attach_usage,
        "knowledge_admin": attach_knowledge_admin,
        "skills_admin": attach_skill_authoring,
    }.get(name)
    if attach is None:
        raise KeyError(f"unknown toolkit {name!r}")
    return attach(agent, **options)


def attach_toolkits(
    agent: Any,
    *,
    enabled: set[str] | None = None,
    settings: Any = None,
    models: dict[str, Any] | None = None,
    tasks: list[str] | None = None,
    jobs: dict[str, Any] | None = None,
) -> set[str]:
    """Attach the enabled toolkits on a built agent; returns the names attached."""
    names = set(enabled) if enabled is not None else enabled_toolkits(settings)
    if "database" in names:
        attach_database(agent, models)
    if "scheduler" in names:
        attach_scheduler(agent, tasks)
    if "queue" in names:
        attach_queue(agent, jobs, tasks)
    if "notifications" in names:
        attach_notifications(agent)
    if "history" in names:
        attach_history(agent)
    if "usage" in names:
        attach_usage(agent)
    if "knowledge_admin" in names:
        attach_knowledge_admin(agent)
    if "skills_admin" in names:
        attach_skill_authoring(agent)
    return names
