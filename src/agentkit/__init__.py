"""agentkit — building blocks for PydanticAI personal-assistant agents.

Compose an agent from: model config + resilience (:mod:`agentkit.config`), an
orchestrator with delegated specialists (:mod:`agentkit.orchestrator`), typed
deps (:mod:`agentkit.deps`), HITL approvals (:mod:`agentkit.approvals`), a
libSQL-backed runtime with durable history (:mod:`agentkit.runtime`,
:mod:`agentkit.session`), DBOS durability (:mod:`agentkit.durability`), an MCP
client registry (:mod:`agentkit.mcp`), A2A client + task-based server
(:mod:`agentkit.a2a`), and CLI/Telegram gateways (:mod:`agentkit.gateways`).
"""

from agentkit import durability, scheduler, workspace
from agentkit.agents import (
    AgentHandle,
    AgentRegistry,
    Mailbox,
    attach_agents,
    handoff,
    handoff_tool,
    mailbox_tools,
)
from agentkit.app import AgentApp
from agentkit.approvals import approval_capability, approval_handler, auto_approver
from agentkit.audio import synthesize, transcribe
from agentkit.cache import cached_tool
from agentkit.compaction import Compactor, summarize_older, transcript, truncating_processor
from agentkit.config import (
    AgentSettings,
    build_model,
    get_settings,
    model_settings,
    usage_limits,
)
from agentkit.consolidation import consolidate_memories
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
from agentkit.evals import Case, CaseResult, EvalSuite, Report
from agentkit.foundation import (
    DB,
    Agent,
    App,
    Cache,
    CacheStore,
    ChannelSpec,
    Command,
    Container,
    DeferrableProvider,
    Dispatcher,
    Event,
    Events,
    Facade,
    Feedback,
    Filesystem,
    FullStackProvider,
    Job,
    Listener,
    Log,
    Memory,
    Middleware,
    Model,
    Notification,
    Notifier,
    Pipeline,
    Provider,
    Query,
    Queue,
    Repository,
    RepositoryQuery,
    Rule,
    Schedule,
    ScheduleBuilder,
    Section,
    SentNotification,
    Storage,
    Turn,
    ValidationError,
    current_app,
    discover_providers,
    emit,
    load_bootstrap,
    package_name,
    run_pipeline,
    scaffold_project,
    using,
    validate,
)
from agentkit.graph import END, GraphError, StateGraph
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
from agentkit.helpers import (
    app,
    cache,
    config,
    dispatch,
    env,
    event,
    logger,
    notify,
    queue,
    report,
    resolve,
    storage,
)
from agentkit.hitl import Clarification, clarification_tool
from agentkit.knowledge import KnowledgeBase, chunk_text
from agentkit.learning import (
    LESSON_TASK,
    LearningSignals,
    attach_learning,
    lessons_digest,
    reflect,
    register_reflect_task,
)
from agentkit.limits import Budget
from agentkit.logging import get_logger, request_context, setup_logging
from agentkit.logging import redact as redact_text
from agentkit.memory import attach_memory, memory_digest
from agentkit.model_providers import (
    register_model_provider,
    resolve_model,
    supported_prefixes,
)
from agentkit.moderation import (
    ModerationPolicy,
    ModerationResult,
    check_output,
    moderation_hooks,
    moderation_middleware,
)
from agentkit.multimodal import audio, content, document, image, text
from agentkit.observability import setup_logfire, setup_observability, start_phoenix
from agentkit.orchestrator import Orchestrator, delegate, make_delegate
from agentkit.planning import Plan, Planner, PlanStep
from agentkit.policy import (
    ALLOW,
    APPROVE,
    DENY,
    NATIVE_APPROVAL_TOOLS,
    NATIVE_TOOLS_POLICY,
    ToolPolicy,
    native_policy,
)
from agentkit.pricing import (
    ModelPrice,
    Pricing,
    default_pricing,
    estimate_cost,
    set_default_pricing,
    usage_cost,
)
from agentkit.prompts import Prompt, PromptRegistry
from agentkit.routing import ModelRouter, Route
from agentkit.runtime import Runtime, build_deps, build_runtime, repositories
from agentkit.sandbox import CommandResult, Sandbox, SandboxError
from agentkit.session import ChatResult, ChatRunner, StreamEvent, load_history, save_new_messages
from agentkit.skills import (
    Skill,
    SkillRegistry,
    load_skill_file,
    parse_front_matter,
    render_skill_file,
    slugify_skill,
    write_skill_file,
)
from agentkit.soul import (
    DEFAULT_SOUL,
    SOUL_FILENAME,
    compose_instructions,
    ensure_soul,
    load_soul,
    soul_path,
)
from agentkit.supervise import Service, run_all
from agentkit.teams import Supervisor, spawn_tool, team_tools
from agentkit.toolkits import TOOLKITS, attach_toolkits, enabled_toolkits
from agentkit.webui import build_webui_app, serve_webui, webui_service
from agentkit.workspace import (
    default_workspace_root,
    detect_legacy,
    migrate,
    workspace_dir,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # app facade + durable scheduling
    "AgentApp",
    # framework foundation (Laravel-style front door)
    "Agent",
    "App",
    "Provider",
    "DeferrableProvider",
    "FullStackProvider",
    "Facade",
    "Event",
    "ChannelSpec",
    "Container",
    "Command",
    "Dispatcher",
    "Pipeline",
    "Middleware",
    "Section",
    "Memory",
    "Schedule",
    "DB",
    "Events",
    "Log",
    "Feedback",
    "Model",
    "Query",
    "Repository",
    "RepositoryQuery",
    "Turn",
    "Listener",
    "Notification",
    "Notifier",
    "SentNotification",
    "Job",
    "Queue",
    "Cache",
    "CacheStore",
    "Storage",
    "Filesystem",
    "ScheduleBuilder",
    "Rule",
    "ValidationError",
    "validate",
    # global helpers (Laravel-style)
    "app",
    "config",
    "env",
    "resolve",
    "dispatch",
    "event",
    "notify",
    "cache",
    "storage",
    "queue",
    "logger",
    "report",
    "current_app",
    "using",
    "run_pipeline",
    "discover_providers",
    "load_bootstrap",
    "scaffold_project",
    "package_name",
    "emit",
    "durability",
    "scheduler",
    # workspace layout + legacy migration
    "workspace",
    "default_workspace_root",
    "workspace_dir",
    "detect_legacy",
    "migrate",
    # operator web UI
    "build_webui_app",
    "serve_webui",
    "webui_service",
    # persona (SOUL.md)
    "DEFAULT_SOUL",
    "SOUL_FILENAME",
    "load_soul",
    "ensure_soul",
    "soul_path",
    "compose_instructions",
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
    # agent-to-agent communication
    "AgentHandle",
    "AgentRegistry",
    "Mailbox",
    "attach_agents",
    "handoff",
    "handoff_tool",
    "mailbox_tools",
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
    "StreamEvent",
    "load_history",
    "save_new_messages",
    # memory
    "attach_memory",
    "memory_digest",
    "consolidate_memories",
    # self-learning (reflect -> learn -> apply)
    "attach_learning",
    "lessons_digest",
    "reflect",
    "register_reflect_task",
    "LearningSignals",
    "LESSON_TASK",
    # native toolkits (first-class agent-callable capabilities)
    "attach_toolkits",
    "enabled_toolkits",
    "TOOLKITS",
    # history compaction
    "Compactor",
    "summarize_older",
    "transcript",
    "truncating_processor",
    # retrieval-augmented generation
    "KnowledgeBase",
    "chunk_text",
    # evaluations
    "EvalSuite",
    "Case",
    "CaseResult",
    "Report",
    # human-in-the-loop
    "Clarification",
    "clarification_tool",
    # planning / graphs / teams
    "Planner",
    "Plan",
    "PlanStep",
    "StateGraph",
    "END",
    "GraphError",
    "Supervisor",
    "spawn_tool",
    "team_tools",
    # tooling
    "cached_tool",
    # safety
    "ModerationPolicy",
    "ModerationResult",
    "moderation_middleware",
    "moderation_hooks",
    "check_output",
    # ops
    "Budget",
    "PromptRegistry",
    "Prompt",
    # multimodal + audio
    "image",
    "audio",
    "document",
    "content",
    "text",
    "transcribe",
    "synthesize",
    # sandboxed workspace
    "Sandbox",
    "CommandResult",
    "SandboxError",
    # skills (discoverable SKILL.md folders)
    "Skill",
    "SkillRegistry",
    "load_skill_file",
    "parse_front_matter",
    "render_skill_file",
    "slugify_skill",
    "write_skill_file",
    # cross-cutting: observability, logging, guardrails, policy, errors, health
    "setup_observability",
    "setup_logfire",
    "start_phoenix",
    "Service",
    "run_all",
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
    "NATIVE_TOOLS_POLICY",
    "NATIVE_APPROVAL_TOOLS",
    "native_policy",
    # model routing + pricing
    "ModelRouter",
    "Route",
    "resolve_model",
    "register_model_provider",
    "supported_prefixes",
    "Pricing",
    "ModelPrice",
    "default_pricing",
    "set_default_pricing",
    "estimate_cost",
    "usage_cost",
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
