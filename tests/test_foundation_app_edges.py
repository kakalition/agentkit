from __future__ import annotations

import pytest
from pydantic_ai import Agent as PydanticAgent
from pydantic_ai import RunContext

from agentkit import App, Provider, Service
from agentkit.config import AgentSettings
from agentkit.deps import Deps
from agentkit.foundation import config as cfg
from agentkit.foundation.application import _as_services, _spec_fields
from agentkit.runtime import Runtime


def _app(runtime: Runtime) -> App:
    app = App(name="edges", settings=runtime.settings, discover=False)
    app._runtime = runtime
    return app


def test_settings_class_is_instantiated():
    class Settings(AgentSettings):
        agent_name: str = "edge"

    app = App(settings=Settings, discover=False)
    assert isinstance(app.settings, Settings)
    assert app.settings.agent_name == "edge"


def test_providers_accepts_single_instance():
    app = App(discover=False)
    provider = Provider()
    app.providers(provider)
    assert provider in app._providers


def test_channels_migrations_middlewares_bind_and_db(runtime: Runtime):
    app = _app(runtime)
    app.channel("cli")
    assert "cli" in app.channels()

    app.migrations(["m1"])
    assert app._migrations == ["m1"]

    app.middleware(object())
    assert len(app.middlewares()) == 1

    app.bind("thing", lambda container: "x", singleton=True)
    assert app.make("thing") == "x"
    assert app.db is not None


def test_commands_accepts_dict():
    app = App(discover=False)
    app.commands({"a": "a", "b": "b"})
    assert app.command_names() == ["a", "b"]


def test_require_agent_raises_without_agent():
    app = App(discover=False)
    with pytest.raises(RuntimeError):
        app._require_agent()


def test_tool_on_raw_agent_with_approval(runtime: Runtime):
    app = _app(runtime)
    agent: PydanticAgent = PydanticAgent(None, output_type=str, name="raw")  # type: ignore[arg-type]
    app.agent(agent)

    async def risky(ctx: RunContext[Deps], value: str) -> str:
        """A risky tool."""
        return value

    app.tool(risky, requires_approval=True)
    assert "risky" in agent._function_toolset.tools


def test_as_services_variants():
    assert _as_services("x", None) == []
    service = Service("s", lambda: None)
    assert _as_services("x", service) == [service]
    assert len(_as_services("x", [service, [service]])) == 2
    assert _as_services("x", lambda: None)[0].name == "x"
    with pytest.raises(TypeError):
        _as_services("x", 123)


class _NoFields:
    pass


def test_spec_fields_requires_name_and_task():
    with pytest.raises(ValueError):
        _spec_fields(_NoFields())


def test_config_directory_from_env(monkeypatch, tmp_path):
    directory = tmp_path / "cfg"
    directory.mkdir()
    (directory / "thing.py").write_text("config = {'value': 3}\n")
    monkeypatch.setenv("AGENTKIT_CONFIG_DIR", str(directory))
    assert cfg.config_directory() == directory
    assert cfg.load_config_file("thing") == {"value": 3}
    assert cfg.load_config_file("missing") == {}


def test_resolve_section_with_plain_class():
    class Plain:
        def __init__(self) -> None:
            self.value = 1

    resolved = cfg.resolve_section("plain", Plain)  # type: ignore[arg-type]
    assert resolved.value == 1
