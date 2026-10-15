from __future__ import annotations

import threading
from dataclasses import dataclass

import pytest
import typer
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from typer.testing import CliRunner

from agentkit import Agent, App, Command, Section, Service
from agentkit.foundation.application import _as_services
from agentkit.foundation.facade import emit
from agentkit.foundation.middleware import logging_middleware
from agentkit.runtime import Runtime


def _app(runtime: Runtime, **kwargs) -> App:
    app = App(name="prod", settings=runtime.settings, discover=False, **kwargs)
    app._runtime = runtime
    return app


async def test_applies_dict_schedules_to_db(runtime: Runtime):
    app = _app(runtime)
    app.schedules(
        [
            {"name": "digest", "cron": "0 8 * * 1", "task": "digest", "args": {"period": "week"}},
            {"name": "once", "when": "2030-01-01T00:00", "task": "ping"},
        ]
    )
    app.boot()
    async with app.repositories() as repos:
        jobs = {job.name: job for job in await repos.schedules.list()}
    assert jobs["digest"].kind == "cron"
    assert jobs["digest"].task == "digest"
    assert jobs["once"].kind == "once"


@dataclass
class _Spec:
    name: str
    task: str
    cron: str


async def test_applies_object_schedules_to_db(runtime: Runtime):
    app = _app(runtime)
    app.schedules([_Spec(name="weekly", task="weekly", cron="0 9 * * 1")])
    app.boot()
    async with app.repositories() as repos:
        rows = await repos.schedules.list()
    assert [row.name for row in rows] == ["weekly"]


async def test_schedule_spec_without_cron_or_when_is_skipped(runtime: Runtime):
    app = _app(runtime)
    app.schedules([{"name": "bad", "task": "t"}])
    app.boot()  # logs and continues rather than raising
    async with app.repositories() as repos:
        assert await repos.schedules.list() == []


def test_schedule_spec_without_name_raises(runtime: Runtime):
    app = _app(runtime)
    with pytest.raises((KeyError, ValueError)):
        app._register_schedule({"task": "t", "cron": "* * * * *"})


class _Hello(Command):
    name = "hello"
    help = "say hello"

    def run(self, app) -> None:  # noqa: ANN001
        self.ran = True


def test_provider_commands_install_onto_typer(runtime: Runtime):
    app = _app(runtime)
    app.commands([_Hello()])
    assert app.command_names() == ["hello"]
    cli = typer.Typer()
    app.install_commands(cli)
    assert "hello" in {c.name for c in cli.registered_commands}


def test_channel_services_resolve_and_serve(runtime: Runtime):
    app = _app(runtime)
    ran: list[str] = []

    def factory(_app: App) -> Service:
        return Service("ticker", lambda: ran.append("tick"))

    app.channel("ticker", factory)
    services = app.channel_services()
    assert [service.name for service in services] == ["ticker"]

    stop = threading.Event()

    def stopper() -> None:
        ran.append("stopper")
        stop.set()

    app.channel("stopper", lambda _app: Service("stopper", stopper))
    app.serve(stop_event=stop, webui=False)
    assert "stopper" in ran


def test_as_services_rejects_bad_factory():
    with pytest.raises(TypeError):
        _as_services("bad", 123)


def test_serve_hands_services_and_app_to_run_all(runtime: Runtime, monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_all(services, **kwargs):  # noqa: ANN001
        captured["services"] = services
        captured["kwargs"] = kwargs

    monkeypatch.setattr("agentkit.supervise.run_all", fake_run_all)
    app = _app(runtime)
    app.channel("ticker", lambda _app: Service("ticker", lambda: None))
    app.serve(webui=False)

    services = captured["services"]
    assert [service.name for service in services] == ["ticker"]  # type: ignore[union-attr]
    kwargs = captured["kwargs"]
    assert kwargs["app"] is app  # type: ignore[index]
    assert kwargs["webui"] is False  # type: ignore[index]
    assert kwargs["runtime"] is runtime  # type: ignore[index]


def test_serve_defaults_webui_to_settings(runtime: Runtime, monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_all(services, **kwargs):  # noqa: ANN001
        captured["webui"] = kwargs.get("webui")

    monkeypatch.setattr("agentkit.supervise.run_all", fake_run_all)
    runtime.settings.webui_enabled = False
    app = _app(runtime)
    app.serve()
    assert captured["webui"] is False


async def test_applies_nothing_when_no_schedules(runtime: Runtime):
    app = _app(runtime)
    app.boot()
    async with app.repositories() as repos:
        assert await repos.schedules.list() == []


def test_config_section_cached_on_app(runtime: Runtime, monkeypatch):
    class Demo(Section):
        env_prefix = "AGENTKIT_PRODCONF_"
        value: int = 1

    monkeypatch.setenv("AGENTKIT_PRODCONF_VALUE", "7")
    app = _app(runtime)
    app.config("demo", Demo)
    first = app.config("demo")
    second = app.config("demo")
    assert first is second
    assert first.value == 7


async def test_logging_middleware_runs_turn(runtime: Runtime):
    model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("hi")]))
    app = _app(runtime, model=model)
    app.agent(Agent.make("prod").instructions("x").output(str))
    app.middleware(logging_middleware())
    app.boot()
    result = await app.run("hello")
    assert result.output == "hi"


async def test_emit_helper_with_and_without_app(runtime: Runtime):
    app = _app(runtime)
    app.boot()
    seen: list[str] = []
    app.on("ping", lambda event: seen.append("pong"))
    assert await emit("ping") is True
    assert seen == ["pong"]


async def test_emit_without_current_app_returns_false():
    from agentkit.foundation.facade import using

    with using(None):
        assert await emit("anything") is False


COMMAND_RAN: list[str] = []


class _Recorder(Command):
    name = "record"
    help = "record"

    def run(self, app) -> None:  # noqa: ANN001
        COMMAND_RAN.append("yes")


class _Other(Command):
    name = "other"
    help = "other"

    def run(self, app) -> None:  # noqa: ANN001
        COMMAND_RAN.append("other")


def test_installed_command_end_to_end(tmp_path, monkeypatch):
    module = tmp_path / "cmd_bootstrap.py"
    module.write_text("from agentkit import App\napp = App('cli', discover=False)\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("AGENTKIT_BOOTSTRAP", "cmd_bootstrap:app")
    app = App(discover=False)
    app.commands([_Recorder(), _Other()])
    cli = typer.Typer()
    app.install_commands(cli)
    result = CliRunner().invoke(cli, ["record"])
    assert result.exit_code == 0
    assert COMMAND_RAN == ["yes"]


def test_cli_serve_missing_bootstrap(monkeypatch):
    monkeypatch.setenv("AGENTKIT_BOOTSTRAP", "definitely_missing_module_xyz:app")
    from agentkit.cli import app as cli_app

    result = CliRunner().invoke(cli_app, ["serve", "--no-scheduler", "--no-webui"])
    assert result.exit_code == 1
    assert "could not load app" in result.output


def test_discovery_positive_loads_provider(monkeypatch):
    class FakeProvider:
        def __init__(self) -> None:
            pass

    class FakeEntryPoint:
        name = "fake"

        def load(self):
            return FakeProvider

    monkeypatch.setattr(
        "agentkit.foundation.application.entry_points", lambda group: [FakeEntryPoint()]
    )
    app = App(discover=True)
    assert FakeProvider in app._providers


async def test_pipeline_reused_across_turns(runtime: Runtime):
    model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("ok")]))
    app = _app(runtime, model=model)
    app.agent(Agent.make("prod").instructions("x").output(str))
    calls: list[str] = []

    async def counter(turn, call_next):
        calls.append(turn.text)
        return await call_next()

    app.middleware(counter)
    app.boot()
    await app.run("a")
    await app.run("b")
    assert calls == ["a", "b"]
