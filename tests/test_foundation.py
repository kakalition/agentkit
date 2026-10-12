from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest
from pydantic_ai import Agent as PydanticAgent
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agentkit.app import AgentApp
from agentkit.deps import Deps
from agentkit.foundation import (
    Agent,
    App,
    Container,
    Dispatcher,
    Event,
    Facade,
    Pipeline,
    Provider,
    Section,
    current_app,
    discover_providers,
)
from agentkit.foundation.container import BindingError
from agentkit.foundation.facade import using
from agentkit.foundation.facades import DB, Events, Log, Memory
from agentkit.runtime import Runtime
from agentkit.supervise import Service, run_all


def _app(runtime: Runtime, **kwargs) -> App:
    app = App(name="test", settings=runtime.settings, discover=False, **kwargs)
    app._runtime = runtime
    app.boot()
    return app


# -- container --------------------------------------------------------------
def test_container_bind_singleton_and_instance():
    container = Container()
    container.bind("greeting", lambda c: "hello")
    assert container.bound("greeting")
    assert container.make("greeting") == "hello"

    calls: list[int] = []
    container.singleton("counter", lambda c: calls.append(1) or object())
    first = container.make("counter")
    assert container.make("counter") is first
    assert calls == [1]

    marker = object()
    container.instance("marker", marker)
    assert container.make("marker") is marker

    container.forget("greeting")
    assert not container.bound("greeting")
    with pytest.raises(BindingError):
        container.make("greeting")


def test_container_bind_non_singleton_rebuilds():
    container = Container()
    container.bind("thing", lambda c: object())
    assert container.make("thing") is not container.make("thing")


# -- providers --------------------------------------------------------------
def test_provider_lifecycle_order_all_register_then_all_boot():
    order: list[str] = []

    class First(Provider):
        def register(self, app):  # noqa: ANN001
            order.append("register:first")

        def boot(self, app):  # noqa: ANN001
            order.append("boot:first")

    class Second(Provider):
        def register(self, app):  # noqa: ANN001
            order.append("register:second")

        def boot(self, app):  # noqa: ANN001
            order.append("boot:second")

    app = App(discover=False)
    app.providers([First, Second])
    app.boot()
    assert order == ["register:first", "register:second", "boot:first", "boot:second"]


def test_boot_is_idempotent():
    order: list[str] = []

    class Once(Provider):
        def boot(self, app):  # noqa: ANN001
            order.append("boot")

    app = App(discover=False)
    app.providers([Once])
    app.boot()
    app.boot()
    assert order == ["boot"]


def test_provider_contributes_commands_and_schedules():
    class WithExtras(Provider):
        def commands(self):
            return ["cmd"]

        def schedules(self):
            return ["sched"]

    app = App(discover=False)
    app.providers([WithExtras])
    app.boot()
    assert "cmd" in app._commands
    assert app._schedules == ["sched"]


def test_discovery_loads_and_wraps_failures(monkeypatch):
    class Good(Provider):
        pass

    class FakeEntryPoint:
        def __init__(self, name, loader):
            self.name = name
            self._loader = loader

        def load(self):
            return self._loader()

    def _boom():
        raise ImportError("nope")

    monkeypatch.setattr(
        "agentkit.foundation.application.entry_points",
        lambda group: [FakeEntryPoint("good", lambda: Good), FakeEntryPoint("bad", _boom)],
    )
    providers = discover_providers()
    assert providers == [Good]


# -- events -----------------------------------------------------------------
def test_events_dispatch_order_and_wildcard():
    dispatcher = Dispatcher()
    seen: list[str] = []
    dispatcher.listen("turn.end", lambda event: seen.append(event.conversation_id))
    dispatcher.listen("*", lambda event: seen.append("wild"))
    dispatcher.dispatch("turn.end", conversation_id="cli:1")
    assert seen == ["cli:1", "wild"]


def test_events_event_attribute_access_and_defaults():
    event = Event("x", payload={"a": 1})
    assert event.a == 1
    assert event.get("missing", 7) == 7
    with pytest.raises(AttributeError):
        _ = event.nope


def test_events_sync_dispatch_rejects_async_listener():
    dispatcher = Dispatcher()

    async def listener(event):  # noqa: ANN001
        return None

    dispatcher.listen("x", listener)
    with pytest.raises(RuntimeError):
        dispatcher.dispatch("x")


async def test_events_async_dispatch_awaits_listeners():
    dispatcher = Dispatcher()
    seen: list[str] = []

    async def listener(event):  # noqa: ANN001
        seen.append("async")

    dispatcher.listen("x", listener)
    await dispatcher.dispatch_async("x")
    assert seen == ["async"]


# -- pipeline ---------------------------------------------------------------
async def test_pipeline_order_and_short_circuit():
    calls: list[str] = []

    def middleware(name: str):
        async def run(passable, call_next):  # noqa: ANN001
            calls.append(f"before:{name}")
            result = await call_next(passable)
            calls.append(f"after:{name}")
            return result

        return run

    async def destination(value):  # noqa: ANN001
        calls.append("dest")
        return value * 2

    result = await Pipeline().send(3).through(middleware("a"), middleware("b")).then(destination)
    assert result == 6
    assert calls == ["before:a", "before:b", "dest", "after:b", "after:a"]


async def test_pipeline_middleware_can_short_circuit():
    async def blocker(passable, call_next):  # noqa: ANN001
        return "blocked"

    async def destination(value):  # noqa: ANN001
        raise AssertionError("should not run")

    assert await Pipeline().send(1).through(blocker).then(destination) == "blocked"


# -- facades ----------------------------------------------------------------
async def test_memory_facade(runtime: Runtime):
    _app(runtime)
    memory_id = await Memory.remember("My name is Ada")
    assert isinstance(memory_id, int)
    assert any("Ada" in row.content for row in Memory.search("Ada"))
    assert Memory.all()
    assert Memory.forget(memory_id) is True
    assert Memory.forget(memory_id) is False


def test_events_and_log_facades(runtime: Runtime):
    _app(runtime)
    seen: list[str] = []
    Events.listen("ping", lambda event: seen.append("pong"))
    Events.dispatch("ping")
    assert seen == ["pong"]
    assert Log.channel("agentkit").name == "agentkit"


def test_db_facade_session_and_transaction(runtime: Runtime):
    _app(runtime)
    with DB.transaction() as repos:
        repos.memories.add("via transaction")
    with DB.session() as session:
        assert session is not None
    assert any("transaction" in row.content for row in Memory.all())


def test_facade_using_scopes_current_app(runtime: Runtime):
    app = _app(runtime)
    with using(app):
        assert current_app() is app
    with Memory.using(app):
        assert current_app() is app


def test_current_app_raises_without_app():
    with using(None), pytest.raises(RuntimeError):
        current_app()


def test_facades_reach_worker_threads(runtime: Runtime):
    app = _app(runtime)
    seen: dict[str, object] = {}
    stop = threading.Event()

    def worker() -> None:
        seen["name"] = current_app().name
        seen["memory_id"] = asyncio.run(Memory.remember("from a thread"))
        stop.set()

    run_all([Service("worker", worker)], stop_event=stop, app=app, webui=False)
    assert seen["name"] == "test"
    assert isinstance(seen["memory_id"], int)


# -- agent builder ----------------------------------------------------------
def _tool_names(agent) -> set[str]:  # noqa: ANN001
    return set(agent._function_toolset.tools.keys())


def test_agent_builder_matches_hand_built_agent():
    from agentkit.orchestrator import make_delegate

    def echo(ctx: RunContext[Deps], text: str) -> str:
        """Echo text back."""
        return text

    specialist = PydanticAgent(
        FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("s")])),
        output_type=str,
        name="spec",
    )

    builder = (
        Agent.make("demo")
        .persona(text="PERSONA")
        .instructions("ROUTING")
        .tool(echo)
        .specialist(specialist, name="handle_spec", description="delegate to spec")
        .output(str)
    )
    built = builder.build()

    hand = PydanticAgent(
        FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("h")])),
        output_type=str,
        instructions="PERSONA\n\nROUTING",
        deps_type=Deps,
    )
    hand.tool(echo)
    hand.tool(make_delegate(specialist, tool_name="handle_spec", description="delegate to spec"))
    assert {"echo", "handle_spec"} == _tool_names(built)
    assert _tool_names(built) == _tool_names(hand)


async def test_agent_builder_persona_reads_live_soul(runtime: Runtime):
    def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        captured["instructions"] = info.instructions
        return ModelResponse(parts=[TextPart("ok")])

    captured: dict[str, object] = {}
    builder = Agent.make("demo").persona().instructions("ROUTING").output(str)
    built = builder.build(settings=runtime.settings)
    deps = Deps(settings=runtime.settings, repos=None)
    deps.model = FunctionModel(model_fn)
    await built.run("hi", deps=deps, model=deps.model)
    text = str(captured["instructions"])
    assert runtime.settings.agent_name in text or text
    assert "ROUTING" in text


def test_agent_builder_memory_attaches_tools():
    built = Agent.make("demo").memory().build()
    assert {"remember", "recall", "forget_memory"} <= _tool_names(built)


# -- app run/answer ---------------------------------------------------------
async def test_app_runs_builder_agent(runtime: Runtime):
    model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("hi there")]))
    app = _app(runtime, model=model)
    builder = Agent.make("demo").instructions("x").output(str)
    app.agent(builder)
    result = await app.run("hello")
    assert result.output == "hi there"
    assert result.history_length == 2
    assert (await app.answer("cli:default", "again")).output == "hi there"


async def test_app_run_sets_current_app_via_boot(runtime: Runtime):
    model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("ok")]))
    app = App(name="runner", settings=runtime.settings, discover=False, model=model)
    app._runtime = runtime
    app.agent(Agent.make("runner").instructions("x").output(str))
    app.boot()
    assert current_app() is app


# -- config -----------------------------------------------------------------
class DemoSection(Section):
    env_prefix = "AGENTKIT_DEMO_"
    enabled: bool = True
    retries: int = 3


def test_config_precedence_defaults_file_env(monkeypatch, tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "demo.py").write_text("config = {'enabled': False, 'retries': 5}\n")
    monkeypatch.setenv("AGENTKIT_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("AGENTKIT_DEMO_RETRIES", "9")
    app = App(discover=False)
    app.config("demo", DemoSection)
    section = app.config("demo")
    assert section.enabled is False  # file beat the default
    assert section.retries == 9  # env beat the file


def test_config_missing_returns_none():
    app = App(discover=False)
    assert app.config("nope") is None


# -- AgentApp shim ----------------------------------------------------------
async def test_agent_app_shim_delegates_to_app(runtime: Runtime):
    model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("legacy")]))
    agent = PydanticAgent(model, output_type=str)
    with pytest.warns(DeprecationWarning):
        legacy = AgentApp.build(agent=agent, settings=runtime.settings, model=model)
    legacy._app._runtime = runtime
    legacy.runtime = runtime
    assert isinstance(legacy.app, App)
    result = await legacy.run("hello")
    assert result.output == "legacy"


def test_facade_binding_requires_definition():
    class Broken(Facade):
        pass

    with pytest.raises(NotImplementedError):
        Broken.binding()
