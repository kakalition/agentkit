from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from agentkit import AgentSettings
from agentkit.errors import ConfigurationError
from agentkit.foundation.agent import Agent
from agentkit.foundation.application import App
from agentkit.gateways.base import GatewayError
from agentkit.gateways.linear import LinearGateway
from agentkit.gateways.mattermost import MattermostGateway
from agentkit.gateways.pairing import PairingRegistry
from agentkit.gateways.registry import LogChannel
from agentkit.gateways.webhook import WebhookGateway
from agentkit.mcp.server import build_agent_mcp_server
from agentkit.scheduling_nl import NaturalSchedule, parse_when
from agentkit.tui import run_tui


def _settings(tmp_path: Path, **overrides) -> AgentSettings:
    return AgentSettings(agent_home=tmp_path, memory_embedding_backend="hash", **overrides)


# -- DM pairing -------------------------------------------------------------
def test_pairing_request_confirm_and_unpair():
    registry = PairingRegistry()
    code = registry.request("user-1", code="123456")
    assert code == "123456"
    assert not registry.is_paired("user-1")
    assert not registry.confirm("user-1", "000000")
    assert registry.confirm("user-1", "123456")
    assert registry.is_paired("user-1")
    assert registry.paired() == ["user-1"]
    assert registry.unpair("user-1") and not registry.is_paired("user-1")


def test_pairing_code_expires():
    now = {"t": 100.0}
    registry = PairingRegistry(code_ttl_s=10, clock=lambda: now["t"])
    registry.request("u", code="1")
    now["t"] = 200.0
    assert not registry.confirm("u", "1")


def test_gateway_pairing_gates_access():
    gateway = LogChannel(app=None, pairing=PairingRegistry())
    assert not gateway.is_allowed("stranger")
    code = gateway.pair("stranger")
    assert gateway.confirm_pairing("stranger", code)
    assert gateway.is_allowed("stranger")


def test_gateway_allow_list_still_wins():
    gateway = LogChannel(app=None, allowed_channel_ids=["vip"])
    assert gateway.is_allowed("vip") and not gateway.is_allowed("other")


# -- channels ---------------------------------------------------------------
async def test_new_gateways_require_configuration():
    with pytest.raises(GatewayError):
        await MattermostGateway(app=None).send("mattermost:c", "hi")
    with pytest.raises(GatewayError):
        await LinearGateway(app=None).send("linear:ENG-1", "hi")
    with pytest.raises(GatewayError):
        await WebhookGateway(app=None).send("webhook:c", "hi")


@pytest.mark.parametrize(
    ("driver", "cls"),
    [("mattermost", MattermostGateway), ("linear", LinearGateway), ("webhook", WebhookGateway)],
)
def test_channel_driver_selection(tmp_path: Path, driver, cls):
    app = App(name="c", settings=_settings(tmp_path, channel_driver=driver), discover=False)
    assert isinstance(app.manager("channel").driver(), cls)


# -- natural-language scheduling -------------------------------------------
def test_parse_when_patterns():
    daily = parse_when("every day at 9am")
    assert daily == NaturalSchedule("cron", schedule="0 9 * * *")
    weekly = parse_when("every monday at 8:30")
    assert weekly is not None and weekly.schedule == "30 8 * * 1"
    every_minute = parse_when("every 15 minutes")
    assert every_minute is not None and every_minute.schedule == "*/15 * * * *"
    assert parse_when("in 2 hours").kind == "once"
    assert parse_when("tomorrow at 8am").kind == "once"
    assert parse_when("whenever you like") is None


def test_schedule_natural_tool_attached(tmp_path: Path):
    settings = _settings(tmp_path)
    built = Agent.make("s").instructions("x").output(str).scheduler(tasks=["sync"]).build(
        settings=settings
    )
    assert "schedule_natural" in set(built._function_toolset.tools.keys())


# -- TUI --------------------------------------------------------------------
def test_tui_requires_extra():
    import importlib.util

    if importlib.util.find_spec("textual") is not None:
        pytest.skip("textual installed; missing-extra path not applicable")
    with pytest.raises(ConfigurationError) as excinfo:
        run_tui()
    assert "tui" in str(excinfo.value)


# -- MCP serve --------------------------------------------------------------
async def test_build_agent_mcp_server_exposes_ask():
    class FakeApp:
        name = "fake"

        async def answer(self, conversation_id: str, text: str):
            return SimpleNamespace(output=f"echo:{text}")

    server = build_agent_mcp_server(FakeApp())
    tools = await server.list_tools()
    assert "ask" in {tool.name for tool in tools}
