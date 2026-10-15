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
from typing import Any

from agentkit.config import AgentSettings, build_model, get_settings
from agentkit.db.repositories import Repositories
from agentkit.deps import ApprovalCallback
from agentkit.foundation.agent import Agent as AgentBuilder
from agentkit.foundation.container import Container
from agentkit.foundation.events import Dispatcher
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
    "agentkit.foundation.agent_middleware",  # agent middleware
    "agentkit.graph",  # graph executors
    "agentkit.executors",  # code executors
    "agentkit.evals",  # eval reporters
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

        self.container.instance("app", self)
        _load_builtin_drivers()
        self._bind_facades()
        if discover:
            self._providers.extend(discover_providers())

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

    def boot(self) -> App:
        """Run the register/boot lifecycle once (idempotent)."""
        if self._booted:
            return self
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
            contributed = provider.schedules()
            if contributed:
                self.schedules(contributed)

        for provider in instances:
            if provider.provides():
                continue
            provider.boot(self)

        self._apply_schedules()

        self._booted = True
        set_current_app(self)
        self.events.dispatch("boot", app=self)
        return self

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
        if self._agent_builder is not None:
            self._agent_builder.tool(function, requires_approval=requires_approval)
        elif self._agent is not None:
            if requires_approval:
                self._agent.tool(function, requires_approval=True)
            else:
                self._agent.tool(function)
        else:
            self._pending_tools.append((function, requires_approval))
        return self

    # -- registries -----------------------------------------------------
    def channel(self, name: str, factory: Any = None, **options: Any) -> App:
        """Register a channel factory: ``factory(app) -> Service | list[Service]``."""
        self._channels[name] = ChannelSpec(name=name, factory=factory, options=options)
        return self

    def channels(self) -> dict[str, ChannelSpec]:
        return dict(self._channels)

    def commands(self, commands: Any) -> App:
        if isinstance(commands, dict):
            self._commands.update(commands)
        else:
            for command in commands:
                if isinstance(command, str):
                    self._commands[command] = command
                    continue
                name = getattr(command, "name", None) or type(command).__name__
                self._commands[name] = command
        return self

    def command(self, command: Any) -> App:
        return self.commands([command])

    def command_names(self) -> list[str]:
        return sorted(self._commands)

    def install_commands(self, typer_app: Any) -> None:
        """Register provider-contributed commands onto a Typer app."""
        from agentkit.foundation.commands import install

        commands = [c for c in self._commands.values() if not isinstance(c, str)]
        install(typer_app, commands)

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
    def on(self, event: str, listener: Any) -> App:
        self.events.listen(event, listener)
        return self

    def middleware(self, middleware: Any) -> App:
        self._middlewares.append(middleware)
        return self

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
        return self.manager("cache").driver()

    @property
    def storage(self) -> Any:
        """The configured file store (see the ``Storage`` facade; ``storage_driver``)."""
        return self.manager("storage").driver()

    @property
    def notifier(self) -> Notifier:
        """The notifier; register channels with ``app.notifier.channel(name, sender)``."""
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
        return self.manager("queue").driver()

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
        return self._notifier.send(notification, to=to, conversation_id=conversation_id)

    async def dispatch(self, job: Any, *, queue: str | None = None) -> Any:
        """Run a :class:`~agentkit.foundation.queue.Job`.

        When ``queue_enabled`` is set the job is pushed onto the queue and returns
        its id (a worker processes it, e.g. ``agentkit queue:work``); otherwise it
        runs inline. With durability initialised, inline work is a durable workflow.
        """
        if not isinstance(job, Job):
            raise TypeError("dispatch() expects a Job instance")
        if getattr(self.settings, "queue_enabled", False):
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
        deps.extras.setdefault("task_store", self.manager("tasks").driver())
        deps.extras.setdefault("code_executor", self.manager("codeexec").driver())
        return deps

    def _require_agent(self) -> Any:
        agent = self.agent()
        if agent is None:
            raise RuntimeError("no primary agent registered on the app")
        return agent

    # -- run / serve ----------------------------------------------------
    async def run(
        self,
        text: str,
        *,
        conversation_id: str = "cli:default",
        approve: ApprovalCallback | None = None,
        actor: Actor | None = None,
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
                )
                return await runner.resume(deferred_tool_results)
        finally:
            self._untrack(conversation_id, task)

    @property
    def answer(self) -> Any:
        """``(conversation_id, text, *, actor=None) -> ChatResult`` for webui/a2a/mcp."""

        async def run_answer(
            conversation_id: str, text: str, *, actor: Actor | None = None
        ) -> ChatResult:
            return await self.run(text, conversation_id=conversation_id, actor=actor)

        return run_answer

    def channel_services(self) -> list[Any]:
        from agentkit.supervise import Service

        services: list[Service] = []
        for spec in self._channels.values():
            if spec.factory is None:
                continue
            services.extend(_as_services(spec.name, spec.factory(self)))
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
        self.container.instance("memory", MemoryService(self))
        self.container.instance("schedule", ScheduleService(self))
        self.container.instance("db", DBService(self))
        self.container.instance("events", EventsService(self))
        self.container.instance("log", LogService(self))
        self.container.instance("feedback", FeedbackService(self))
        self.container.instance("cache", CacheService(self))
        self.container.instance("storage", StorageService(self))
        self.container.instance("queue", QueueService(self))


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


__all__ = ["App", "ChannelSpec", "PROVIDER_ENTRY_POINT_GROUP", "discover_providers"]
