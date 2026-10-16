from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agentkit import scheduler
from agentkit.agents.handle import AgentHandle
from agentkit.agents.registry import AgentRegistry
from agentkit.agents.speaker import AllSpeaker, ModeratorSpeaker, RoundRobinSpeaker
from agentkit.config import AgentSettings
from agentkit.runtime import build_runtime
from agentkit.studio import (
    TeamDefinition,
    TeamMember,
    materialize_team,
    render_team_code,
    resolve_from_app,
    run_team_definition,
    speaker_for,
)
from agentkit.webui.app import build_webui_app


@pytest.fixture(autouse=True)
def _reset_scheduler():
    old = scheduler._runtime
    scheduler._runtime = None
    yield
    scheduler._runtime = old


# -- definition validation --------------------------------------------------
def test_definition_validates_kind_speaker_and_members():
    with pytest.raises(ValidationError):
        TeamDefinition(name="x", kind="bogus")
    with pytest.raises(ValidationError):
        TeamDefinition(name="x", speaker="bogus")
    with pytest.raises(ValidationError):
        TeamDefinition(name="x", members=[TeamMember(name="a"), TeamMember(name="a")])
    with pytest.raises(ValidationError):
        TeamDefinition(name="x", members=[TeamMember(name="a")], moderator="b")
    with pytest.raises(ValidationError):
        TeamDefinition(name="x", members=[TeamMember(name="a")], manual_order=["b"])


def test_speaker_for_maps_strategies():
    assert isinstance(speaker_for(TeamDefinition(name="x")), RoundRobinSpeaker)
    assert isinstance(speaker_for(TeamDefinition(name="x", speaker="all")), AllSpeaker)
    moderate = TeamDefinition(
        name="x", speaker="moderator", members=[TeamMember(name="m")], moderator="m"
    )
    assert isinstance(speaker_for(moderate), ModeratorSpeaker)
    supervisor = TeamDefinition(name="x", kind="supervisor", members=[TeamMember(name="m")])
    assert isinstance(speaker_for(supervisor), ModeratorSpeaker)


# -- materialize / run ------------------------------------------------------
async def test_run_definition_groupchat():
    definition = TeamDefinition(
        name="squad", members=[TeamMember(name="a"), TeamMember(name="b")], max_turns=2
    )
    result = await run_team_definition(definition, "go")
    assert result["team"] == "squad" and result["kind"] == "groupchat"
    assert [turn["speaker"] for turn in result["transcript"]] == ["user", "a", "b"]
    assert result["rounds"] == 2
    assert "not a registered agent" in result["output"]
    assert result["ledger"] is None


async def test_run_definition_managed_returns_ledger():
    definition = TeamDefinition(
        name="crew", kind="managed", members=[TeamMember(name="a")], max_rounds=1
    )
    result = await run_team_definition(definition, "task")
    assert result["ledger"] is not None
    assert any("Task: task" in fact for fact in result["ledger"]["facts"])


async def test_resolve_from_registry_binds_live_member():
    class FakeAgent:
        async def run(self, task, *, deps=None, usage=None, model=None):  # noqa: ANN001, ANN003
            return SimpleNamespace(output="from-tool")

    registry = AgentRegistry()
    handle = registry.register(AgentHandle.local(FakeAgent(), name="tool"))

    definition = TeamDefinition(name="t", members=[TeamMember(name="tool")], max_turns=1)
    result = await run_team_definition(
        definition, "hi", resolve=resolve_from_app(SimpleNamespace(_agent_registry=registry))
    )
    assert result["output"] == "from-tool"
    resolve = resolve_from_app(SimpleNamespace(_agent_registry=registry))
    assert resolve("tool") is handle
    assert callable(resolve("missing"))


def test_materialize_team_kind():
    from agentkit.agents.groupchat import GroupChatRunner
    from agentkit.agents.team import ManagedTeam

    assert isinstance(materialize_team(TeamDefinition(name="g")), GroupChatRunner)
    assert isinstance(materialize_team(TeamDefinition(name="m", kind="managed")), ManagedTeam)


# -- python export ----------------------------------------------------------
def test_render_team_code_contains_registration_and_tool():
    definition = TeamDefinition(
        name="squad",
        kind="supervisor",
        members=[TeamMember(name="a", description="planner"), TeamMember(name="b")],
        max_turns=3,
    )
    code = render_team_code(definition)
    assert "register_team(" in code
    assert "'a'" in code and "kind='supervisor'" in code
    assert "build_team('squad', max_turns=3)" in code
    assert "team('squad')" in code
    assert "team_squad" in code


# -- webui studio API -------------------------------------------------------
def _client(tmp_path):
    settings = AgentSettings(agent_home=tmp_path, agent_name="studio", memory_embedding_backend="hash")
    runtime = build_runtime(settings)
    return TestClient(build_webui_app(runtime=runtime, settings=settings))


def test_studio_crud_run_and_code(tmp_path):
    client = _client(tmp_path)
    body = {
        "name": "studio_squad",
        "kind": "groupchat",
        "members": [{"name": "a"}, {"name": "b"}],
        "max_turns": 2,
    }
    created = client.post("/api/studio/teams", json=body)
    assert created.status_code == 201 and created.json()["created"] is True

    listed = client.get("/api/studio/teams").json()
    assert [team["name"] for team in listed["teams"]] == ["studio_squad"]
    assert "groupchat" in listed["kinds"] and "round_robin" in listed["speakers"]
    assert listed["teams"][0]["registered"] is False

    code = client.get("/api/studio/teams/studio_squad/code").json()["code"]
    assert "register_team(" in code

    run = client.post("/api/studio/teams/studio_squad/run", json={"prompt": "go"}).json()
    assert run["team"] == "studio_squad"
    assert [turn["speaker"] for turn in run["transcript"]] == ["user", "a", "b"]

    activated = client.post("/api/studio/teams/studio_squad/activate").json()
    assert activated["registered"] is True and activated["tool"] == "team_studio_squad"
    assert client.get("/api/studio/teams").json()["teams"][0]["registered"] is True

    assert client.delete("/api/studio/teams/studio_squad").json()["removed"] is True
    assert client.get("/api/studio/teams/studio_squad/code").status_code == 404


def test_studio_rejects_invalid_definition(tmp_path):
    client = _client(tmp_path)
    assert client.post("/api/studio/teams", json={"name": "x", "kind": "bogus"}).status_code == 422
    assert client.post("/api/studio/teams/x/run", json={"prompt": "hi"}).status_code == 404
