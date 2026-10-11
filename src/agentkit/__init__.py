"""agentkit — building blocks for PydanticAI personal-assistant agents.

Compose an agent from: model config + resilience (:mod:`agentkit.config`), an
orchestrator with delegated specialists (:mod:`agentkit.orchestrator`), typed
deps (:mod:`agentkit.deps`), HITL approvals (:mod:`agentkit.approvals`), a
libSQL-backed runtime with durable history (:mod:`agentkit.runtime`,
:mod:`agentkit.session`), DBOS durability (:mod:`agentkit.durability`), an MCP
client registry (:mod:`agentkit.mcp`), A2A client + task-based server
(:mod:`agentkit.a2a`), and CLI/Telegram gateways (:mod:`agentkit.gateways`).
"""

from agentkit import durability, scheduler
from agentkit.app import AgentApp
from agentkit.approvals import approval_capability, approval_handler, auto_approver
from agentkit.config import (
    AgentSettings,
    build_model,
    get_settings,
    model_settings,
    usage_limits,
)
from agentkit.deps import ApprovalCallback, ApprovalRequest, Deps
from agentkit.errors import (
    AgentKitError,
    ConfigurationError,
    Conflict,
    DependencyMissing,
    InvalidInput,
    NotFound,
    PermissionDenied,
    RateLimited,
    UpstreamError,
)
from agentkit.guardrails import (
    check_egress,
    is_loopback,
    is_suspicious,
    redact,
    scan_injection,
    warn_if_exposed,
    wrap_untrusted,
)
from agentkit.health import Check, db_check, health_routes, install_signal_handlers
from agentkit.logging import get_logger, request_context, setup_logging
from agentkit.logging import redact as redact_text
from agentkit.observability import setup_logfire, setup_observability
from agentkit.orchestrator import Orchestrator, delegate, make_delegate
from agentkit.policy import ALLOW, APPROVE, DENY, ToolPolicy
from agentkit.runtime import Runtime, build_deps, build_runtime, repositories
from agentkit.session import ChatResult, ChatRunner, load_history, save_new_messages

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # app facade + durable scheduling
    "AgentApp",
    "durability",
    "scheduler",
    # config
    "AgentSettings",
    "get_settings",
    "build_model",
    "model_settings",
    "usage_limits",
    # agent framework
    "Deps",
    "ApprovalRequest",
    "ApprovalCallback",
    "Orchestrator",
    "delegate",
    "make_delegate",
    "approval_capability",
    "approval_handler",
    "auto_approver",
    # persistence / runtime
    "Runtime",
    "build_runtime",
    "repositories",
    "build_deps",
    "ChatRunner",
    "ChatResult",
    "load_history",
    "save_new_messages",
    # cross-cutting: observability, logging, guardrails, policy, errors, health
    "setup_observability",
    "setup_logfire",
    "setup_logging",
    "get_logger",
    "redact_text",
    "request_context",
    "is_loopback",
    "warn_if_exposed",
    "is_suspicious",
    "scan_injection",
    "redact",
    "wrap_untrusted",
    "check_egress",
    "ToolPolicy",
    "ALLOW",
    "APPROVE",
    "DENY",
    "AgentKitError",
    "ConfigurationError",
    "InvalidInput",
    "NotFound",
    "Conflict",
    "PermissionDenied",
    "RateLimited",
    "DependencyMissing",
    "UpstreamError",
    "Check",
    "db_check",
    "health_routes",
    "install_signal_handlers",
]
