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

import json
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
from agentkit.foundation.jobs import CacheStore
from agentkit.foundation.notifications import Notifier
from agentkit.foundation.provider import Provider
from agentkit.foundation.queue import Job, Queue
from agentkit.foundation.schedule import ScheduleBuilder
from agentkit.foundation.storage import Filesystem
from agentkit.logging import get_logger
from agentkit.runtime import Runtime, build_deps, build_runtime, repositories
from agentkit.session import ChatResult, ChatRunner

log = get_logger("agentkit.app")

PROVIDER_ENTRY_POINT_GROUP = "agentkit.providers"


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
        self._cache = CacheStore()
        self._notifier = Notifier(self)
        self._storage: Filesystem | None = None
        self._queue: Queue | None = None

        self.container.instance("app", self)
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
        with self.repositories() as repos:
            if cron:
                repos.schedules.upsert(
                    name,
                    kind="cron",
                    schedule=cron,
                    task=task,
                    args=json.dumps(args or {}),
                    enabled=fields.get("enabled", True),
                )
            elif when:
                dot = when if isinstance(when, str) else when.isoformat()
                repos.schedules.upsert(
                    name, kind="once", schedule=dot, task=task, args=json.dumps(args or {})
                )
            else:
                raise ValueError(f"schedule {name!r} needs a 'cron' or 'when' field")

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

    def models(self, resolver: Any) -> App:
        """Alias for :meth:`model_resolver`."""
        return self.model_resolver(resolver)

    def clarify(self, handler: Any) -> App:
        """Set a ``handler(question, options) -> str`` for the ``ask_user`` tool."""
        self._clarify_handler = handler
        return self

    def budget(self, budget: Any) -> App:
        """Enforce a :class:`~agentkit.limits.Budget` before each turn."""
        self._budget = budget
        return self

    def fork(self, source: str, target: str, *, upto: int | None = None) -> int:
        """Copy a conversation's messages into ``target`` (branching)."""
        with self.repositories() as repos:
            return repos.conversations.fork(source, target, upto=upto)

    async def replay(
        self,
        conversation_id: str,
        *,
        target: str | None = None,
        approve: ApprovalCallback | None = None,
    ) -> ChatResult:
        """Re-run the last user prompt (optionally into a fresh ``target`` conversation)."""
        from agentkit.session import last_user_prompt, load_history

        with self.repositories() as repos:
            history = load_history(repos, conversation_id, max_messages=10_000)
        prompt = last_user_prompt(history)
        if prompt is None:
            raise ValueError(f"conversation {conversation_id!r} has no user prompt to replay")
        text, index = prompt
        target = target or f"{conversation_id}:replay"
        with self.repositories() as repos:
            repos.conversations.fork(conversation_id, target, upto=index)
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
    def cache(self) -> CacheStore:
        """The in-process cache store (see the ``Cache`` facade)."""
        return self._cache

    @property
    def storage(self) -> Filesystem:
        """The agent's file store under ``<agent_home>/storage``."""
        if self._storage is None:
            self._storage = Filesystem(self.settings.home / "storage")
        return self._storage

    @property
    def notifier(self) -> Notifier:
        """The notifier; register channels with ``app.notifier.channel(name, sender)``."""
        return self._notifier

    @property
    def queue(self) -> Queue:
        """The database-backed job queue (see the ``Queue`` facade)."""
        if self._queue is None:
            self._queue = Queue(self)
        return self._queue

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
            return self.queue.push(job, queue=queue)
        return await job.dispatch(self)

    # -- runtime / deps -------------------------------------------------
    @property
    def runtime(self) -> Runtime:
        if self._runtime is None:
            self._runtime = build_runtime(self.settings, repos_factory=self.repos_factory)
        return self._runtime

    def repositories(self):
        return repositories(self.runtime)

    def deps(
        self, repos: Any, *, approve: ApprovalCallback | None = None, context: Any = None
    ) -> Any:
        model = self._model
        if self._model_resolver is not None:
            model = self._model_resolver(context)
        deps = build_deps(
            self.runtime,
            repos,
            model=model or build_model(self.settings),
            mcp=self._mcp,
            a2a=self._a2a,
            approve=approve,
        )
        if self._clarify_handler is not None:
            deps.extras["clarify"] = self._clarify_handler
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
    ) -> ChatResult:
        from agentkit.foundation.pipeline import Pipeline

        turn = Turn(conversation_id=conversation_id, text=text, approve=approve)

        async def destination(current: Turn) -> Turn:
            with self.repositories() as repos:
                if self._budget is not None:
                    from agentkit.limits import check_budget

                    check_budget(repos, self._budget, conversation_id=current.conversation_id)
                runner = ChatRunner(
                    self.deps(repos, approve=current.approve, context=current),
                    agent=self._require_agent(),
                    conversation_id=current.conversation_id,
                    history_processor=self._history_processor,
                )
                current.result = await runner.send(current.text)
            return current

        await Pipeline(self._middlewares).send(turn).then(destination)
        assert turn.result is not None
        return turn.result

    async def stream(
        self,
        text: str,
        *,
        conversation_id: str = "cli:default",
        approve: ApprovalCallback | None = None,
    ) -> Any:
        """Stream one turn as :class:`~agentkit.session.StreamEvent` increments."""
        with self.repositories() as repos:
            if self._budget is not None:
                from agentkit.limits import check_budget

                check_budget(repos, self._budget, conversation_id=conversation_id)
            runner = ChatRunner(
                self.deps(repos, approve=approve),
                agent=self._require_agent(),
                conversation_id=conversation_id,
                history_processor=self._history_processor,
            )
            async for event in runner.stream(text):
                yield event

    async def resume(
        self,
        deferred_tool_results: Any,
        *,
        conversation_id: str = "cli:default",
        approve: ApprovalCallback | None = None,
    ) -> ChatResult:
        """Resume a turn that deferred tool calls (approvals / clarification)."""
        with self.repositories() as repos:
            runner = ChatRunner(
                self.deps(repos, approve=approve),
                agent=self._require_agent(),
                conversation_id=conversation_id,
                history_processor=self._history_processor,
            )
            return await runner.resume(deferred_tool_results)

    @property
    def answer(self) -> Any:
        """``(conversation_id, text) -> ChatResult`` for webui/a2a/mcp."""

        async def run_answer(conversation_id: str, text: str) -> ChatResult:
            return await self.run(text, conversation_id=conversation_id)

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
