from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agentkit.foundation.agent import Agent


def _fn(agent, name):
    return agent._function_toolset.tools[name].function


# -- storage: composite + tools ---------------------------------------------
def test_composite_filesystem_overlay(tmp_path):
    from agentkit.errors import InvalidInput
    from agentkit.foundation.storage import CompositeFileSystem, Filesystem, MemoryFilesystem

    top = MemoryFilesystem()
    base = MemoryFilesystem()
    base.put("base.txt", "from base")
    top.put("top.txt", "from top")
    fs = CompositeFileSystem(top, base)
    assert fs.get("base.txt") == "from base"
    assert fs.get("top.txt") == "from top"
    assert fs.list() == ["base.txt", "top.txt"]
    assert fs.exists("base.txt") is True
    with pytest.raises(InvalidInput):
        fs.get("missing.txt")

    local = Filesystem(tmp_path / "store")
    local.put("docs/a.md", "hello world\nsecond line")
    assert "docs/a.md" in local.glob("docs/*.md")
    assert local.grep("hello")[0][0] == "docs/a.md"
    assert local.edit_file("docs/a.md", "hello", "goodbye") == 1
    assert "goodbye" in local.get("docs/a.md")
    assert local.edit_file("docs/a.md", "absent", "x") == 0


# -- tasks ------------------------------------------------------------------
async def test_attach_tasks_tools_and_store(tmp_path):
    from agentkit.config import AgentSettings
    from agentkit.foundation import App

    app = App(settings=AgentSettings(agent_home=tmp_path), discover=False)
    agent = Agent.make("t").instructions("x").todos().output(str).build()
    tools = set(agent._function_toolset.tools.keys())
    assert {"write_todos", "read_todos", "add_todo", "update_todo", "clear_todos"} <= tools

    deps = SimpleNamespace(extras={"task_store": app.tasks})
    ctx = SimpleNamespace(deps=deps)
    assert "one" in await _fn(agent, "write_todos")(ctx, ["one", "two"])
    assert "added #3" in await _fn(agent, "add_todo")(ctx, "three")
    assert "completed" in await _fn(agent, "update_todo")(ctx, 1, "completed")
    assert "cleared 3" in await _fn(agent, "clear_todos")(ctx)


# -- code execution ---------------------------------------------------------
def test_attach_code_executor_is_approval_gated():
    agent = Agent.make("c").instructions("x").code_execution().output(str).build()
    assert agent._function_toolset.tools["run_code"].requires_approval is True


async def test_local_code_executor_runs():
    from agentkit.executors import LocalSubprocessExecutor

    result = await LocalSubprocessExecutor().run("print(2 + 2)")
    assert result.ok and "4" in result.stdout


# -- subagents --------------------------------------------------------------
async def test_subagent_tool_isolated_and_shared():
    from agentkit.agents.handle import AgentHandle
    from agentkit.agents.registry import AgentRegistry
    from agentkit.agents.subagent import SharedContext, subagent_tool

    seen: dict[str, object] = {}

    class EchoAgent:
        async def run(self, prompt, *, deps=None, usage=None, model=None, **kwargs):
            seen["deps"] = deps
            return type("Result", (), {"output": f"echo:{prompt}"})()

    registry = AgentRegistry()
    registry.register(AgentHandle.local(EchoAgent(), name="echo"))

    parent_ctx = SimpleNamespace(deps="PARENT")
    assert (await subagent_tool(registry)(parent_ctx, "echo", "hi")) == "echo:hi"
    assert seen["deps"] is None

    shared = subagent_tool(registry, strategy=SharedContext())
    assert (await shared(parent_ctx, "echo", "hi")) == "echo:hi"
    assert seen["deps"] == "PARENT"


# -- groupchat speakers -----------------------------------------------------
async def test_groupchat_speaker_strategies():
    from agentkit.comms import GroupChatSpeaker, GroupChatTopology

    async def echo(message: str) -> str:
        return f"ack:{message}"

    rr = GroupChatTopology(speaker=GroupChatSpeaker.ROUND_ROBIN)
    rr.register("a", echo).register("b", echo)
    assert set(await rr.broadcast("hi")) == {"a"}
    assert set(await rr.broadcast("hi")) == {"b"}
    assert set(await rr.broadcast("hi")) == {"a"}

    mod = GroupChatTopology(speaker=GroupChatSpeaker.MODERATOR, moderator="b")
    mod.register("a", echo).register("b", echo)
    assert set(await mod.broadcast("hi")) == {"b"}

    everyone = GroupChatTopology(speaker=GroupChatSpeaker.ALL)
    everyone.register("a", echo).register("b", echo)
    assert set(await everyone.broadcast("hi")) == {"a", "b"}


# -- workspace tools --------------------------------------------------------
async def test_workspace_glob_grep_edit(tmp_path):
    agent = Agent.make("w").instructions("x").workspace(tmp_path).output(str).build()
    tools = set(agent._function_toolset.tools.keys())
    assert {"read_file", "write_file", "list_files", "run_command", "edit_file", "glob", "grep"} <= tools
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("import os\nVALUE = 1\n")
    ctx = SimpleNamespace(deps=None)
    assert "pkg/a.py" in await _fn(agent, "glob")(ctx, "**/a.py")
    assert "VALUE" in await _fn(agent, "grep")(ctx, "VALUE")
    assert "edited" in await _fn(agent, "edit_file")(ctx, "pkg/a.py", "VALUE = 1", "VALUE = 2")
    assert "VALUE = 2" in (tmp_path / "pkg" / "a.py").read_text()


# -- type-safe driver constants ---------------------------------------------
def test_driver_settings_are_typed():
    import pydantic
    import pytest as _pytest

    from agentkit.config import AgentSettings
    from agentkit.support.kinds import CacheDriver, DriverKind

    settings = AgentSettings(cache_driver="array", memory_embedding_backend="hash")
    assert settings.cache_driver is CacheDriver.ARRAY
    assert settings.cache_driver == "array"  # StrEnum compares equal to its value
    assert f"{DriverKind.CACHE}" == "cache"
    with _pytest.raises(pydantic.ValidationError):
        AgentSettings(cache_driver="not-a-driver")


# -- comms context ----------------------------------------------------------
def test_comms_context_on_deps(deps):
    from agentkit.agents.handoff import _depth
    from agentkit.agents.mailbox import _with_sender

    assert deps.comms.sender is None and deps.comms.handoff_depth == 0
    ctx = SimpleNamespace(deps=deps)
    _with_sender(ctx, "researcher")
    assert deps.comms.sender == "researcher"
    deps.comms.handoff_depth = 2
    assert _depth(deps) == 2


# -- deps seeding -----------------------------------------------------------
def test_app_deps_seed_task_store_and_executor(tmp_path):
    from agentkit.config import AgentSettings
    from agentkit.foundation import App

    app = App(
        settings=AgentSettings(agent_home=tmp_path, memory_embedding_backend="hash"),
        discover=False,
        model=object(),
    )

    async def _check():
        async with app.repositories() as repos:
            deps = app.deps(repos)
        assert deps.extras.get("task_store") is not None
        assert deps.extras.get("code_executor") is not None

    asyncio.run(_check())
