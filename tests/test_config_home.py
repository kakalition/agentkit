from __future__ import annotations

from agentkit.config import AgentSettings
from agentkit.workspace import default_workspace_root


def test_agent_home_defaults_under_workspace_root(tmp_path):
    settings = AgentSettings(workspace_root=tmp_path, agent_name="calliope")
    assert settings.home == tmp_path / "calliope"
    assert settings.db_path == tmp_path / "calliope" / "agent.db"
    assert settings.artifacts_dir == tmp_path / "calliope" / "artifacts"


def test_explicit_agent_home_wins(tmp_path):
    settings = AgentSettings(
        workspace_root=tmp_path / "ws", agent_home=tmp_path / "elsewhere", agent_name="x"
    )
    assert settings.home == tmp_path / "elsewhere"


def test_agent_home_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_HOME", str(tmp_path / "custom"))
    settings = AgentSettings()
    assert settings.home == tmp_path / "custom"


def test_workspace_root_env_override(monkeypatch, tmp_path):
    monkeypatch.delenv("AGENT_HOME", raising=False)
    monkeypatch.setenv("AGENTKIT_HOME", str(tmp_path / "ws"))
    settings = AgentSettings(agent_name="artemis")
    assert settings.home == tmp_path / "ws" / "artemis"


def test_default_workspace_root_is_dot_agentkit():
    assert default_workspace_root() == default_workspace_root().expanduser()
    assert default_workspace_root().name == ".agentkit"


def test_ensure_dirs_creates_logs(tmp_path):
    settings = AgentSettings(workspace_root=tmp_path, agent_name="a")
    settings.ensure_dirs()
    assert (tmp_path / "a" / "logs").is_dir()
