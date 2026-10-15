from __future__ import annotations

from pathlib import Path

from agentkit import App, FullStackProvider
from agentkit.config import AgentSettings
from agentkit.foundation.fullstack import ChannelsSection, MemorySection


def _settings(tmp_path: Path, **overrides) -> AgentSettings:
    return AgentSettings(
        agent_home=tmp_path, memory_embedding_backend="hash", webui_enabled=False, **overrides
    )


def _app(tmp_path: Path, **overrides) -> App:
    return App(name="stack", settings=_settings(tmp_path, **overrides), discover=False)


def test_register_declares_config_sections(tmp_path: Path):
    app = _app(tmp_path).providers([FullStackProvider])
    app.boot()
    assert "memory" in app._config_schemas
    assert "channels" in app._config_schemas
    assert isinstance(app.config("memory"), MemorySection)
    assert isinstance(app.config("channels"), ChannelsSection)


def test_boot_is_graceful_with_no_channels(tmp_path: Path):
    app = _app(tmp_path).fullstack()
    app.boot()  # must not raise
    names = {spec.build()["name"] for spec in app.schedule_specs()}
    assert "memory-consolidate" in names
    assert app.channels() == {}


def test_boot_registers_configured_channel_and_sender(tmp_path: Path):
    app = _app(tmp_path, telegram_bot_token="token").fullstack()
    app.boot()
    assert "telegram" in app.channels()
    assert app.notifier.channel("telegram") is not None


def test_boot_registers_settings_list_flags(tmp_path: Path):
    app = _app(tmp_path, memory_enabled=False, learning_enabled=False).fullstack()
    app.boot()
    assert {spec.build()["name"] for spec in app.schedule_specs()} == set()


def test_memory_consolidate_task_is_registered(tmp_path: Path):
    app = _app(tmp_path).fullstack()
    app.boot()
    from agentkit.scheduler import TASKS

    assert "memory:consolidate" in TASKS


def test_learning_reflect_scheduled_and_registered(tmp_path: Path):
    app = _app(tmp_path).fullstack()
    app.boot()
    from agentkit.learning import LESSON_TASK
    from agentkit.scheduler import TASKS

    names = {spec.build()["name"] for spec in app.schedule_specs()}
    assert "learning-reflect" in names
    assert LESSON_TASK in TASKS


def test_learning_disabled_skips_reflect(tmp_path: Path):
    app = _app(tmp_path, learning_enabled=False).fullstack()
    app.boot()
    names = {spec.build()["name"] for spec in app.schedule_specs()}
    assert "learning-reflect" not in names


def test_boot_wires_registry_and_mailbox_when_subagents_enabled(tmp_path: Path):
    app = _app(tmp_path, subagents_enabled=True).fullstack()
    app.boot()
    from agentkit.agents.mailbox import Mailbox
    from agentkit.agents.registry import AgentRegistry

    assert isinstance(app.make("agents"), AgentRegistry)
    assert isinstance(app.make("mailbox"), Mailbox)


def test_boot_leaves_agents_unwired_by_default(tmp_path: Path):
    app = _app(tmp_path).fullstack()
    app.boot()
    assert getattr(app, "_agent_registry", None) is None
