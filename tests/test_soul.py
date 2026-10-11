from __future__ import annotations

from agentkit.config import AgentSettings
from agentkit.soul import DEFAULT_SOUL, compose_instructions, ensure_soul, load_soul, soul_path


def test_load_soul_default_when_missing(tmp_path):
    settings = AgentSettings(agent_home=tmp_path)
    assert load_soul(settings) == DEFAULT_SOUL
    assert soul_path(settings) == tmp_path / "SOUL.md"


def test_ensure_soul_creates_file(tmp_path):
    settings = AgentSettings(agent_home=tmp_path)
    path = ensure_soul(settings)
    assert path.exists()
    path.write_text("# Soul\n\nCustom persona.", encoding="utf-8")
    assert load_soul(settings) == "# Soul\n\nCustom persona."


def test_soul_file_override(tmp_path):
    custom = tmp_path / "custom-soul.md"
    custom.write_text("You are custom.", encoding="utf-8")
    settings = AgentSettings(agent_home=tmp_path / "home", soul_file=str(custom))
    assert load_soul(settings) == "You are custom."


def test_compose_instructions():
    text = compose_instructions("persona", "routes")
    assert text.startswith("persona")
    assert text.endswith("routes")
    assert compose_instructions("persona", None) == "persona"
