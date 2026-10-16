from __future__ import annotations

import pytest

from agentkit.catalog import (
    CATALOGS,
    DefinitionsTarget,
    HttpCatalog,
    LocalCatalog,
    SkillsCatalog,
    register_catalog_source,
)
from agentkit.config import AgentSettings
from agentkit.contracts import Catalog
from agentkit.foundation import App
from agentkit.runtime import build_runtime, repositories


def _write_catalog(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "greeter.json").write_text(
        '{"name": "greeter", "spec_kind": "agent", "instructions": "hi"}', encoding="utf-8"
    )
    (root / "team1.json").write_text(
        '{"name": "squad", "spec_kind": "team", "members": [{"name": "a"}]}', encoding="utf-8"
    )


async def test_local_catalog_search_and_get(tmp_path):
    _write_catalog(tmp_path / "catalog")
    catalog = LocalCatalog(tmp_path / "catalog")
    assert isinstance(catalog, Catalog)
    items = await catalog.search("")
    assert {item.id for item in items} == {"greeter", "team1"}
    assert (await catalog.get("greeter")).kind == "agent"
    assert await catalog.get("missing") is None


async def test_local_catalog_install_into_definitions(tmp_path):
    _write_catalog(tmp_path / "catalog")
    runtime = build_runtime(
        AgentSettings(agent_home=tmp_path, memory_embedding_backend="hash")
    )
    catalog = LocalCatalog(tmp_path / "catalog")
    async with repositories(runtime) as repos:
        from agentkit.specs import RepositorySpecStore

        target = DefinitionsTarget(RepositorySpecStore(repos))
        result = await catalog.install("team1", target)
        assert result["installed"] is True and result["kind"] == "team"
        record = await repos.definitions.get("team", "squad")
        assert record is not None
        # Idempotent: installing again updates in place.
        await catalog.install("team1", target)
        records = await repos.definitions.list("team")
        assert len(records) == 1


async def test_skills_catalog_lists_and_installs(tmp_path):
    skills = tmp_path / "skills"
    (skills / "writer").mkdir(parents=True)
    (skills / "writer" / "SKILL.md").write_text("# Writer\n", encoding="utf-8")
    catalog = SkillsCatalog(skills)
    items = await catalog.search("")
    assert [item.id for item in items] == ["writer"]
    result = await catalog.install("writer", None)
    assert result["installed"] is False


def test_register_catalog_source():
    register_catalog_source("custom", lambda app: {"ok": True})
    assert "custom" in CATALOGS


async def test_http_catalog_with_a_local_server(monkeypatch):
    index = {"items": [{"id": "one", "kind": "agent", "description": "first"}]}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return index

        @property
        def text(self):
            return "{}"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):
            return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    catalog = HttpCatalog("https://index.test/catalog.json")
    items = await catalog.search("first")
    assert [item.id for item in items] == ["one"]


def test_catalog_manager_requires_nothing(tmp_path):
    app = App(settings=AgentSettings(agent_home=tmp_path), discover=False)
    assert isinstance(app.manager("catalog").driver(), LocalCatalog)


@pytest.mark.parametrize("driver", ["local", "skills", "http", "git"])
def test_catalog_drivers_construct(tmp_path, driver):
    app = App(settings=AgentSettings(agent_home=tmp_path), discover=False)
    assert app.manager("catalog").create(driver) is not None


def test_catalog_endpoints(tmp_path):
    from fastapi.testclient import TestClient

    from agentkit.webui.app import build_webui_app

    catalog_dir = tmp_path / "catalog"
    _write_catalog(catalog_dir)
    settings = AgentSettings(
        agent_home=tmp_path,
        memory_embedding_backend="hash",
        catalog_dir=str(catalog_dir),
    )
    runtime = build_runtime(settings)
    client = TestClient(build_webui_app(runtime=runtime, settings=settings))

    listing = client.get("/api/studio/catalog", params={"q": "team"}).json()
    assert [item["id"] for item in listing["items"]] == ["team1"]

    installed = client.post("/api/studio/catalog/team1/install", json={"into": "definitions"}).json()
    assert installed["installed"] is True and installed["kind"] == "team"
    assert client.post("/api/studio/catalog/missing/install", json={}).status_code == 404

    specs = client.get("/api/studio/specs/team").json()
    assert [item["name"] for item in specs["specs"]] == ["squad"]
