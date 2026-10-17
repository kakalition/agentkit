"""Duality parity — every seam accepts both a class form and a functional form.

WS8 of the class/functional duality plan: for each seam, the closure/function
form and the class form must behave identically, and the documented examples
(``app.on(...)``, ``.tool(ToolClass)``, ``attach_*``, callable drivers) must run.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel

import agentkit.toolkits as _toolkits_pkg
from agentkit import (
    Agent,
    AgentDefinition,
    App,
    Channel,
    Command,
    Container,
    Event,
    Listener,
    Middleware,
    Provider,
    Rule,
    Tool,
    Toolkit,
    TurnEnded,
    ValidationRule,
    Validator,
)
from agentkit.foundation.container import BindingError
from agentkit.foundation.jobs import NullCacheStore
from agentkit.foundation.pipeline import MiddlewareGroup
from agentkit.foundation.signature import ParsedInput
from agentkit.runtime import Runtime
from agentkit.supervise import Service
from agentkit.support import Driver, register_driver
from agentkit.support.drivers import register, resolve, unregister
from agentkit.toolkits import UsageToolkit, attach_usage


def _app(runtime: Runtime, name: str = "duality") -> App:
    app = App(name=name, settings=runtime.settings, discover=False)
    app._runtime = runtime
    app.boot()
    return app


# -- WS0: shared normalization layer ----------------------------------------
class _Dep:
    pass


def test_container_call_injects_typed_params() -> None:
    container = Container()
    container.instance(App, "the-app")

    def handler(dep: _Dep, app: App, name: str = "x") -> tuple[_Dep, Any, str]:
        return dep, app, name

    dep, app, name = container.call(handler)
    assert isinstance(dep, _Dep)
    assert app == "the-app"
    assert name == "x"


def test_container_call_explicit_params_win() -> None:
    container = Container()

    def handler(dep: _Dep, name: str = "x") -> str:
        return name

    assert container.call(handler, {"name": "explicit"}) == "explicit"
    assert container.call(handler, name="kw") == "kw"


def test_container_call_raises_when_unresolvable() -> None:
    class _NeedsArg:
        def __init__(self, required):  # noqa: ANN001
            self.required = required

    container = Container()

    def handler(thing: _NeedsArg) -> Any:
        return thing

    with pytest.raises(BindingError):
        container.call(handler)


def test_normalize_forms() -> None:
    from agentkit.foundation.callable import normalize

    closure = normalize(lambda ev: None, protocol="listener")
    assert closure.origin == "closure" and callable(closure.invocable)

    class SimpleListener(Listener):
        def handle(self, event: Event) -> None:  # noqa: ARG002
            return None

    from_class = normalize(SimpleListener, protocol="listener")
    assert from_class.origin == "class"
    assert isinstance(from_class.invocable, SimpleListener)

    instance = SimpleListener()
    from_instance = normalize(instance, protocol="listener")
    assert from_instance.invocable is instance

    from_string = normalize("agentkit.foundation.events:should_queue")
    assert callable(from_string.invocable)

    bad = normalize("not-a-module:attr")
    assert bad.invocable is None


def test_container_wrap_listener_class_instantiates() -> None:
    class Wrapped(Listener):
        def handle(self, event: Event) -> None:  # noqa: ARG002
            return None

    wrapped = Container().wrap(Wrapped, protocol="listener")
    assert isinstance(wrapped, Wrapped)


# -- WS1: events & listeners ------------------------------------------------
def test_app_on_closure_and_listeners_class_same_event() -> None:
    app = App(name="ev", discover=False)
    seen: list[str] = []
    app.on("turn.end", lambda ev: seen.append(f"closure:{ev.get('conversation_id')}"))

    class Recording(Listener):
        event = TurnEnded

        def handle(self, event: Event) -> None:
            seen.append("class")

    app.listeners([Recording])
    app.events.dispatch(TurnEnded(app=app, payload={"conversation_id": "c1"}))
    assert seen == ["closure:c1", "class"]


def test_app_on_wildcard_and_chaining() -> None:
    app = App(name="ev", discover=False)
    seen: list[str] = []
    assert app.on("*", lambda ev: seen.append(ev.name)) is app
    app.events.dispatch("anything.happened")
    assert seen == ["anything.happened"]


# -- WS2: tools & toolkits --------------------------------------------------
class EchoTool(Tool):
    name = "echo"
    description = "Echo the text back."

    def handle(self, ctx: RunContext[Any], text: str) -> str:  # noqa: ARG002
        return f"echo:{text}"


def _echo_function(ctx: RunContext[Any], text: str) -> str:  # noqa: ARG001
    return f"echo:{text}"


def test_tool_function_class_instance_parity() -> None:
    by_function = Agent.make("a").tool(_echo_function)
    by_class = Agent.make("a").tool(EchoTool)
    by_instance = Agent.make("a").tool(EchoTool())

    results = {builder._tools[0][0](None, "hi") for builder in (by_function, by_class, by_instance)}
    assert results == {"echo:hi"}
    assert by_class._tools[0][1]["name"] == "echo"
    assert by_instance._tools[0][1]["name"] == "echo"


def test_tool_params_are_not_container_injected() -> None:
    builder = Agent.make("a").tool(EchoTool)
    target, _options = builder._tools[0]
    # ``text`` stays a tool parameter (PydanticAI owns the schema); it is required.
    assert "text" in inspect.signature(target).parameters
    assert inspect.signature(target).parameters["text"].default is inspect.Parameter.empty


def test_agent_definition_accepts_tool_class() -> None:
    class Defined(AgentDefinition):
        name = "defined"
        tools = [EchoTool]

    builder = Defined.to_builder()
    assert builder._tools[0][1]["name"] == "echo"


def test_public_attach_aliases_match_private_helpers() -> None:
    assert attach_usage is _toolkits_pkg._attach_usage


class _RecordingAgent:
    def __init__(self) -> None:
        self.tools: list[str] = []
        self._agentkit_usage_attached = False

    def tool(self, function: Any = None, **_options: Any) -> Any:
        if function is None:

            def decorator(func: Any) -> Any:
                self.tools.append(getattr(func, "__name__", repr(func)))
                return func

            return decorator
        self.tools.append(getattr(function, "__name__", repr(function)))
        return function


def test_toolkit_class_and_attach_helper_parity() -> None:
    helper_agent = _RecordingAgent()
    class_agent = _RecordingAgent()
    attach_usage(helper_agent)
    UsageToolkit().install(class_agent)
    assert helper_agent.tools == class_agent.tools
    assert helper_agent.tools  # non-empty


class _EchoToolkit(Toolkit):
    name = "echo"
    tools = [EchoTool]


def test_toolkit_resolves_tool_classes() -> None:
    resolved = _EchoToolkit().tool_objects()
    assert isinstance(resolved[0], EchoTool)


# -- WS3: drivers -----------------------------------------------------------
def test_driver_registry_accepts_callable_and_class() -> None:
    class ClassDriver(Driver):
        def build(self) -> str:
            return "from-class"

    register("duality-demo", "cls", ClassDriver)
    register("duality-demo", "fn", lambda app: "from-fn")
    try:
        assert resolve("duality-demo", "cls")(None) == "from-class"
        assert resolve("duality-demo", "fn")(None) == "from-fn"
    finally:
        unregister("duality-demo", "cls")
        unregister("duality-demo", "fn")


def test_register_driver_decorator_on_plain_function() -> None:
    @register_driver("duality-demo", "decorated")
    def decorated(app: Any) -> str:  # noqa: ARG001
        return "decorated"

    try:
        assert resolve("duality-demo", "decorated")(None) == "decorated"
    finally:
        unregister("duality-demo", "decorated")


def test_registry_and_app_extend_agree() -> None:
    app = App(discover=False)
    app.extend("cache", "custom", lambda app: NullCacheStore())  # noqa: ARG005
    assert isinstance(app.manager("cache").driver("custom"), NullCacheStore)

    @register_driver("cache", "global-custom")
    class GlobalCache(Driver):
        def build(self) -> Any:
            return NullCacheStore()

    try:
        assert isinstance(app.manager("cache").driver("global-custom"), NullCacheStore)
    finally:
        unregister("cache", "global-custom")


# -- WS4: container bindings & providers ------------------------------------
class _Impl:
    pass


def test_container_bind_closure_class_instance() -> None:
    container = Container()
    container.bind("closure", lambda c: "closure-value")
    container.bind("class", _Impl)
    container.instance("instance", 42)
    container.singleton("singleton", lambda c: object())

    assert container.make("closure") == "closure-value"
    assert isinstance(container.make("class"), _Impl)
    assert container.make("instance") == 42
    assert container.make("singleton") is container.make("singleton")


class _BindingsProvider(Provider):
    bindings = {"from-closure": lambda c: 1, "from-class": _Impl}
    singletons = {"shared": lambda c: object()}


def test_provider_bindings_accept_closure_and_class(runtime: Runtime) -> None:
    app = App(name="bindings", settings=runtime.settings, discover=False)
    app._runtime = runtime
    app.providers([_BindingsProvider])
    app.boot()
    assert app.make("from-closure") == 1
    assert isinstance(app.make("from-class"), _Impl)
    assert app.make("shared") is app.make("shared")


# -- WS5: commands, channels, middleware, jobs ------------------------------
def test_closure_command_matches_class_command() -> None:
    app = App(discover=False)
    app.commands(
        [("greet {name} {--loud}", lambda name, loud=False: f"hi {name} loud={loud}")]
    )

    class GreetCommand(Command):
        signature = "greet:class {name} {--loud}"

        def handle(self, name: str, loud: bool = False) -> str:
            return f"hi {name} loud={loud}"

    app.commands([GreetCommand])

    parsed = ParsedInput(arguments={"name": "Ada"}, options={"loud": True})
    closure_result = app._commands["greet"].call(parsed, app)
    registered = app._commands["greet:class"]
    class_command = registered() if isinstance(registered, type) else registered
    class_result = class_command.call(parsed, app)
    assert closure_result == class_result == "hi Ada loud=True"


def test_channel_function_and_class_parity() -> None:
    def run() -> None:
        return None

    class EchoChannel(Channel):
        name = "echo-class"

        def handle(self) -> Service:
            return Service("echo-class", run)

    app = App(discover=False)
    app.channel("echo-fn", lambda app: Service("echo-fn", run))
    app.channel("echo-class", EchoChannel)
    services = app.channel_services()
    assert sorted(service.name for service in services) == ["echo-class", "echo-fn"]


def test_middleware_function_and_class_parity() -> None:
    class TagMiddleware(Middleware):
        async def handle(self, turn: Any, call_next: Any) -> Any:
            return await call_next()

    async def tag(turn: Any, call_next: Any) -> Any:
        return await call_next()

    app = App(discover=False)
    app.middleware(TagMiddleware)
    app.middleware(tag)
    registered = app.middlewares()
    assert isinstance(registered[0], TagMiddleware)
    assert registered[1] is tag


def test_middleware_group_normalizes_members() -> None:
    class GroupMiddleware(Middleware):
        async def handle(self, turn: Any, call_next: Any) -> Any:
            return await call_next()

    app = App(discover=False)
    app.middleware(MiddlewareGroup("web", [GroupMiddleware]))
    app.middleware("web")
    assert isinstance(app.middlewares()[0], GroupMiddleware)


async def test_closure_job_runs_inline() -> None:
    app = App(discover=False)
    result = await app.dispatch(lambda: "ran")
    assert result == "ran"


async def test_closure_job_stays_inline_with_queue_enabled(runtime: Runtime) -> None:
    app = _app(runtime, "job")
    runtime.settings.queue_enabled = True
    try:
        assert await app.dispatch(lambda: "inline") == "inline"
    finally:
        runtime.settings.queue_enabled = False


# -- WS6: validation, gate, agent -------------------------------------------
def test_validation_three_forms() -> None:
    class EvenRule(ValidationRule):
        def validate(self, attribute: str, value: Any, fail: Any) -> None:
            if value % 2 != 0:
                fail("must be even")

    # string sugar | callable predicate | ValidationRule object
    assert Validator({"n": 4}, {"n": ["integer"]}).passes()
    assert Validator({"n": 4}, {"n": [Rule.min(0)]}).passes()
    assert Validator({"n": 3}, {"n": [EvenRule()]}).fails()


def test_gate_define_and_policy_parity(runtime: Runtime) -> None:
    app = _app(runtime, "gate")
    app.gate.define("ping", lambda actor, subject: getattr(actor, "id", None) == "ada")

    class _Actor:
        def __init__(self, ident: str) -> None:
            self.id = ident

    actor = _Actor("ada")
    assert app.gate.allows("ping", None, actor=actor) is True
    assert app.gate.denies("ping", None, actor=_Actor("bob")) is True


# -- executable examples: the documented forms run --------------------------
def test_documented_app_on_pattern_runs(runtime: Runtime) -> None:
    app = _app(runtime, "docs")
    recorded: list[str] = []
    app.on("boot", lambda ev: recorded.append(ev.name))
    app.events.dispatch("boot")
    assert recorded == ["boot"]


def test_documented_tool_class_pattern_runs() -> None:
    built = Agent.make("docs").tool(EchoTool).build(model=TestModel())
    assert built is not None
    assert built.name == "docs"
