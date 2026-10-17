from __future__ import annotations

from pathlib import Path

import pytest

from agentkit import Posture
from agentkit.config import AgentSettings
from agentkit.foundation.agent import Agent
from agentkit.policy import ALLOW, APPROVE, DENY, free_policy, specialized_policy
from agentkit.posture import (
    PostureProfile,
    apply_settings_overrides,
    register_posture,
    resolve_posture,
)


def _settings(tmp_path: Path, **overrides) -> AgentSettings:
    return AgentSettings(agent_home=tmp_path, memory_embedding_backend="hash", **overrides)


def _tools(builder: Agent, settings: AgentSettings) -> set[str]:
    built = builder.build(settings=settings)
    return set(built._function_toolset.tools.keys())


def test_default_posture_is_hybrid(tmp_path: Path):
    settings = _settings(tmp_path)
    assert settings.agent_posture == Posture.HYBRID
    profile = resolve_posture(settings.agent_posture)
    assert profile is not None and profile.name is Posture.HYBRID
    assert profile.preamble == ""


def test_hybrid_full_matches_unpostured_full(tmp_path: Path):
    settings = _settings(tmp_path)
    plain = Agent.make("a").instructions("x").output(str).full(settings=settings)
    hybrid = Agent.make("a").instructions("x").output(str).posture("hybrid").full(settings=settings)
    assert _tools(plain, settings) == _tools(hybrid, settings)
    assert plain.policies[0].decision("run_command") == hybrid.policies[0].decision("run_command")
    assert plain._instruction_parts == hybrid._instruction_parts == ["x"]


def test_specialized_policy_denies_egress_and_code():
    policy = specialized_policy()
    for tool in ("web_search", "web_fetch", "x_search", "run_code", "send_email", "send_to", "broadcast"):
        assert policy.decision(tool) == DENY
    assert policy.decision("write_file") == APPROVE
    assert policy.decision("read_file") == ALLOW


def test_free_policy_only_gates_destructive():
    policy = free_policy()
    assert policy.decision("delete_file") == APPROVE
    assert policy.decision("send_email") == APPROVE
    assert policy.decision("write_file") == ALLOW
    assert policy.decision("run_code") == ALLOW


def test_specialized_full_is_constrained(tmp_path: Path):
    settings = _settings(tmp_path)
    builder = Agent.make("a").instructions("x").output(str).specialized().full(settings=settings)
    tools = _tools(builder, settings)
    assert "remember" not in tools  # memory off
    assert "ask_user" in tools  # hitl on
    assert builder.policies[0].decision("run_code") == DENY
    assert builder._instruction_parts[0].startswith("You are a focused specialist")


def test_free_full_enables_autonomy(tmp_path: Path):
    settings = _settings(tmp_path)
    builder = Agent.make("a").instructions("x").output(str).free().full(settings=settings)
    tools = _tools(builder, settings)
    assert "remember" in tools  # memory on
    assert "run_command" in tools  # workspace on
    assert "run_code" in tools  # code on
    assert "egress" in builder._full_layers  # web search + fetch
    assert builder._instruction_parts[0].startswith("You are an autonomous generalist")


def test_explicit_arg_beats_posture(tmp_path: Path):
    settings = _settings(tmp_path)
    builder = (
        Agent.make("a")
        .instructions("x")
        .output(str)
        .specialized()
        .full(memory=True, settings=settings)
    )
    assert "remember" in _tools(builder, settings)


def test_settings_flag_vetoes_posture(tmp_path: Path):
    settings = _settings(tmp_path, memory_enabled=False)
    builder = Agent.make("a").instructions("x").output(str).free().full(settings=settings)
    assert "remember" not in _tools(builder, settings)


def test_posture_comes_from_settings(tmp_path: Path):
    settings = _settings(tmp_path, agent_posture=Posture.SPECIALIZED)
    builder = Agent.make("a").instructions("x").output(str).full(settings=settings)
    assert builder.policies[0].decision("run_code") == DENY


def test_register_and_resolve_custom_posture():
    profile = PostureProfile(name=Posture.HYBRID, preamble="custom", layers={"todos": False})
    register_posture("custom", profile)
    assert resolve_posture("custom") is profile
    with pytest.raises(ValueError):
        resolve_posture("does-not-exist")


def test_scaffold_posture_option(tmp_path: Path):
    from agentkit import scaffold_project

    target = scaffold_project("postured", tmp_path, posture="free")
    assistant = (target / "app" / "Agents" / "assistant.py").read_text()
    assert 'posture = "free"' in assistant
    with pytest.raises(ValueError):
        scaffold_project("bad", tmp_path, posture="bogus")


# -- settings overrides -----------------------------------------------------
def test_free_posture_overrides_defaulted_settings(tmp_path: Path):
    settings = _settings(tmp_path)
    updated = apply_settings_overrides(settings, resolve_posture("free"))
    assert updated is not settings
    assert updated.tool_output_offload_threshold == 4000
    assert updated.memory_nudge_every == 10
    # the original is untouched
    assert settings.tool_output_offload_threshold == 0
    assert settings.memory_nudge_every == 0


def test_operator_value_beats_posture_override(tmp_path: Path):
    settings = _settings(tmp_path, memory_nudge_every=3)
    updated = apply_settings_overrides(settings, resolve_posture("free"))
    assert updated.memory_nudge_every == 3  # operator value wins
    assert updated.tool_output_offload_threshold == 4000  # still defaulted -> overridden


def test_hybrid_and_specialized_settings_unchanged(tmp_path: Path):
    settings = _settings(tmp_path)
    assert apply_settings_overrides(settings, resolve_posture("hybrid")) is settings
    assert apply_settings_overrides(settings, resolve_posture("specialized")) is settings
    assert apply_settings_overrides(settings, None) is settings


def test_boot_applies_posture_settings(tmp_path: Path):
    from agentkit.foundation.application import App

    settings = _settings(tmp_path, agent_posture="free")
    app = App(name="free-app", settings=settings, discover=False)
    app.boot()
    assert app.settings.tool_output_offload_threshold == 4000
    assert app.settings.memory_nudge_every == 10


def test_boot_hybrid_leaves_settings_identity(tmp_path: Path):
    from agentkit.foundation.application import App

    settings = _settings(tmp_path)
    app = App(name="hybrid-app", settings=settings, discover=False)
    app.boot()
    assert app.settings is settings
