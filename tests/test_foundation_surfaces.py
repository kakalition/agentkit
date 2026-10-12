from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_ai import Agent as PydanticAgent
from pydantic_ai import RunContext

from agentkit import Agent, App, Events, Log, Memory, Schedule, ToolPolicy
from agentkit import scheduler as scheduler_mod
from agentkit.deps import Deps
from agentkit.foundation.commands import load_bootstrap
from agentkit.foundation.db import active_repos, session_scope, using_repos
from agentkit.foundation.events import Dispatcher, Event
from agentkit.runtime import Runtime


def _app(runtime: Runtime) -> App:
    app = App(name="surfaces", settings=runtime.settings, discover=False)
    app._runtime = runtime
    app.boot()
    return app


async def test_memory_facade_digest(runtime: Runtime):
    _app(runtime)
    await Memory.remember("The user keeps a cat named Mochi", kind="person")
    digest = Memory.digest()
    assert digest is not None and "Mochi" in digest
    assert Memory.all(limit=1)
    assert Memory.search("Mochi")


async def test_events_facade_async_dispatch(runtime: Runtime):
    _app(runtime)
    seen: list[str] = []

    async def listener(event) -> None:  # noqa: ANN001
        seen.append(event.name)

    Events.on("ping", listener)
    await Events.dispatch_async("ping")
    assert seen == ["ping"]


def test_log_facade_methods(runtime: Runtime):
    _app(runtime)
    Log.info("hello %s", "world")
    Log.warning("careful")
    Log.error("boom")
    Log.debug("trace")


def test_schedule_facade_crud(runtime: Runtime):
    _app(runtime)
    ran: list[str] = []

    @Schedule.task("digest")
    def digest(*, period: str = "week") -> None:
        ran.append(period)

    scheduler_mod._runtime = None
    try:
        Schedule.cron("weekly", "0 8 * * 1", "digest", args={"period": "week"})
        Schedule.once("once", "2030-01-01T00:00", "digest")
        jobs = {job["name"]: job for job in Schedule.list()}
        assert jobs["weekly"]["kind"] == "cron"
        assert jobs["once"]["kind"] == "once"

        assert Schedule.disable("weekly") is True
        assert Schedule.enable("weekly") is True
        assert Schedule.remove("once") is True
        assert Schedule.remove("once") is False
    finally:
        scheduler_mod._runtime = None


def test_schedule_facade_run_due(monkeypatch, runtime: Runtime):
    _app(runtime)
    ran: list[str] = []

    @Schedule.task("ping")
    def ping() -> None:
        ran.append("ping")

    class FakeScheduler:
        def run_due_now(self, now=None):  # noqa: ANN001
            ran.append("due")
            return ["ping"]

    monkeypatch.setattr(
        "agentkit.foundation.facades.ScheduleService._scheduler", lambda self: FakeScheduler()
    )
    assert Schedule.run_due() == ["ping"]
    assert ran == ["due"]


def test_db_ambient_repos_reuse(runtime: Runtime):
    app = _app(runtime)
    with app.repositories() as repos, using_repos(repos):
        assert active_repos() is repos
        with session_scope(app) as inner:
            assert inner is repos
    assert active_repos() is None


def test_events_dispatcher_forget_and_event_instance():
    dispatcher = Dispatcher()
    seen: list[object] = []

    def listener(event) -> None:  # noqa: ANN001
        seen.append(event.a)

    dispatcher.listen("x", listener)
    assert dispatcher.listeners("x") == [listener]
    dispatcher.dispatch(Event("x", payload={"a": 1}))
    assert seen == [1]
    dispatcher.forget("x")
    assert dispatcher.listeners("x") == []
    dispatcher.listen("*", listener)
    dispatcher.forget()
    assert dispatcher.listeners("y") == []


def test_builder_fluent_surface():
    async def tool_a(ctx: RunContext[Deps], x: str) -> str:
        """A."""
        return x

    async def tool_b(ctx: RunContext[Deps], y: str) -> str:
        """B."""
        return y

    specialist = PydanticAgent(
        None, output_type=str, name="spec"  # type: ignore[arg-type]
    )
    builder = (
        Agent.make("fluent", description="d")
        .tools(tool_a, tool_b)
        .specialist(specialist, name="s1", description="d1")
        .orchestrate({"s2": (specialist, "d2")})
        .orchestrate([(specialist, "s3", "d3")])
        .policy(ToolPolicy(deny=set()))
        .retries(1)
        .output(str)
    )
    assert repr(builder).startswith("Agent.make('fluent'")
    built = builder.build()
    tools = set(built._function_toolset.tools.keys())
    assert {"tool_a", "tool_b", "s1", "s2", "s3"} <= tools
    assert builder.agent is built  # cached
    assert builder.policies
    builder.model(None)  # fluent setter returns self
    builder.capability(object())  # stored, not applied to the cached build


def test_builder_orchestrate_noop():
    builder = Agent.make("x").orchestrate()
    assert builder.build() is not None


def test_app_pending_tool_before_agent(runtime: Runtime):
    app = App(name="pending", settings=runtime.settings, discover=False)
    app._runtime = runtime

    async def late(ctx: RunContext[Deps], value: str) -> str:
        """Late tool."""
        return value

    app.tool(late)
    app.agent(Agent.make("pending").instructions("i").output(str))
    assert "late" in app.agent()._function_toolset.tools


def test_app_deps_uses_model_override(runtime: Runtime):
    marker = object()
    app = App(name="deps", settings=runtime.settings, discover=False, model=marker)
    app._runtime = runtime
    with app.repositories() as repos:
        deps = app.deps(repos)
    assert deps.model is marker


def test_load_bootstrap_rejects_non_app(tmp_path: Path, monkeypatch):
    module = tmp_path / "not_an_app.py"
    module.write_text("app = 123\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(TypeError):
        load_bootstrap("not_an_app:app")


def test_load_bootstrap_on_module_object(tmp_path: Path, monkeypatch):
    module = tmp_path / "module_obj.py"
    module.write_text("value = 1\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(TypeError):
        load_bootstrap("module_obj")
