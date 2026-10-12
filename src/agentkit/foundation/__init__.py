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
from agentkit.foundation.facades import DB, Events, Feedback, Log, Memory, Schedule
from agentkit.foundation.middleware import (
    guardrails_hooks,
    lifecycle_hooks,
    logging_middleware,
    policy_hooks,
)
from agentkit.foundation.model import Model, Query
from agentkit.foundation.pipeline import Middleware, Pipeline, run_pipeline
from agentkit.foundation.provider import Provider

__all__ = [
    "Agent",
    "App",
    "ChannelSpec",
    "Command",
    "Container",
    "DB",
    "Dispatcher",
    "Event",
    "Events",
    "Facade",
    "Feedback",
    "Listener",
    "Log",
    "Memory",
    "Middleware",
    "Model",
    "Pipeline",
    "Provider",
    "Query",
    "Schedule",
    "Section",
    "Turn",
    "active_repos",
    "current_app",
    "discover_providers",
    "emit",
    "get_current_app",
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
]
