from __future__ import annotations

from pathlib import Path

from agentkit import Agent, App
from agentkit.config import AgentSettings
from agentkit.db.models import Feedback
from agentkit.toolkits import RunRegisteredTask
from agentkit.webui.introspect import stack_view

NATIVE_TOOLS = {
    "db_find",
    "schedule_task",
    "enqueue_task",
    "notify",
    "list_conversations",
    "usage_summary",
    "index_document",
    "save_skill",
}

LEARNING_TOOLS = {"learn", "reflect", "list_lessons", "forget_lesson"}


def _settings(tmp_path: Path, **overrides) -> AgentSettings:
    return AgentSettings(
        agent_home=tmp_path,
        memory_embedding_backend="hash",
        webui_enabled=False,
        **overrides,
    )


def test_full_attaches_enabled_toolkits_and_learning(tmp_path: Path):
    settings = _settings(tmp_path)
    agent = (
        Agent.make("full")
        .instructions("x")
        .full(models={"feedback": Feedback}, tasks=["noop"], jobs={"noop": RunRegisteredTask}, settings=settings)
        .output(str)
        .build(settings=settings)
    )
    tools = set(agent._function_toolset.tools.keys())
    assert tools >= NATIVE_TOOLS
    assert tools >= LEARNING_TOOLS


def test_full_respects_disabled_toolkit_flag(tmp_path: Path):
    settings = _settings(tmp_path, db_tools_enabled=False)
    agent = (
        Agent.make("full")
        .instructions("x")
        .full(settings=settings)
        .output(str)
        .build(settings=settings)
    )
    tools = set(agent._function_toolset.tools.keys())
    assert "db_find" not in tools
    assert "schedule_task" in tools


def test_full_respects_disabled_learning_flag(tmp_path: Path):
    settings = _settings(tmp_path, learning_enabled=False)
    agent = (
        Agent.make("full")
        .instructions("x")
        .full(settings=settings)
        .output(str)
        .build(settings=settings)
    )
    tools = set(agent._function_toolset.tools.keys())
    assert not (LEARNING_TOOLS & tools)


def test_stack_view_reports_toolkits_and_allow_lists(tmp_path: Path):
    settings = _settings(tmp_path)
    app = App(name="stack", settings=settings, discover=False)
    app.models({"feedback": Feedback})
    app.agent_tasks(["noop"])
    app.agent_jobs({"noop": RunRegisteredTask})

    view = stack_view(settings, app)
    native = view["native_tools"]
    assert set(native["enabled"]) == {
        "database",
        "scheduler",
        "queue",
        "notifications",
        "history",
        "usage",
        "knowledge_admin",
        "skills_admin",
    }
    assert native["models"] == ["feedback"]
    assert native["tasks"] == ["noop"]
    assert native["jobs"] == ["noop"]
    assert view["learning"]["enabled"] is True
    assert "reflect_cron" in view["learning"]
