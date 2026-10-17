"""The application container: providers, concerns, and the turn runner.

``App`` is the framework front door. It owns the settings, a service container,
the lifecycle event bus, a middleware pipeline, and the registries providers
contribute to (agent, tools, channels, commands, schedules, migrations, config).

Boot order is explicit and load-bearing::

    all Provider.register()  ->  all Provider.boot()  ->  scheduler/services

Importing a provider module must be side-effect-free; only ``register``/``boot``
may act.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

from agentkit.config import AgentSettings, build_model, get_settings
from agentkit.db.repositories import Repositories
from agentkit.deps import ApprovalCallback
from agentkit.foundation.agent import Agent as AgentBuilder
from agentkit.foundation.container import Container
from agentkit.foundation.events import Dispatcher, Listener
from agentkit.foundation.facade import set_current_app
from agentkit.foundation.facades import (
    CacheService,
    DBService,
    EventsService,
    FeedbackService,
    LogService,
    MemoryService,
    QueueService,
    ScheduleService,
    StorageService,
)
from agentkit.foundation.notifications import Notifier
from agentkit.foundation.provider import Provider
from agentkit.foundation.queue import Job
from agentkit.foundation.schedule import ScheduleBuilder
from agentkit.logging import get_logger
from agentkit.runtime import Runtime, build_deps, build_runtime, repositories
from agentkit.security import Actor
from agentkit.session import ChatResult, ChatRunner

log = get_logger("agentkit.app")

PROVIDER_ENTRY_POINT_GROUP = "agentkit.providers"

# Modules whose import registers the built-in core drivers (via Manager subclasses
# and @register_driver). Importing them lazily keeps App construction robust even
# when callers import agentkit.foundation.application directly.
_BUILTIN_DRIVER_MODULES = (
    "agentkit.foundation.jobs",  # cache
    "agentkit.prompts",  # prompts
    "agentkit.embeddings",  # embeddings
    "agentkit.pricing",  # pricing
    "agentkit.ingest",  # ingest
    "agentkit.audio",  # audio
    "agentkit.db.engine",  # database dialect
    "agentkit.foundation.queue",  # queue
    "agentkit.scheduler",  # scheduler
    "agentkit.search",  # conversation search indexes
    "agentkit.observability",  # observability
    "agentkit.foundation.storage",  # storage
    "agentkit.guardrails",  # guardrails
    "agentkit.ratelimit",  # rate limiting
    "agentkit.durability",  # durability
    "agentkit.security.authenticator",  # auth
    "agentkit.security.credentials",  # vault
    "agentkit.memory",  # memory store + recall strategy
    "agentkit.knowledge",  # rag: chunker / retriever / reranker
    "agentkit.learning",  # learning extractor / strategy / sink
    "agentkit.comms",  # comms topologies
    "agentkit.tasks",  # task store + planning strategy
    "agentkit.agents.subagent",  # subagent context strategies
    "agentkit.agents.speaker",  # group-chat speaker strategies
    "agentkit.foundation.agent_middleware",  # agent middleware
    "agentkit.graph",  # graph executors
    "agentkit.executors",  # code executors
    "agentkit.evals",  # eval reporters
    "agentkit.checkpoints",  # checkpoint stores
    "agentkit.computer",  # computer-use drivers
    "agentkit.realtime",  # realtime voice drivers
    "agentkit.graders",  # eval graders
    "agentkit.catalog",  # catalog sources
    "agentkit.specs",  # spec kinds + built-in Studio panels
    "agentkit.extensions",  # extension registry + panel/action SPI
    "agentkit.gateways.registry",  # chat channels
    "agentkit.foundation.notifications",  # notification channels
)


def _load_builtin_drivers() -> None:
    for module in _BUILTIN_DRIVER_MODULES:
        importlib.import_module(module)


def discover_providers(group: str = PROVIDER_ENTRY_POINT_GROUP) -> list[Any]:
    """Load installed providers from the ``agentkit.providers`` entry-point group.

    A failed entry point is logged and skipped so one bad package cannot stop the
    app from booting.
    """
    discovered: list[Any] = []
    for entry_point in entry_points(group=group):
        try:
            discovered.append(entry_point.load())
        except Exception:  # pragma: no cover - defensive
            log.exception("failed to load provider entry point %r", entry_point.name)
    return discovered


class App:
    """A container + lifecycle for one primary agent and its channels."""

    def __init__(
        self,
        name: str | None = None,
        settings: AgentSettings | type[AgentSettings] | None = None,
        *,
        discover: bool = True,
        repos_factory: type[Repositories] = Repositories,
        model: Any = None,
        mcp: Any = None,
        a2a: Any = None,
    ) -> None:
        self.name = name
        self._settings = settings
        self.repos_factory = repos_factory or Repositories
        self.container = Container()
        self.events = Dispatcher(self)
        self._providers: list[Any] = []
        self._provider_instances: list[Provider] = []
        self._deferred: dict[Any, Provider] = {}
        self._middlewares: list[Any] = []
        self._fakes: dict[str, Any] = {}
        self._middleware_groups: dict[str, list[Any]] = {}
        self._booted = False
        self._agent_builder: AgentBuilder | None = None
        self._agent: Any = None
        self._pending_tools: list[Any] = []
        self._channels: dict[str, ChannelSpec] = {}
        self._commands: dict[str, Any] = {}
        self._schedules: list[Any] = []
        self._migrations: list[Any] = []
        self._config_schemas: dict[str, Any] = {}
        self._config_cache: dict[str, Any] = {}
        self._runtime: Runtime | None = None
        self._model = model
        self._mcp = mcp
        self._a2a = a2a
        self._history_processor: Any = None
        self._model_resolver: Any = None
        self._clarify_handler: Any = None
        self._budget: Any = None
        self._managers: dict[str, Any] = {}
        self._notifier = Notifier(self)
        self._agent_models: dict[str, Any] = {}
        self._agent_tasks: list[str] = []
        self._agent_jobs: dict[str, Any] = {}
        self._credential_service: Any = None
        self._running: dict[str, Any] = {}
        self._approval_queue: Any = None
        self._posture: str | None = None
        self._extension_manifests: list[Any] = []
        self._extensions_loaded = False
        self._applied_extensions: list[dict[str, Any]] = []

        self.container.instance("app", self)
        _load_builtin_drivers()
        self._bind_facades()
        if discover:
            self._providers.extend(discover_providers())

    # -- fluent entry point ---------------------------------------------
    @classmethod
    def configure(
        cls,
        name: str | None = None,
        settings: AgentSettings | type[AgentSettings] | None = None,
        base_path: str | Path | None = None,
        *,
        discover: bool = True,
        repos_factory: type[Repositories] | None = None,
        model: Any = None,
        mcp: Any = None,
        a2a: Any = None,
    ) -> ApplicationBuilder:
        """Start a fluent build (Laravel's ``Application::configure()``).

        Returns an :class:`ApplicationBuilder`; discovery of ``app/``/``config/``
        runs when :meth:`ApplicationBuilder.create` is called (never here).
        """
        return ApplicationBuilder(
            name=name,
            settings=settings,
            base_path=base_path,
            discover=discover,
            repos_factory=repos_factory,
            model=model,
            mcp=mcp,
            a2a=a2a,
        )

    # -- settings -------------------------------------------------------
    @property
    def settings(self) -> AgentSettings:
        if self._settings is None:
            self._settings = get_settings()
        elif isinstance(self._settings, type):
            self._settings = self._settings()
        return self._settings

    # -- providers ------------------------------------------------------
    def providers(self, providers: Any) -> App:
        """Register provider classes/instances (before ``boot``)."""
        if isinstance(providers, (Provider, type)):
            providers = [providers]
        self._providers.extend(providers)
        return self

    def fullstack(self) -> App:
        """Register :class:`~agentkit.foundation.fullstack.FullStackProvider`."""
        from agentkit.foundation.fullstack import FullStackProvider

        return self.providers([FullStackProvider])

    # -- extensions -----------------------------------------------------
    def extensions(self, *manifests: Any) -> App:
        """Register programmatic extension manifests (applied at ``boot``).

        Discovery (entry points, ``AGENTKIT_EXTENSIONS``) is layered underneath so
        a programmatic manifest of the same name wins (D9).
        """
        from agentkit.extensions.discovery import resolve_manifest

        for manifest in manifests:
            items = manifest if isinstance(manifest, (list, tuple)) else [manifest]
            for item in items:
                try:
                    self._extension_manifests.append(resolve_manifest(item))
                except Exception:  # pragma: no cover - never fatal
                    log.exception("could not resolve extension manifest %r", item)
        return self

    def extension_info(self) -> list[dict[str, Any]]:
        """A description of the applied extensions (empty before ``boot``)."""
        return list(self._applied_extensions)

    def _apply_extensions(self) -> None:
        """Register discovered + programmatic manifests and apply them (once)."""
        if self._extensions_loaded:
            return
        from agentkit.extensions import EXTENSIONS
        from agentkit.extensions.discovery import discover_manifests

        for manifest in discover_manifests():
            EXTENSIONS.register_manifest(manifest)
        for manifest in self._extension_manifests:
            EXTENSIONS.register_manifest(manifest)
        self._applied_extensions = EXTENSIONS.apply(self)
        self._extensions_loaded = True

    def boot(self) -> App:
        """Run the register/boot lifecycle once (idempotent)."""
        if self._booted:
            return self
        self._apply_posture_settings()
        self._apply_extensions()
        from agentkit import scheduler as _scheduler

        _scheduler.set_result_sink(self._deliver_result)
        instances: list[Provider] = []
        for candidate in self._providers:
            provider = candidate() if isinstance(candidate, type) else candidate
            provider.app = self
            instances.append(provider)
        self._provider_instances = instances

        for provider in instances:
            if provider.provides():
                for service in provider.provides():
                    self._deferred[service] = provider
                continue  # deferred: registered on first use
            self._apply_bindings(provider)
            provider.register(self)
            for command in provider.commands():
                self.command(command)
            contributed_listeners = provider.listeners()
            if contributed_listeners:
                self.listeners(contributed_listeners)
            for middleware in provider.middleware():
                self.middleware(middleware)
            contributed_policies = provider.policies()
            if contributed_policies:
                self.policies(contributed_policies)
            contributed = provider.schedules()
            if contributed:
                self.schedules(contributed)

        for provider in instances:
            if provider.provides():
                continue
            provider.boot(self)

        self._apply_schedules()

        if int(getattr(self.settings, "memory_nudge_every", 0) or 0) > 0:
            from agentkit.nudges import register_memory_nudges

            register_memory_nudges(self)

        self._booted = True
        set_current_app(self)
        self._wire_validation()
        self.events.dispatch("boot", app=self)
        return self

    def _wire_validation(self) -> None:
        """Back ``Rule.unique``/``Rule.exists`` with the app's repositories."""
        from agentkit.foundation.validation import set_uniqueness_resolver

        app = self

        def resolver(model: type, filters: dict[str, Any]) -> bool:
            from sqlmodel import func, select

            from agentkit._sync import run_sync
            from agentkit.foundation.db import session_scope

            async def check() -> int:
                async with session_scope(app) as repos:
                    stmt: Any = select(func.count()).select_from(model)
                    for field, value in filters.items():
                        stmt = stmt.where(getattr(model, field) == value)
                    return int((await repos.session.exec(stmt)).one())

            return run_sync(check()) > 0

        set_uniqueness_resolver(resolver)

    # -- agent ----------------------------------------------------------
    def agent(self, agent: Any = None) -> Any:
        """Get the primary agent, or set it (builder or built PydanticAI agent)."""
        if agent is None:
            if self._agent is None and self._agent_builder is not None:
                self._agent = self._agent_builder.build(settings=self.settings, events=self.events)
                self._flush_pending_tools()
            return self._agent
        if isinstance(agent, AgentBuilder):
            self._agent_builder = agent
            self._agent = None
        else:
            self._agent = agent
            self._agent_builder = None
        self._flush_pending_tools()
        return agent

    def _flush_pending_tools(self) -> None:
        while self._pending_tools:
            function, requires_approval = self._pending_tools.pop(0)
            self.tool(function, requires_approval=requires_approval)

    def tool(self, function: Any, *, requires_approval: bool = False) -> App:
        """Register a tool: a plain function, a :class:`Tool` class, or an instance."""
        from agentkit.foundation.tools import Tool, resolve_tool

        resolved = resolve_tool(function)
        if self._agent_builder is not None:
            self._agent_builder.tool(resolved, requires_approval=requires_approval)
        elif self._agent is not None:
            if isinstance(resolved, Tool):
                options = dict(resolved.tool_options())
                target = resolved.function()
            else:
                options = {}
                target = resolved
            if requires_approval:
                options["requires_approval"] = True
            if options:
                self._agent.tool(**options)(target)
            else:
                self._agent.tool(target)
        else:
            self._pending_tools.append((resolved, requires_approval))
        return self

    # -- registries -----------------------------------------------------
    def channel(self, name: str, factory: Any = None, **options: Any) -> App:
        """Register a channel factory: ``factory(app) -> Service | list[Service]``."""
        self._channels[name] = ChannelSpec(name=name, factory=factory, options=options)
        return self

    def channels(self) -> dict[str, ChannelSpec]:
        return dict(self._channels)

    def policies(self, policies: Any) -> App:
        """Register authorization policies on the Gate (classes or instances)."""
        if isinstance(policies, dict):
            for subject, policy_class in policies.items():
                self.gate.policy(subject, policy_class)
            return self
        for policy in policies:
            subject = getattr(policy, "model", None) or type(policy).__name__.removesuffix("Policy")
            self.gate.policy(subject, policy)
        return self

    def tool_policy(self, policy: Any) -> App:
        """Install a tool-RBAC policy on this app's Gate."""
        self.gate.tool_policy(policy)
        return self

    def commands(self, commands: Any) -> App:
        """Register commands: classes, instances, string specs, or closures.

        A ``(signature, callable)`` pair (or a bare callable) becomes a
        :class:`~agentkit.foundation.commands.ClosureCommand` — the functional form
        of a class-based ``Command``.
        """
        if isinstance(commands, dict):
            self._commands.update(commands)
            return self
        for command in commands:
            self._register_command(command)
        return self

    def _register_command(self, command: Any) -> None:
        from agentkit.foundation.commands import ClosureCommand, Command

        if isinstance(command, str):
            if ":" in command:
                resolved = self.container.wrap(command, protocol="command")
                if resolved is not None:
                    self._commands[_command_name(resolved)] = resolved
            else:
                self._commands[command] = command
            return
        if isinstance(command, tuple) and len(command) == 2 and callable(command[1]):
            closure = ClosureCommand(command[0], command[1])
            self._commands[closure.command_name()] = closure
            return
        if isinstance(command, (ClosureCommand, Command)):
            self._commands[command.command_name()] = command
            return
        if callable(command) and not isinstance(command, type):
            closure = ClosureCommand(getattr(command, "__name__", "command"), command)
            self._commands[closure.command_name()] = closure
            return
        self._commands[_command_name(command)] = command

    def command(self, command: Any) -> App:
        return self.commands([command])

    def listeners(self, listeners: Any) -> App:
        """Register event listeners (classes, instances, callables, string specs)."""
        if isinstance(listeners, (Listener, type, str)) or callable(listeners):
            listeners = [listeners]
        for listener in listeners:
            instance = self.container.wrap(listener, protocol="listener")
            if instance is None:
                continue
            names = instance.events() if hasattr(instance, "events") else []
            if not names and isinstance(getattr(instance, "event", None), str):
                names = [instance.event]
            for name in names:
                self.events.listen(name, instance)
        return self

    def on(self, event: Any, listener: Any) -> App:
        """Register an event listener (``app.on("turn.end", fn)``, chainable).

        ``listener`` may be a closure/callable, a :class:`Listener` class or
        instance, or a ``"module:attr"`` string spec. Accepts an event name, a
        :class:`Event` class, or ``"*"`` for the wildcard.
        """
        self.events.listen(event, listener)
        return self

    def command_names(self) -> list[str]:
        return sorted(self._commands)

    def install_commands(self, typer_app: Any) -> None:
        """Register provider-contributed commands onto a Typer app."""
        from agentkit.foundation.commands import install

        commands = [c for c in self._commands.values() if not isinstance(c, str)]
        install(typer_app, commands)

    def console(self, base_path: str | Path = ".") -> Any:
        """A :class:`~agentkit.foundation.console.Kernel` for this app's commands."""
        from agentkit.foundation.console import Kernel

        return Kernel(self, base_path)

    def schedules(self, schedules: Any) -> App:
        self._schedules.extend(schedules)
        return self

    def schedule(
        self,
        task: str,
        *,
        name: str | None = None,
        args: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> ScheduleBuilder:
        """Declare a durable schedule fluently (``.every_minute()``, ``.daily_at()``)."""
        builder = ScheduleBuilder(task, name=name, args=args, enabled=enabled)
        self._schedules.append(builder)
        return builder

    def schedule_specs(self) -> list[Any]:
        return list(self._schedules)

    def _apply_schedules(self) -> None:
        """Persist registered schedule specs as durable jobs (idempotent upsert).

        A spec may be a mapping with ``name`` and ``task`` plus either ``cron``
        (recurring) or ``when``/``at`` (one-off), or any object exposing the same
        attributes. Failures are logged and skipped so a bad spec cannot stop boot.
        """
        if not self._schedules:
            return
        from agentkit.logging import get_logger

        log = get_logger("agentkit.app")
        for spec in self._schedules:
            try:
                self._register_schedule(spec)
            except Exception:  # pragma: no cover - defensive
                log.exception("could not register schedule %r", spec)

    def _register_schedule(self, spec: Any) -> None:
        if hasattr(spec, "build"):
            fields = spec.build()
        elif isinstance(spec, dict):
            fields = spec
        else:
            fields = _spec_fields(spec)
        name = fields["name"]
        task = fields["task"]
        args = fields.get("args")
        cron = fields.get("cron")
        when = fields.get("when") or fields.get("at")

        async def _register() -> None:
            async with self.repositories() as repos:
                if cron:
                    await repos.schedules.upsert(
                        name,
                        kind="cron",
                        schedule=cron,
                        task=task,
                        args=json.dumps(args or {}),
                        enabled=fields.get("enabled", True),
                    )
                elif when:
                    dot = when if isinstance(when, str) else when.isoformat()
                    await repos.schedules.upsert(
                        name, kind="once", schedule=dot, task=task, args=json.dumps(args or {})
                    )
                else:
                    raise ValueError(f"schedule {name!r} needs a 'cron' or 'when' field")

        from agentkit._sync import run_sync

        run_sync(_register())

    def migrations(self, migrations: Any) -> App:
        self._migrations.extend(migrations)
        return self

    def config(self, name: str, schema: Any = None) -> Any:
        """Register/get a layered config section (defaults < file < env)."""
        if schema is not None:
            self._config_schemas[name] = schema
            self._config_cache.pop(name, None)
            return self
        if name in self._config_cache:
            return self._config_cache[name]
        schema = self._config_schemas.get(name)
        if schema is None:
            return None
        from agentkit.foundation.config import resolve_section

        section = resolve_section(name, schema)
        self._config_cache[name] = section
        return section

    # -- events + middleware -------------------------------------------
    def middleware(self, middleware: Any) -> App:
        """Register turn middleware: a closure, a ``Middleware`` class/instance, a
        named group (:class:`MiddlewareGroup`), or a group alias.

        Classes are instantiated (autowired) through the shared normalizer; a
        ``"module:attr"`` string spec is imported lazily.
        """
        from agentkit.foundation.pipeline import MiddlewareGroup

        if isinstance(middleware, MiddlewareGroup):
            self._middleware_groups[middleware.name] = [
                self._normalize_middleware(item) for item in middleware.middlewares
            ]
            return self
        if isinstance(middleware, str):
            group = self._middleware_groups.get(middleware)
            if group is None:
                resolved = self.container.wrap(middleware, protocol="middleware")
                if resolved is None:
                    raise KeyError(f"unknown middleware group: {middleware!r}")
                self._middlewares.append(resolved)
                return self
            self._middlewares.extend(group)
            return self
        self._middlewares.append(self._normalize_middleware(middleware))
        return self

    def _normalize_middleware(self, middleware: Any) -> Any:
        resolved = self.container.wrap(middleware, protocol="middleware")
        return middleware if resolved is None else resolved

    def middleware_group(self, name: str, *middlewares: Any) -> App:
        """Declare a named middleware group (usable by alias)."""
        from agentkit.foundation.pipeline import MiddlewareGroup

        return self.middleware(MiddlewareGroup(name, list(middlewares)))

    def history_processor(self, processor: Any) -> App:
        """Set a callable ``messages -> messages`` run before each turn (compaction)."""
        self._history_processor = processor
        return self

    def compact(self, **options: Any) -> App:
        """Compact history with :class:`~agentkit.compaction.Compactor`."""
        from agentkit.compaction import Compactor

        self._history_processor = Compactor(**options)
        return self

    def model_resolver(self, resolver: Any) -> App:
        """Set a callable ``context -> model`` choosing the model per turn.

        ``context`` is the :class:`Turn` for ``run`` (``None`` for ``stream``).
        A :class:`~agentkit.routing.ModelRouter` is callable, so it works here.
        """
        self._model_resolver = resolver
        return self

    def models(self, models_or_resolver: Any) -> App:
        """Record the native-toolkit model allow-list, or set the model resolver.

        Passing a mapping (``{"notes": Note}``) allow-lists those models for the
        database toolkit; passing a callable is an alias for :meth:`model_resolver`.
        """
        if isinstance(models_or_resolver, Mapping):
            self._agent_models.update(models_or_resolver)
            return self
        return self.model_resolver(models_or_resolver)

    def agent_tasks(self, tasks: Any) -> App:
        """Record the task allow-list the scheduler/queue toolkits may reach."""
        self._agent_tasks = list(tasks)
        return self

    def agent_jobs(self, jobs: Any) -> App:
        """Record the :class:`~agentkit.foundation.queue.Job` allow-list by name."""
        self._agent_jobs.update(jobs)
        return self

    def clarify(self, handler: Any) -> App:
        """Set a ``handler(question, options) -> str`` for the ``ask_user`` tool."""
        self._clarify_handler = handler
        return self

    def budget(self, budget: Any) -> App:
        """Enforce a :class:`~agentkit.limits.Budget` before each turn."""
        self._budget = budget
        return self

    def posture(self, name: Any) -> App:
        """Select the app-wide posture (``specialized`` | ``hybrid`` | ``free``)."""
        from agentkit.posture import resolve_posture

        profile = resolve_posture(name)
        self._posture = str(profile.name) if profile is not None else None
        return self

    @property
    def posture_name(self) -> str:
        """The active posture name (explicit, else the ``agent_posture`` setting)."""
        if self._posture is not None:
            return self._posture
        return str(getattr(self.settings, "agent_posture", "hybrid"))

    def _apply_posture_settings(self) -> None:
        """Apply the active posture's settings overrides (once, at boot).

        Runs before the runtime/settings are read elsewhere so ``runtime.settings``
        and ``deps.settings`` (which read the same object) see the override. Only
        replaces ``self._settings`` when a defaulted override actually applies; an
        operator-set (non-default) value wins.
        """
        from agentkit.posture import apply_settings_overrides, resolve_posture

        name = self._posture or getattr(self.settings, "agent_posture", None)
        try:
            profile = resolve_posture(name)
        except ValueError:  # pragma: no cover - defensive
            profile = None
        updated = apply_settings_overrides(self.settings, profile)
        if updated is not self.settings:
            self._settings = updated

    # -- running turns / approvals -------------------------------------
    @property
    def approvals(self) -> Any:
        """The in-process approval queue (for a web approval UI)."""
        if self._approval_queue is None:
            from agentkit.approvals import ApprovalQueue

            self._approval_queue = ApprovalQueue()
        return self._approval_queue

    def running(self) -> list[str]:
        """Conversation ids with a turn currently in flight."""
        return [cid for cid, task in self._running.items() if not task.done()]

    def cancel(self, conversation_id: str) -> bool:
        """Cancel the in-flight turn for ``conversation_id`` (if any)."""
        task = self._running.get(conversation_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def _track(self, conversation_id: str) -> Any:
        import asyncio

        task = asyncio.current_task()
        if task is not None:
            self._running[conversation_id] = task
        return task

    def _untrack(self, conversation_id: str, task: Any) -> None:
        if task is not None and self._running.get(conversation_id) is task:
            self._running.pop(conversation_id, None)

    async def fork(self, source: str, target: str, *, upto: int | None = None) -> int:
        """Copy a conversation's messages into ``target`` (branching)."""
        async with self.repositories() as repos:
            return await repos.conversations.fork(source, target, upto=upto)

    async def replay(
        self,
        conversation_id: str,
        *,
        target: str | None = None,
        approve: ApprovalCallback | None = None,
    ) -> ChatResult:
        """Re-run the last user prompt (optionally into a fresh ``target`` conversation)."""
        from agentkit.session import last_user_prompt, load_history

        async with self.repositories() as repos:
            history = await load_history(repos, conversation_id, max_messages=10_000)
        prompt = last_user_prompt(history)
        if prompt is None:
            raise ValueError(f"conversation {conversation_id!r} has no user prompt to replay")
        text, index = prompt
        target = target or f"{conversation_id}:replay"
        async with self.repositories() as repos:
            await repos.conversations.fork(conversation_id, target, upto=index)
        return await self.run(text, conversation_id=target, approve=approve)

    def middlewares(self) -> list[Any]:
        return list(self._middlewares)

    def bind(self, name: str, factory: Any, *, singleton: bool = False) -> App:
        self.container.bind(name, factory, singleton=singleton)
        return self

    def make(self, name: Any) -> Any:
        provider = self._deferred.get(name)
        if provider is not None and not getattr(provider, "_ak_registered", False):
            self._apply_bindings(provider)
            provider.register(self)
            provider._ak_registered = True  # type: ignore[attr-defined]
        return self.container.make(name)

    def resolve(self, name: Any) -> Any:
        """Resolve a binding (alias for :meth:`make`, Laravel's ``resolve``)."""
        return self.make(name)

    # -- drivers / managers --------------------------------------------
    def manager(self, kind: str) -> Any:
        """The :class:`~agentkit.support.manager.Manager` for a subsystem ``kind``."""
        manager = self._managers.get(kind)
        if manager is None:
            from agentkit.support.manager import manager_class

            manager = manager_class(kind)(self)
            self._managers[kind] = manager
        return manager

    def extend(self, kind: str, name: str, factory: Any) -> App:
        """Register a custom ``kind`` driver (``app.extend("cache", "redis", fn)``)."""
        self.manager(kind).extend(name, factory)
        return self

    def drivers(self) -> dict[str, Any]:
        """Every registered kind's active driver and available alternatives."""
        from agentkit.support.manager import registered_managers

        view: dict[str, Any] = {}
        for kind in sorted(set(self._managers) | set(registered_managers())):
            manager = self.manager(kind)
            view[kind] = {
                "driver": manager.configured_driver(),
                "available": manager.available(),
            }
        return view

    def _apply_bindings(self, provider: Provider) -> None:
        for abstract, concrete in provider.bindings.items():
            self.container.bind(abstract, _binding_factory(concrete))
        for abstract, concrete in provider.singletons.items():
            self.container.singleton(abstract, _binding_factory(concrete))

    @property
    def db(self) -> Any:
        """The ``DB`` service (sessions/transactions/repositories) bound to this app."""
        return self.make("db")

    @property
    def cache(self) -> Any:
        """The configured cache driver (see the ``Cache`` facade; ``cache_driver``)."""
        if "cache" in self._fakes:
            return self._fakes["cache"]
        return self.manager("cache").driver()

    @property
    def storage(self) -> Any:
        """The configured file store (see the ``Storage`` facade; ``storage_driver``)."""
        if "storage" in self._fakes:
            return self._fakes["storage"]
        return self.manager("storage").driver()

    @property
    def notifier(self) -> Notifier:
        """The notifier; register channels with ``app.notifier.channel(name, sender)``."""
        if "notifier" in self._fakes:
            return self._fakes["notifier"]
        return self._notifier

    @property
    def credentials(self) -> Any:
        """The encrypted credential vault (or ``None`` when disabled)."""
        if not getattr(self.settings, "credentials_enabled", False):
            return None
        if self._credential_service is None:
            from agentkit.security.credentials import Credentials

            self._credential_service = Credentials(self.runtime)
        return self._credential_service

    @property
    def queue(self) -> Any:
        """The configured job queue driver (see the ``Queue`` facade; ``queue_driver``)."""
        if "queue" in self._fakes:
            return self._fakes["queue"]
        return self.manager("queue").driver()

    # -- test fakes -----------------------------------------------------
    def fake(self, name: str, fake: Any = None) -> Any:
        """Install (or read) a fake for a subsystem: ``queue``/``cache``/``storage``/``notifier``."""
        if fake is None:
            return self._fakes.get(name)
        self._fakes[name] = fake
        return fake

    def restore_fakes(self) -> None:
        """Drop every installed fake."""
        self._fakes.clear()

    @property
    def pricing(self) -> Any:
        """The configured price provider (``pricing_driver``, default ``genai``)."""
        return self.manager("pricing").driver()

    @property
    def ingest(self) -> Any:
        """The configured document loader (``ingest_driver``, default ``default``)."""
        return self.manager("ingest").driver()

    @property
    def speech(self) -> Any:
        """The configured speech driver (``audio_driver``, default ``openai``)."""
        return self.manager("audio").driver()

    @property
    def dialect(self) -> Any:
        """The configured DB dialect (``database_driver``, default ``sqlite``)."""
        return self.manager("database").driver()

    @property
    def tracer(self) -> Any:
        """The configured tracer driver (the ``observability`` setting)."""
        return self.manager("observability").driver()

    @property
    def guard(self) -> Any:
        """The configured guardrail scanner (``guardrails_driver``, default ``regex``)."""
        return self.manager("guardrails").driver()

    @property
    def limiter(self) -> Any:
        """The configured rate-limit driver (``rate_limit_driver``, default ``database``)."""
        return self.manager("ratelimit").driver()

    @property
    def durability(self) -> Any:
        """The configured durability driver (``durability_driver``, default ``dbos``)."""
        return self.manager("durability").driver()

    @property
    def vault(self) -> Any:
        """The configured secret vault (``vault_driver``, default ``fernet``)."""
        return self.manager("vault").driver()

    @property
    def auth(self) -> Any:
        """The configured auth strategy (``auth_driver``, default ``default``)."""
        return self.manager("auth").driver()

    @property
    def memory(self) -> Any:
        """The configured memory store (``memory_driver``, default ``repository``)."""
        return self.manager("memory").driver()

    @property
    def chunker(self) -> Any:
        """The configured RAG chunker (``chunker_driver``, default ``semantic``)."""
        return self.manager("chunker").driver()

    @property
    def retriever(self) -> Any:
        """The configured RAG retriever (``retriever_driver``, default ``repository``)."""
        return self.manager("retriever").driver()

    @property
    def reranker(self) -> Any:
        """The configured RAG reranker (``reranker_driver``, default ``identity``)."""
        return self.manager("reranker").driver()

    @property
    def search(self) -> Any:
        """The configured conversation search index (``search_driver``, default ``fts``)."""
        return self.manager("search").driver()

    @property
    def extractor(self) -> Any:
        """The configured learning extractor (``learning_extractor_driver``)."""
        return self.manager("learning_extractor").driver()

    @property
    def learning_strategy(self) -> Any:
        """The configured learning strategy (``learning_strategy_driver``)."""
        return self.manager("learning_strategy").driver()

    @property
    def learning_sink(self) -> Any:
        """The configured learning sink (``learning_sink_driver``)."""
        return self.manager("learning_sink").driver()

    @property
    def comms(self) -> Any:
        """The configured agent comms topology (``comms_driver``, default ``mailbox``)."""
        return self.manager("comms").driver()

    @property
    def speaker(self) -> Any:
        """The configured group-chat speaker strategy (``speaker_driver``)."""
        return self.manager("speaker").driver()

    @property
    def tasks(self) -> Any:
        """The configured task store (``tasks_driver``, default ``memory``)."""
        return self.manager("tasks").driver()

    @property
    def planning(self) -> Any:
        """The configured planning strategy (``planning_driver``, default ``single``)."""
        return self.manager("planning").driver()

    @property
    def context_strategy(self) -> Any:
        """The configured subagent context strategy (``context_driver``, default ``isolated``)."""
        return self.manager("context").driver()

    @property
    def agent_middleware(self) -> Any:
        """The configured agent middleware (``agent_middleware_driver``, default ``noop``)."""
        return self.manager("agent_middleware").driver()

    @property
    def graph_executor(self) -> Any:
        """The configured graph executor (``graph_driver``, default ``sequential``)."""
        return self.manager("graph").driver()

    @property
    def code_executor(self) -> Any:
        """The configured code executor (``code_executor_driver``, default ``local``)."""
        return self.manager("codeexec").driver()

    @property
    def eval_reporter(self) -> Any:
        """The configured eval reporter (``evals_reporter_driver``, default ``text``)."""
        return self.manager("evals_reporter").driver()

    def notify(self, notification: Any, *, to: Any = None, conversation_id: str | None = None) -> Any:
        """Send a :class:`~agentkit.foundation.notifications.Notification`."""
        return self.notifier.send(notification, to=to, conversation_id=conversation_id)

    def _deliver_result(self, conversation_id: str, text: str) -> None:
        """Deliver a scheduled task's result to the conversation that scheduled it.

        Best-effort: the scheduler calls this after a successful run; the channel
        is derived from the conversation prefix (``telegram``/``log`` when
        registered, else ``conversation`` — which writes into chat history).
        """
        if not conversation_id:
            return
        from agentkit.foundation.notifications import Notification

        prefix = conversation_id.split(":", 1)[0]
        channel = prefix if self._notifier.channel(prefix) is not None else "conversation"

        body = text or "(scheduled task finished)"

        class _ScheduledResult(Notification):
            channels = (channel,)

            def content(self) -> str:
                return body

        self.notify(_ScheduledResult(), to=[channel], conversation_id=conversation_id)

    async def dispatch(self, job: Any, *, queue: str | None = None) -> Any:
        """Run a job — a :class:`~agentkit.foundation.queue.Job` instance or class,
        or a plain callable (wrapped into a closure job).

        When ``queue_enabled`` is set the job is pushed onto the queue and returns
        its id (a worker processes it, e.g. ``agentkit queue:work``); otherwise it
        runs inline. Closure jobs always run inline (they are not serializable).
        """
        from agentkit.foundation.queue import ClosureJob

        if isinstance(job, type) and issubclass(job, Job):
            job = job()
        if callable(job) and not isinstance(job, Job):
            job = ClosureJob(job)
        if not isinstance(job, Job):
            raise TypeError("dispatch() expects a Job instance, Job class, or callable")
        if getattr(self.settings, "queue_enabled", False) and not isinstance(job, ClosureJob):
            return await self.queue.push(job, queue=queue)
        return await job.dispatch(self)

    # -- runtime / deps -------------------------------------------------
    @property
    def runtime(self) -> Runtime:
        if self._runtime is None:
            self._runtime = build_runtime(self.settings, repos_factory=self.repos_factory)
        return self._runtime

    def repositories(self, owner_id: str | None = None):
        return repositories(self.runtime, owner_id)

    def deps(
        self,
        repos: Any,
        *,
        approve: ApprovalCallback | None = None,
        context: Any = None,
        actor: Actor | None = None,
    ) -> Any:
        model = self._model
        if self._model_resolver is not None:
            model = self._model_resolver(context)
        if approve is None and getattr(self.settings, "approval_ui_enabled", False):
            approve = self.approvals.request
        deps = build_deps(
            self.runtime,
            repos,
            model=model or build_model(self.settings),
            mcp=self._mcp,
            a2a=self._a2a,
            approve=approve,
            actor=actor,
        )
        if self._credential_service is not None:
            deps.credentials = self._credential_service
        if self._clarify_handler is not None:
            deps.extras["clarify"] = self._clarify_handler
        deps.extras["app"] = self
        deps.extras.setdefault("posture", self.posture_name)
        deps.extras.setdefault("task_store", self.manager("tasks").driver())
        deps.extras.setdefault("code_executor", self.manager("codeexec").driver())
        return deps

    def _require_agent(self) -> Any:
        agent = self.agent()
        if agent is None:
            raise RuntimeError("no primary agent registered on the app")
        return agent

    def _make_recorder(self, run_id: str, repos: Any) -> Any:
        """A run-trace recorder for a turn (repository-backed when enabled)."""
        from agentkit.runs import recorder_for

        enabled = bool(getattr(self.settings, "run_trace_enabled", True))
        return recorder_for(repos, run_id or "run", enabled=enabled)

    def _make_checkpointer(self, repos: Any) -> Any:
        """A checkpoint store for a turn (over the live repos; off by default)."""
        if not bool(getattr(self.settings, "checkpoints_enabled", False)):
            return None
        from agentkit.checkpoints import checkpointer_for

        retention = int(getattr(self.settings, "checkpoint_retention", 50) or 50)
        return checkpointer_for(repos, enabled=True, retention=retention)

    # -- run / serve ----------------------------------------------------
    async def run(
        self,
        text: str,
        *,
        conversation_id: str = "cli:default",
        approve: ApprovalCallback | None = None,
        actor: Actor | None = None,
        ephemeral: bool = False,
    ) -> ChatResult:
        from agentkit.foundation.pipeline import Pipeline

        turn = Turn(conversation_id=conversation_id, text=text, approve=approve)
        owner_id = actor.owner_id if actor is not None else None

        async def destination(current: Turn) -> Turn:
            async with self.repositories(owner_id) as repos:
                if self._budget is not None:
                    from agentkit.limits import check_budget

                    await check_budget(repos, self._budget, conversation_id=current.conversation_id)
                runner = ChatRunner(
                    self.deps(repos, approve=current.approve, context=current, actor=actor),
                    agent=self._require_agent(),
                    conversation_id=current.conversation_id,
                    history_processor=self._history_processor,
                    persist=not ephemeral,
                    recorder=self._make_recorder(current.conversation_id, repos),
                    checkpointer=self._make_checkpointer(repos),
                )
                current.result = await runner.send(current.text)
            return current

        task = self._track(conversation_id)
        try:
            await Pipeline(self._middlewares).send(turn).then(destination)
        finally:
            self._untrack(conversation_id, task)
        assert turn.result is not None
        return turn.result

    async def stream(
        self,
        text: str,
        *,
        conversation_id: str = "cli:default",
        approve: ApprovalCallback | None = None,
        actor: Actor | None = None,
        ephemeral: bool = False,
    ) -> Any:
        """Stream one turn as :class:`~agentkit.session.StreamEvent` increments."""
        owner_id = actor.owner_id if actor is not None else None
        task = self._track(conversation_id)
        try:
            async with self.repositories(owner_id) as repos:
                if self._budget is not None:
                    from agentkit.limits import check_budget

                    await check_budget(repos, self._budget, conversation_id=conversation_id)
                runner = ChatRunner(
                    self.deps(repos, approve=approve, actor=actor),
                    agent=self._require_agent(),
                    conversation_id=conversation_id,
                    history_processor=self._history_processor,
                    persist=not ephemeral,
                    recorder=self._make_recorder(conversation_id, repos),
                    checkpointer=self._make_checkpointer(repos),
                )
                async for event in runner.stream(text):
                    yield event
        finally:
            self._untrack(conversation_id, task)

    async def resume(
        self,
        deferred_tool_results: Any,
        *,
        conversation_id: str = "cli:default",
        approve: ApprovalCallback | None = None,
        actor: Actor | None = None,
    ) -> ChatResult:
        """Resume a turn that deferred tool calls (approvals / clarification)."""
        owner_id = actor.owner_id if actor is not None else None
        task = self._track(conversation_id)
        try:
            async with self.repositories(owner_id) as repos:
                runner = ChatRunner(
                    self.deps(repos, approve=approve, actor=actor),
                    agent=self._require_agent(),
                    conversation_id=conversation_id,
                    history_processor=self._history_processor,
                    recorder=self._make_recorder(conversation_id, repos),
                    checkpointer=self._make_checkpointer(repos),
                )
                return await runner.resume(deferred_tool_results)
        finally:
            self._untrack(conversation_id, task)

    @property
    def answer(self) -> Any:
        """``(conversation_id, text, *, actor=None) -> ChatResult`` for webui/a2a/mcp."""

        async def run_answer(
            conversation_id: str,
            text: str,
            *,
            actor: Actor | None = None,
            ephemeral: bool = False,
        ) -> ChatResult:
            return await self.run(
                text, conversation_id=conversation_id, actor=actor, ephemeral=ephemeral
            )

        return run_answer

    def channel_services(self) -> list[Any]:
        from agentkit.foundation.channels import Channel
        from agentkit.supervise import Service

        services: list[Service] = []
        for spec in self._channels.values():
            factory = spec.factory
            if factory is None:
                continue
            if isinstance(factory, str):
                factory = self.container.wrap(factory, protocol="channel")
            if isinstance(factory, type) and issubclass(factory, Channel):
                produced = factory(self).services(self)
            elif isinstance(factory, Channel):
                produced = factory.services(self)
            elif callable(factory):
                produced = factory(self)
            else:  # pragma: no cover - defensive
                produced = getattr(factory, "services", lambda app: None)(self)
            services.extend(_as_services(spec.name, produced))
        return services

    def serve(
        self,
        *,
        stop_event: Any = None,
        webui: bool | None = None,
    ) -> None:
        """Boot then run every channel service (plus the web UI) until shutdown."""
        self.boot()
        from agentkit.supervise import run_all

        use_webui = self.settings.webui_enabled if webui is None else webui
        run_all(
            self.channel_services(),
            stop_event=stop_event,
            settings=self.settings,
            runtime=self.runtime,
            webui_answer=self.answer,
            webui=use_webui,
            app=self,
        )

    # -- internals ------------------------------------------------------
    def _bind_facades(self) -> None:
        from agentkit.foundation.gate import Gate as GateManager

        self.container.instance("app", self)
        self.container.instance(type(self), self)
        self.container.instance("memory", MemoryService(self))
        self.container.instance("schedule", ScheduleService(self))
        self.container.instance("db", DBService(self))
        self.container.instance("events", EventsService(self))
        self.container.instance("log", LogService(self))
        self.container.instance("feedback", FeedbackService(self))
        self.container.instance("cache", CacheService(self))
        self.container.instance("storage", StorageService(self))
        self.container.instance("queue", QueueService(self))
        self.container.instance("gate", GateManager(self))

    @property
    def gate(self) -> Any:
        """The app's authorization :class:`~agentkit.foundation.gate.Gate`."""
        return self.make("gate")


#: ``Application`` is the canonical container name; ``App`` stays as an alias.
Application = App


class ApplicationBuilder:
    """Fluent assembly for an :class:`App` (see :meth:`App.configure`).

    Convention discovery of ``app/`` and ``config/`` runs in :meth:`create`; a
    provider/agent/channel/command passed explicitly to a ``with*`` method always
    wins over the discovered one.
    """

    def __init__(
        self,
        name: str | None = None,
        settings: AgentSettings | type[AgentSettings] | None = None,
        base_path: str | Path | None = None,
        *,
        discover: bool = True,
        repos_factory: type[Repositories] | None = None,
        model: Any = None,
        mcp: Any = None,
        a2a: Any = None,
    ) -> None:
        self.name = name
        self.settings = settings
        self.base_path = Path(base_path).expanduser() if base_path is not None else Path.cwd()
        self.discover = discover
        self.repos_factory = repos_factory
        self.model = model
        self.mcp = mcp
        self.a2a = a2a
        self._providers: list[Any] = []
        self._config: dict[str, Any] = {}
        self._agents: list[Any] = []
        self._channels: dict[str, Any] = {}
        self._commands: list[Any] = []
        self._posture: Any = None

    def withProviders(self, *providers: Any) -> ApplicationBuilder:
        for provider in providers:
            if isinstance(provider, (list, tuple)):
                self._providers.extend(provider)
            else:
                self._providers.append(provider)
        return self

    def withConfig(
        self, sections: Mapping[str, Any] | None = None, **kwargs: Any
    ) -> ApplicationBuilder:
        if sections:
            self._config.update(sections)
        self._config.update(kwargs)
        return self

    def withAgents(self, *agents: Any) -> ApplicationBuilder:
        self._agents.extend(agents)
        return self

    def withChannels(
        self, channels: Mapping[str, Any] | None = None, **kwargs: Any
    ) -> ApplicationBuilder:
        if channels:
            self._channels.update(channels)
        self._channels.update(kwargs)
        return self

    def withCommands(self, *commands: Any) -> ApplicationBuilder:
        self._commands.extend(commands)
        return self

    def withPosture(self, name: Any) -> ApplicationBuilder:
        self._posture = name
        return self

    def withBasePath(self, path: str | Path) -> ApplicationBuilder:
        self.base_path = Path(path).expanduser()
        return self

    def create(self) -> App:
        """Build the :class:`App`, running convention discovery here (at boot)."""
        from agentkit.foundation import discovery

        repos_factory = self.repos_factory
        if repos_factory is None and self.discover:
            repos_factory = discovery.discover_repositories(self.base_path)
        kwargs: dict[str, Any] = {"discover": True}
        if repos_factory is not None:
            kwargs["repos_factory"] = repos_factory
        if self.model is not None:
            kwargs["model"] = self.model
        if self.mcp is not None:
            kwargs["mcp"] = self.mcp
        if self.a2a is not None:
            kwargs["a2a"] = self.a2a
        app = App(name=self._resolved_name(), settings=self.settings, **kwargs)
        if self._posture is not None:
            app.posture(self._posture)
        if self.discover:
            self._discover_into(app)
        # Explicit declarations win over discovered ones (registered last).
        app.providers(self._providers)
        for builder in self._agents:
            app.agent(builder)
        for name, factory in self._channels.items():
            app.channel(name, factory)
        app.commands(self._commands)
        for section, schema in self._config.items():
            app.config(section, schema)
        return app

    def _resolved_name(self) -> str | None:
        if self.name is not None:
            return self.name
        settings = self.settings() if isinstance(self.settings, type) else self.settings
        if settings is None or not hasattr(settings, "agent_name"):
            return None
        return getattr(settings, "agent_name", None)

    def _discover_into(self, app: App) -> None:
        from agentkit.foundation import discovery

        app.providers(discovery.discover_providers(self.base_path))
        for definition in discovery.discover_agents(self.base_path):
            app.agent(definition.to_builder(settings=app.settings, events=app.events))
        for name, factory in discovery.discover_channels(self.base_path):
            app.channel(name, factory)
        app.commands(discovery.discover_commands(self.base_path))
        listeners = discovery.discover_listeners(self.base_path)
        if listeners:
            app.listeners(listeners)
        policies = discovery.discover_policies(self.base_path)
        if policies:
            app.policies(policies)
        for section, schema in discovery.discover_config(self.base_path).items():
            app.config(section, schema)


class ChannelSpec:
    """A registered channel: its factory and any options."""

    def __init__(self, name: str, factory: Any = None, options: dict[str, Any] | None = None) -> None:
        self.name = name
        self.factory = factory
        self.options = options or {}

    def __repr__(self) -> str:
        return f"ChannelSpec({self.name!r})"


@dataclass
class Turn:
    """One chat turn as it flows through the middleware pipeline."""

    conversation_id: str
    text: str
    approve: Any = None
    result: Any = None
    extras: dict[str, Any] = field(default_factory=dict)


def _command_name(command: Any) -> str:
    name = getattr(command, "name", None)
    if name:
        return str(name)
    if hasattr(command, "command_name"):
        try:
            return str(command.command_name())
        except Exception:  # pragma: no cover - defensive
            pass
    return type(command).__name__


def _binding_factory(concrete: Any) -> Any:
    """A container factory for a provider binding (a class is built/autowired)."""
    if isinstance(concrete, type):
        return lambda container, cls=concrete: container.build(cls)
    return concrete


def _spec_fields(spec: Any) -> dict[str, Any]:
    names = ("name", "task", "args", "cron", "when", "at", "enabled")
    fields = {name: getattr(spec, name) for name in names if hasattr(spec, name)}
    if "name" not in fields or "task" not in fields:
        raise ValueError(f"schedule {spec!r} must define 'name' and 'task'")
    return fields


def _as_services(name: str, produced: Any) -> list[Any]:
    from agentkit.supervise import Service

    if produced is None:
        return []
    if isinstance(produced, Service):
        return [produced]
    if isinstance(produced, (list, tuple)):
        services: list[Any] = []
        for item in produced:
            services.extend(_as_services(name, item))
        return services
    if callable(produced):
        return [Service(name, produced)]
    raise TypeError(f"channel {name!r} factory returned {type(produced)!r}")


__all__ = [
    "App",
    "Application",
    "ApplicationBuilder",
    "ChannelSpec",
    "PROVIDER_ENTRY_POINT_GROUP",
    "discover_providers",
]
