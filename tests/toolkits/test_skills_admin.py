from __future__ import annotations

from types import SimpleNamespace

from agentkit.deps import Deps
from agentkit.foundation.agent import Agent
from agentkit.skills import SkillRegistry


def _fn(agent, name):
    return agent._function_toolset.tools[name].function


def _ctx(deps: Deps) -> SimpleNamespace:
    return SimpleNamespace(deps=deps)


def _agent():
    return Agent.make("sk").instructions("x").skill_authoring().output(str).build()


def _registry(deps: Deps) -> SkillRegistry:
    return SkillRegistry.from_settings(deps.settings).discover(reload=True)


def test_skill_authoring_approval_flags():
    agent = _agent()
    assert agent._function_toolset.tools["save_skill"].requires_approval is True
    assert agent._function_toolset.tools["update_skill"].requires_approval is True


async def test_save_and_update_skill(tmp_path, deps: Deps):
    deps.settings.skills_dir = str(tmp_path / "skills")
    agent = _agent()
    ctx = _ctx(deps)

    assert "saved skill" in await _fn(agent, "save_skill")(
        ctx, "My New Skill", "does things", "body here"
    )
    skill_md = tmp_path / "skills" / "my-new-skill" / "SKILL.md"
    assert skill_md.is_file()

    skill = _registry(deps).get("my-new-skill")
    assert skill is not None
    assert skill.description == "does things"
    assert skill.body == "body here"

    assert "updated skill" in await _fn(agent, "update_skill")(ctx, "my new skill", "new body")
    updated = _registry(deps).get("my-new-skill")
    assert updated is not None and updated.body == "new body"

    assert await _fn(agent, "update_skill")(ctx, "ghost", "x") == "(no such skill)"
