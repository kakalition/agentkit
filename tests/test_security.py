from __future__ import annotations

from types import SimpleNamespace

from agentkit.config import AgentSettings
from agentkit.deps import Deps
from agentkit.foundation import App
from agentkit.runtime import build_deps, build_runtime, repositories
from agentkit.security import API_KEY, Actor, system_actor
from agentkit.webui.context import WebUIContext, get_actor


def test_actor_roles_and_provenance():
    actor = Actor(owner_id="o", subject="s", roles=frozenset({"admin"}), method=API_KEY)
    assert actor.authenticated is True
    assert actor.has_role("admin")
    assert not actor.has_role("user")
    assert actor.has_role()
    assert actor.with_roles("user").roles == frozenset({"admin", "user"})


def test_system_actor_defaults():
    settings = AgentSettings(owner_id="acme")
    actor = system_actor(settings)
    assert actor.owner_id == "acme"
    assert actor.method == "none"
    assert actor.authenticated is False


def test_deps_owner_id_prefers_actor(tmp_path):
    settings = AgentSettings(owner_id="acme", agent_home=tmp_path)
    assert Deps(settings=settings).owner_id == "acme"
    deps = Deps(settings=settings, actor=Actor(owner_id="tenant-b", method=API_KEY))
    assert deps.owner_id == "tenant-b"


async def test_repositories_explicit_owner(runtime):
    async with repositories(runtime, "other-owner") as repos:
        assert repos.owner_id == "other-owner"
    async with repositories(runtime) as repos:
        assert repos.owner_id == "owner"


async def test_build_deps_threads_actor(runtime, repos):
    actor = Actor(owner_id="tenant-b", roles=frozenset({"admin"}), method=API_KEY)
    deps = build_deps(runtime, repos, actor=actor)
    assert deps.actor is actor
    assert deps.owner_id == "tenant-b"


async def test_app_deps_sets_actor(runtime, repos):
    app = App(name="test", settings=runtime.settings, discover=False, model=object())
    app._runtime = runtime
    actor = Actor(owner_id="tenant-b", method=API_KEY)
    deps = app.deps(repos, actor=actor)
    assert deps.actor is actor
    assert deps.owner_id == "tenant-b"


def test_get_actor_defaults_to_settings_owner(tmp_path):
    settings = AgentSettings(owner_id="acme", agent_home=tmp_path)
    runtime = build_runtime(settings)
    ctx = WebUIContext(runtime=runtime, settings=settings)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(webui=ctx)), state=SimpleNamespace()
    )
    actor = get_actor(request)
    assert actor.owner_id == "acme"
    assert actor.method == "none"
