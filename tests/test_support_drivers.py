from __future__ import annotations

import pytest

from agentkit.config import AgentSettings
from agentkit.errors import ConfigurationError
from agentkit.foundation import App
from agentkit.foundation.container import Container
from agentkit.foundation.facades import Cache
from agentkit.foundation.jobs import CacheStore, NullCacheStore
from agentkit.support import register_driver
from agentkit.support.drivers import available, parse, register, resolve, unregister


@pytest.fixture
def app(tmp_path):
    return App(settings=AgentSettings(agent_home=tmp_path, cache_driver="array"), discover=False)


# -- registry ---------------------------------------------------------------
def test_driver_registry_register_and_resolve():
    register("demo", "one", lambda app: "one")
    assert resolve("demo", "one") is not None
    assert "one" in available("demo")
    unregister("demo", "one")
    assert resolve("demo", "one") is None


def test_driver_parse_normalises_keys():
    assert parse("cache:redis") == ("cache", "redis")
    assert parse(("Cache", "Redis")) == ("cache", "redis")
    with pytest.raises(ValueError):
        parse("no-colon")


def test_register_driver_decorator():
    @register_driver("demo-decorator", "x")
    def _factory(app):  # noqa: ANN001
        return 123

    assert resolve("demo-decorator", "x")(None) == 123
    unregister("demo-decorator", "x")


# -- manager ----------------------------------------------------------------
def test_manager_resolves_configured_driver_and_caches(app):
    manager = app.manager("cache")
    assert manager.configured_driver() == "array"
    first = manager.driver()
    assert first is manager.driver()
    assert isinstance(first, CacheStore)
    assert {"array", "null"} <= set(manager.available())


def test_manager_create_unknown_raises(app):
    with pytest.raises(ConfigurationError):
        app.manager("cache").create("nope")


def test_manager_extend_overrides_builtin(app):
    manager = app.manager("cache")
    manager.extend("array", lambda app: NullCacheStore())
    assert isinstance(manager.driver(), NullCacheStore)


def test_app_extend_and_drivers_view(app):
    app.extend("cache", "custom", lambda app: NullCacheStore())
    view = app.drivers()
    assert view["cache"]["driver"] == "array"
    assert "custom" in view["cache"]["available"]


def test_cache_driver_setting_selects_null(tmp_path):
    app = App(settings=AgentSettings(agent_home=tmp_path, cache_driver="null"), discover=False)
    assert isinstance(app.cache, NullCacheStore)


def test_cache_facade_resolves_through_manager(app):
    from agentkit.foundation.facade import using

    with using(app):
        Cache.put("k", 5)
        assert Cache.get("k") == 5
        assert Cache.remember("k", lambda: 1) == 5


# -- container --------------------------------------------------------------
def test_container_tags_and_tagged():
    container = Container()
    container.bind("a", lambda c: 1, tag="group")
    container.bind("b", lambda c: 2, tag="group")
    container.bind("c", lambda c: 3)
    assert container.tagged("group") == {"a": 1, "b": 2}


class _Iface:
    pass


class _Impl:
    pass


class _Client:
    def __init__(self, dep: _Iface) -> None:
        self.dep = dep


def test_container_contextual_binding_with_factory():
    container = Container()
    container.bind(_Iface, lambda c: "bound")
    container.when(_Client).needs(_Iface).give(lambda c: "contextual")
    assert container.make(_Client).dep == "contextual"


def test_container_contextual_binding_with_class():
    container = Container()
    container.when(_Client).needs(_Iface).give(_Impl)
    assert isinstance(container.make(_Client).dep, _Impl)
