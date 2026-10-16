from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from agentkit.config import AgentSettings
from agentkit.db.migrations import init_db
from agentkit.session import ChatResult
from agentkit.specs import SPECS, SpecKind
from agentkit.specs.codegen import render_spec, targets
from agentkit.specs.eval import EvalDefinition
from agentkit.specs.workflow import WorkflowDefinition
from agentkit.studio import TeamDefinition


def _client(tmp_path):
    from agentkit.runtime import build_runtime
    from agentkit.webui.app import build_webui_app

    settings = AgentSettings(
        agent_home=tmp_path, agent_name="studio", memory_embedding_backend="hash"
    )
    runtime = build_runtime(settings)
    return TestClient(build_webui_app(runtime=runtime, settings=settings))


# -- registry ---------------------------------------------------------------
def test_registry_registers_all_kinds_and_schemas():
    assert set(SPECS.kinds()) == {"agent", "team", "workflow", "eval"}
    for kind in SPECS.kinds():
        schema = SPECS.schema_for(kind)
        assert schema["type"] == "object" and "properties" in schema


def test_validate_round_trips_and_rejects_bad_input():
    from pydantic import ValidationError

    spec = SPECS.validate("team", {"name": "t", "members": [{"name": "a"}]})
    assert isinstance(spec, TeamDefinition)
    assert SPECS.validate("team", spec.model_dump_json()).name == "t"
    with pytest.raises(ValidationError):
        SPECS.validate("team", {"name": ""})


def test_unknown_kind_raises():
    from agentkit.errors import NotFound

    with pytest.raises(NotFound):
        SPECS.schema_for("nope")


# -- materializers / runners ------------------------------------------------
async def test_agent_spec_materializes_and_runs():
    from pydantic_ai.models.test import TestModel

    result = await SPECS.run(
        SpecKind.AGENT, {"name": "greeter", "instructions": "Say hi."}, "hello", model=TestModel()
    )
    assert result["agent"] == "greeter"
    assert result["output"]


async def test_workflow_spec_runs_end_to_end():
    spec = WorkflowDefinition(
        name="wf",
        nodes=[{"name": "a"}, {"name": "b"}],
        edges={"a": "b", "b": "__end__"},
        entry="a",
    )
    result = await SPECS.run("workflow", spec, "go")
    assert result["state"]["last"] == "b"


async def test_eval_spec_runs_suite():
    spec = EvalDefinition(name="smoke", cases=[{"name": "c", "input": "i", "expect": "o"}])

    async def target(text, conversation_id):
        return ChatResult(output="o")

    report = await SPECS.run("eval", spec, target=target)
    assert report.passed


async def test_team_spec_materializes():
    runner = SPECS.materialize("team", {"name": "t", "members": [{"name": "a"}]})
    assert hasattr(runner, "run")


# -- codegen ----------------------------------------------------------------
def test_codegen_targets_render_and_round_trip():
    assert set(targets()) >= {"python", "yaml", "json"}
    definition = TeamDefinition(name="t", members=[{"name": "a"}])
    yaml_text = render_spec(definition, "yaml")
    assert "name: t" in yaml_text
    json_text = render_spec(definition, "json")
    assert json.loads(json_text)["name"] == "t"
    assert "register_team(" in render_spec(definition, "python")
    # Round trip via the registry.
    assert SPECS.validate("team", json_text).name == "t"


def test_state_graph_to_spec_and_from_spec():
    from agentkit.graph import END, StateGraph

    graph = StateGraph()
    graph.add_node("a", lambda state: {"x": 1})
    graph.add_edge("a", END)
    graph.set_entry("a")
    spec = graph.to_spec("g")
    assert [node.name for node in spec.nodes] == ["a"]
    rebuilt = StateGraph.from_spec(spec)
    assert isinstance(rebuilt, StateGraph)


# -- migration back-compat --------------------------------------------------
async def test_team_definitions_copied_to_definitions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'mig.db'}")
    await init_db(engine)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO team_definitions (name, owner_id, kind, definition, created_at, updated_at) "
                "VALUES ('legacy', 'owner', 'groupchat', '{\"name\": \"legacy\"}', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
    await init_db(engine)  # triggers the copy
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT kind, name, spec FROM definitions WHERE name = 'legacy'")
            )
        ).all()
    assert rows and rows[0][0] == "team"
    # Idempotent: a second run does not duplicate.
    await init_db(engine)
    async with engine.connect() as conn:
        count = (
            await conn.execute(
                text("SELECT COUNT(*) FROM definitions WHERE name = 'legacy'")
            )
        ).scalar()
    assert count == 1


def test_legacy_teams_endpoint_sees_migrated_rows(tmp_path):
    client = _client(tmp_path)
    # Create through the legacy endpoint, then confirm the spec store agrees.
    created = client.post(
        "/api/studio/teams", json={"name": "legacy_team", "members": [{"name": "a"}]}
    )
    assert created.status_code == 201
    specs = client.get("/api/studio/specs/team").json()
    assert [item["name"] for item in specs["specs"]] == ["legacy_team"]


# -- spec CRUD endpoints ----------------------------------------------------
def test_spec_crud_code_and_run_endpoints(tmp_path):
    client = _client(tmp_path)
    payload = {"name": "pipeline", "nodes": [{"name": "a"}], "edges": {"a": "__end__"}, "entry": "a"}
    created = client.post("/api/studio/specs/workflow", json=payload)
    assert created.status_code == 201 and created.json()["created"] is True

    listed = client.get("/api/studio/specs/workflow").json()
    assert [item["name"] for item in listed["specs"]] == ["pipeline"]

    code = client.get("/api/studio/specs/workflow/pipeline/code", params={"target": "yaml"}).json()
    assert "pipeline" in code["code"]

    run = client.post("/api/studio/specs/workflow/pipeline/run", json={"prompt": "go"}).json()
    assert run["result"]["state"]["last"] == "a"

    assert client.post("/api/studio/specs/workflow", json={"name": ""}).status_code == 422
    assert client.delete("/api/studio/specs/workflow/pipeline").json()["removed"] is True
    assert client.get("/api/studio/specs/workflow/pipeline").status_code == 404
