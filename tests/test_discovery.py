from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agentkit import AgentDefinition, Application, Command, Provider, Service
from agentkit.config import AgentSettings
from agentkit.foundation import discovery


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build(root: Path) -> Path:
    for package in (
        "app",
        "app/Providers",
        "app/Agents",
        "app/Channels",
        "app/Console",
        "app/Console/Commands",
    ):
        _write(root / package / "__init__.py", "")
    _write(
        root / "app" / "Providers" / "AppServiceProvider.py",
        "from agentkit import Provider\n\n\nclass AppServiceProvider(Provider):\n"
        "    def register(self, app):\n        return None\n",
    )
    _write(
        root / "app" / "Agents" / "Assistant.py",
        "from agentkit import AgentDefinition\n\n\nclass Assistant(AgentDefinition):\n"
        "    name = 'assistant'\n\n    def define(self, agent):\n"
        "        return agent.instructions('hi').memory().output(str)\n",
    )
    _write(
        root / "app" / "Channels" / "Example.py",
        "from agentkit import Channel, Service\n\n\nclass ExampleChannel(Channel):\n"
        "    name = 'example'\n\n"
        "    def handle(self):\n        return Service('example', lambda: None)\n",
    )
    _write(
        root / "app" / "Console" / "Commands" / "Ping.py",
        "from agentkit import Command\n\n\nclass PingCommand(Command):\n"
        "    name = 'ping'\n    help = 'ping'\n\n    def run(self, app):\n        return None\n",
    )
    _write(root / "config" / "app.py", "config = {}\n")
    _write(
        root / "config" / "feature.py",
        "from agentkit import Section\n\n\nclass FeatureSection(Section):\n    flag: bool = True\n",
    )
    return root


@pytest.fixture
def project(tmp_path: Path):
    root = _build(tmp_path / "proj")
    yield root
    resolved = str(root.resolve())
    sys.path[:] = [entry for entry in sys.path if entry != resolved]
    for name, module in list(sys.modules.items()):
        source = getattr(module, "__file__", None)
        if source and resolved in source:
            sys.modules.pop(name, None)


def test_discovery_finds_conventions(project: Path):
    assert [c.__name__ for c in discovery.discover_providers(project)] == ["AppServiceProvider"]
    assert [c.__name__ for c in discovery.discover_agents(project)] == ["Assistant"]
    assert [name for name, _ in discovery.discover_channels(project)] == ["example"]
    assert [c.__name__ for c in discovery.discover_commands(project)] == ["PingCommand"]
    assert set(discovery.discover_config(project)) == {"feature"}


def test_discovery_is_empty_without_dirs(tmp_path: Path):
    assert discovery.discover_providers(tmp_path) == []
    assert discovery.discover_agents(tmp_path) == []


def test_application_configure_autodiscovers(project: Path, monkeypatch, tmp_path: Path):
    settings = AgentSettings(agent_home=tmp_path, memory_embedding_backend="hash", agent_name="proj")

    app = Application.configure(settings=settings, base_path=project).create()
    app.boot()

    assert app.name == "proj"  # auto-detected from settings.agent_name
    assert app.agent() is not None  # the class in app/Agents/ registered itself
    assert "example" in app.channels()
    assert "ping" in app.command_names()
    assert set(discovery.discover_config(project)) == {"feature"}


def test_explicit_declarations_win(project: Path, tmp_path: Path):
    settings = AgentSettings(agent_home=tmp_path, memory_embedding_backend="hash")

    class ExplicitProvider(Provider):
        def register(self, app):  # noqa: ANN001
            app.bind("explicit", lambda c: "value")

    app = (
        Application.configure(settings=settings, base_path=project)
        .withProviders([ExplicitProvider])
        .create()
    )
    app.boot()
    assert app.make("explicit") == "value"


def test_agent_definition_builds_class_based_agent(tmp_path: Path):
    settings = AgentSettings(agent_home=tmp_path, memory_embedding_backend="hash")

    class MyAgent(AgentDefinition):
        name = "custom"
        posture = "hybrid"

        def define(self, agent):  # noqa: ANN001
            return agent.instructions("custom").output(str)

    builder = MyAgent.to_builder(settings=settings)
    assert builder.name == "custom"
    assert builder.posture_name == "hybrid"
    assert builder.build(settings=settings).name == "custom"


def test_service_import_is_public():
    assert Service is not None and Command is not None
