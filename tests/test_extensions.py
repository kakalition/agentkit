from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from agentkit import Driver
from agentkit.config import AgentSettings
from agentkit.extensions import (
    EXTENSIONS,
    PANELS,
    ExtensionManifest,
    PanelSpec,
    discover_from_env,
    register_panel,
)
from agentkit.foundation import App
from agentkit.runtime import build_runtime
from agentkit.specs import SPECS, SpecModel
from agentkit.webui.app import build_webui_app


class PantryCacheDriver(Driver):
    def build(self):
        return {"pantry": True}


@pytest.fixture(autouse=True)
def _isolate():
    saved = EXTENSIONS.manifests()
    saved_specs = dict(SPECS._entries)
    EXTENSIONS.clear()
    yield
    EXTENSIONS.clear()
    EXTENSIONS.register_manifests(saved)
    SPECS._entries.clear()
    SPECS._entries.update(saved_specs)


def test_manifest_normalises_and_describes():
    class Greeting(SpecModel):
        spec_kind = "greeting"
        name: str

    manifest = ExtensionManifest(
        name="demo",
        version="1.2.0",
        specs=[("greeting", Greeting)],
        panels=[PanelSpec(id="greetings", spec_kind="greeting")],
        actions={"ping": lambda body, ctx: {"pong": True}},
        drivers=[("cache", "pantry", PantryCacheDriver)],
        codegen={"toml": lambda spec: "x"},
    )
    info = manifest.to_dict()
    assert info["name"] == "demo"
    assert info["specs"] == ["greeting"]
    assert info["panels"] == ["greetings"]
    assert info["actions"] == ["ping"]
    assert info["drivers"] == ["cache:pantry"]
    assert info["codegen"] == ["toml"]


def test_conflicting_names_last_wins_with_warning(caplog):
    EXTENSIONS.register_manifest(ExtensionManifest(name="dup", version="1.0.0"))
    with caplog.at_level(logging.WARNING):
        EXTENSIONS.register_manifest(ExtensionManifest(name="dup", version="2.0.0"))
    assert any("registered twice" in record.message for record in caplog.records)
    assert EXTENSIONS.manifests()[0].version == "2.0.0"


def test_boot_applies_specs_panels_and_drivers():
    class Greeting(SpecModel):
        spec_kind = "greeting"
        name: str

    manifest = ExtensionManifest(
        name="demo",
        specs=[("greeting", Greeting)],
        panels=[PanelSpec(id="greetings", spec_kind="greeting")],
        drivers=[("cache", "pantry", PantryCacheDriver)],
    )
    app = App("demo", discover=False).extensions(manifest)
    app.boot()
    assert "greeting" in SPECS.kinds()
    assert PANELS.get("greetings") is not None
    assert app.manager("cache").create("pantry") == {"pantry": True}
    assert app.extension_info()[0]["name"] == "demo"
    # Re-booting is idempotent.
    app.boot()


def test_broken_manifest_does_not_break_boot():
    bad = ExtensionManifest(name="bad", panels=[{"id": ""}])
    app = App("demo", discover=False).extensions(bad)
    app.boot()  # must not raise
    assert app.extension_info() == []


def test_broken_factory_is_skipped_not_fatal():
    def boom():
        raise RuntimeError("nope")

    app = App("demo", discover=False).extensions(boom)
    app.boot()
    assert app.extension_info() == []


def test_discover_from_env(monkeypatch):
    import sys
    import types

    module = types.ModuleType("agentkit.extensions.demo_manifest")
    module.manifest = ExtensionManifest(name="env-demo")
    monkeypatch.setitem(sys.modules, "agentkit.extensions.demo_manifest", module)
    monkeypatch.setenv("AGENTKIT_EXTENSIONS", "agentkit.extensions.demo_manifest:manifest")
    manifests = discover_from_env()
    assert [m.name for m in manifests] == ["env-demo"]


def test_studio_extension_and_panel_endpoints(tmp_path):
    register_panel(PanelSpec(id="custom", title="Custom", order=999))
    settings = AgentSettings(agent_home=tmp_path, agent_name="studio", memory_embedding_backend="hash")
    runtime = build_runtime(settings)
    client = TestClient(build_webui_app(runtime=runtime, settings=settings))

    panels = client.get("/api/studio/panels").json()["panels"]
    assert any(panel["id"] == "custom" for panel in panels)
    assert {"agents", "teams", "workflows", "evals", "catalog", "traces", "playground"} <= {
        panel["id"] for panel in panels
    }

    specs = client.get("/api/studio/specs").json()
    assert set(specs["kinds"]) == {"agent", "team", "workflow", "eval"}
    assert specs["specs"]["team"]["type"] == "object"

    assert "extensions" in client.get("/api/studio/extensions").json()
    assert client.get("/api/studio/app").json()["name"] == "studio"


def test_action_endpoint_invokes_and_404s(tmp_path):
    from agentkit.extensions.actions import ACTIONS, register_action

    register_action("echo")(lambda body, ctx: {"hello": body.get("who", "world")})
    settings = AgentSettings(agent_home=tmp_path, memory_embedding_backend="hash")
    runtime = build_runtime(settings)
    client = TestClient(build_webui_app(runtime=runtime, settings=settings))

    result = client.post("/api/studio/actions/echo", json={"who": "ada"}).json()
    assert result["result"] == {"hello": "ada"}
    assert client.post("/api/studio/actions/missing", json={}).status_code == 404
    ACTIONS.clear()
