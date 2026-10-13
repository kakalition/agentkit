"""The agentkit framework foundation: app container, providers, facades.

Everything here is additive on top of the existing building blocks; the
low-level modules (``agentkit.runtime``, ``agentkit.session`` …) keep working
unchanged.
"""

from agentkit.foundation.agent import Agent
from agentkit.foundation.application import App, ChannelSpec, Turn, discover_providers
from agentkit.foundation.commands import Command, load_bootstrap
from agentkit.foundation.config import Section
from agentkit.foundation.container import Container
from agentkit.foundation.db import active_repos, session_scope, using_repos
from agentkit.foundation.events import Dispatcher, Event, Listener
from agentkit.foundation.facade import (
    Facade,
    current_app,
    emit,
    get_current_app,
    set_current_app,
    using,
)
from agentkit.foundation.facades import (
    DB,
    Cache,
    Events,
    Feedback,
    Log,
    Memory,
    Queue,
    Schedule,
    Storage,
)
from agentkit.foundation.jobs import CacheStore
from agentkit.foundation.middleware import (
    guardrails_hooks,
    lifecycle_hooks,
    logging_middleware,
    policy_hooks,
)
from agentkit.foundation.model import Model, Query
from agentkit.foundation.notifications import Notification, Notifier, SentNotification
from agentkit.foundation.pipeline import Middleware, Pipeline, run_pipeline
from agentkit.foundation.provider import DeferrableProvider, Provider
from agentkit.foundation.queue import Job
from agentkit.foundation.repository import Repository, RepositoryQuery
from agentkit.foundation.scaffold import package_name, scaffold_project
from agentkit.foundation.schedule import ScheduleBuilder
from agentkit.foundation.service import Service
from agentkit.foundation.storage import Filesystem
from agentkit.foundation.validation import Rule, ValidationError, validate

__all__ = [
    "Agent",
    "App",
    "Cache",
    "CacheStore",
    "ChannelSpec",
    "Command",
    "Container",
    "DB",
    "Dispatcher",
    "Event",
    "Events",
    "Facade",
    "Feedback",
    "Filesystem",
    "Job",
    "Listener",
    "Log",
    "Memory",
    "Middleware",
    "Model",
    "Notification",
    "Notifier",
    "Pipeline",
    "DeferrableProvider",
    "Provider",
    "Query",
    "Queue",
    "Repository",
    "RepositoryQuery",
    "Rule",
    "Schedule",
    "ScheduleBuilder",
    "Section",
    "SentNotification",
    "Service",
    "Storage",
    "Turn",
    "ValidationError",
    "active_repos",
    "current_app",
    "discover_providers",
    "emit",
    "get_current_app",
    "package_name",
    "scaffold_project",
    "guardrails_hooks",
    "lifecycle_hooks",
    "load_bootstrap",
    "logging_middleware",
    "policy_hooks",
    "run_pipeline",
    "session_scope",
    "set_current_app",
    "using",
    "using_repos",
    "validate",
]
