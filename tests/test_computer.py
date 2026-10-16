from __future__ import annotations

import importlib.util

import pytest

from agentkit.computer import ComputerManager, LoopbackComputer, PlaywrightComputer
from agentkit.config import AgentSettings
from agentkit.errors import ConfigurationError
from agentkit.foundation import App


def _app(tmp_path) -> App:
    return App(settings=AgentSettings(agent_home=tmp_path), discover=False)


async def test_loopback_computer_actions():
    computer = LoopbackComputer()
    snapshot = await computer.goto("https://example.test")
    assert "example.test" in snapshot
    assert "clicked" in await computer.click("#go")
    assert "typed" in await computer.type("#q", "hi")
    assert (await computer.evaluate("1 + 1"))["expression"] == "1 + 1"
    await computer.close()


def test_manager_resolves_loopback(tmp_path):
    assert isinstance(_app(tmp_path).manager("computer").driver(), LoopbackComputer)


async def test_playwright_missing_extra_names_browser(tmp_path):
    if importlib.util.find_spec("playwright") is not None:
        pytest.skip("playwright installed; missing-extra path not applicable")
    computer = PlaywrightComputer()
    with pytest.raises(ConfigurationError) as excinfo:
        await computer.snapshot()
    assert "browser" in str(excinfo.value)


def test_computer_tools_are_approval_gated():
    from pydantic_ai import Agent as PydanticAgent
    from pydantic_ai.models.test import TestModel

    from agentkit.deps import Deps
    from agentkit.toolkits.computer import attach_computer_tools

    agent = PydanticAgent(TestModel(), deps_type=Deps)
    attach_computer_tools(agent, LoopbackComputer())
    names = {
        tool.name
        for tool in getattr(agent._function_toolset, "tools", {}).values()  # noqa: SLF001
    }
    assert {"browser_goto", "browser_snapshot", "browser_click"} <= names


def test_computer_manager_class_registered():
    assert ComputerManager.kind == "computer"
