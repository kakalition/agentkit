"""Native toolkits: every agentkit capability as first-class, agent-callable tools.

Each :class:`~agentkit.foundation.tools.Toolkit` subclass registers its tools on a
*built* PydanticAI agent (idempotent). :func:`install_toolkits` installs the
settings-enabled set — used by ``Agent.full()``/``Agent.native()``. Reachable
models/tasks/jobs stay deny-by-default (empty allow-lists) and writes require
approval, so enabling a toolkit is safe.
"""

from __future__ import annotations

from typing import Any

from agentkit.foundation.tools import Toolkit
from agentkit.toolkits.database import _attach_database
from agentkit.toolkits.history import _attach_history
from agentkit.toolkits.knowledge_admin import _attach_knowledge_admin
from agentkit.toolkits.notifications import _attach_notifications
from agentkit.toolkits.queue import RunRegisteredTask, _attach_queue
from agentkit.toolkits.scheduler import _attach_scheduler
from agentkit.toolkits.skills_admin import _attach_skill_authoring
from agentkit.toolkits.usage import _attach_usage

__all__ = [
    "TOOLKITS",
    "TOOLKIT_CLASSES",
    "DatabaseToolkit",
    "HistoryToolkit",
    "KnowledgeAdminToolkit",
    "NotificationsToolkit",
    "QueueToolkit",
    "RunRegisteredTask",
    "SchedulerToolkit",
    "SkillAuthoringToolkit",
    "UsageToolkit",
    "attach_database",
    "attach_history",
    "attach_knowledge_admin",
    "attach_notifications",
    "attach_queue",
    "attach_scheduler",
    "attach_skill_authoring",
    "attach_usage",
    "enabled_toolkits",
    "install_toolkits",
    "toolkit_for",
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


# -- functional form of the built-in toolkits ------------------------------
# These public ``attach_*`` helpers are the closure/functional face of the
# ``Toolkit`` classes below; the classes delegate to them, so both forms install
# exactly the same tools. Prefer a class for a reusable bundle, a helper for a
# one-off install.
attach_database = _attach_database
attach_history = _attach_history
attach_knowledge_admin = _attach_knowledge_admin
attach_notifications = _attach_notifications
attach_queue = _attach_queue
attach_scheduler = _attach_scheduler
attach_skill_authoring = _attach_skill_authoring
attach_usage = _attach_usage


# -- class-based toolkits (thin wrappers over the attach_* helpers) ---------
class DatabaseToolkit(Toolkit):
    name = "database"

    def __init__(self, models: dict[str, Any] | None = None, **options: Any) -> None:
        super().__init__(models=models, **options)
        self.models = models

    def install(self, agent: Any) -> Any:
        return _attach_database(agent, self.models)


class SchedulerToolkit(Toolkit):
    name = "scheduler"

    def __init__(self, tasks: list[str] | None = None, **options: Any) -> None:
        super().__init__(tasks=tasks, **options)
        self.tasks = tasks

    def install(self, agent: Any) -> Any:
        return _attach_scheduler(agent, self.tasks)


class QueueToolkit(Toolkit):
    name = "queue"

    def __init__(
        self, jobs: dict[str, Any] | None = None, tasks: list[str] | None = None, **options: Any
    ) -> None:
        super().__init__(jobs=jobs, tasks=tasks, **options)
        self.jobs = jobs
        self.tasks = tasks

    def install(self, agent: Any) -> Any:
        return _attach_queue(agent, self.jobs, self.tasks)


class NotificationsToolkit(Toolkit):
    name = "notifications"

    def install(self, agent: Any) -> Any:
        return _attach_notifications(agent)


class HistoryToolkit(Toolkit):
    name = "history"

    def install(self, agent: Any) -> Any:
        return _attach_history(agent)


class UsageToolkit(Toolkit):
    name = "usage"

    def install(self, agent: Any) -> Any:
        return _attach_usage(agent)


class KnowledgeAdminToolkit(Toolkit):
    name = "knowledge_admin"

    def install(self, agent: Any) -> Any:
        return _attach_knowledge_admin(agent)


class SkillAuthoringToolkit(Toolkit):
    name = "skills_admin"

    def install(self, agent: Any) -> Any:
        return _attach_skill_authoring(agent)


TOOLKIT_CLASSES: dict[str, type[Toolkit]] = {
    "database": DatabaseToolkit,
    "scheduler": SchedulerToolkit,
    "queue": QueueToolkit,
    "notifications": NotificationsToolkit,
    "history": HistoryToolkit,
    "usage": UsageToolkit,
    "knowledge_admin": KnowledgeAdminToolkit,
    "skills_admin": SkillAuthoringToolkit,
}


def toolkit_for(name: str) -> type[Toolkit]:
    """The :class:`~agentkit.foundation.tools.Toolkit` class for a toolkit name."""
    klass = TOOLKIT_CLASSES.get(name)
    if klass is None:
        raise KeyError(f"unknown toolkit {name!r}")
    return klass


def enabled_toolkits(settings: Any = None) -> set[str]:
    """The toolkits whose settings flag is on (all, when there are no settings)."""
    if settings is None:
        return set(TOOLKITS)
    return {
        name
        for name, flag in TOOLKITS.items()
        if bool(getattr(settings, flag, True))
    }


def install_toolkits(
    agent: Any,
    *,
    enabled: set[str] | None = None,
    settings: Any = None,
    models: dict[str, Any] | None = None,
    tasks: list[str] | None = None,
    jobs: dict[str, Any] | None = None,
) -> set[str]:
    """Install the enabled :class:`Toolkit` classes on a built agent (returns names)."""
    names = set(enabled) if enabled is not None else enabled_toolkits(settings)
    options: dict[str, dict[str, Any]] = {
        "database": {"models": models},
        "scheduler": {"tasks": tasks},
        "queue": {"jobs": jobs, "tasks": tasks},
    }
    for name in sorted(names):
        klass = TOOLKIT_CLASSES.get(name)
        if klass is None:
            raise KeyError(f"unknown toolkit {name!r}")
        klass(**options.get(name, {})).install(agent)
    return names
