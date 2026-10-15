from __future__ import annotations

import pytest
from conformance import cache_conformance

from agentkit.config import AgentSettings
from agentkit.foundation import App

DRIVERS = ["array", "null"]


@pytest.fixture
def app(tmp_path):
    return App(settings=AgentSettings(agent_home=tmp_path), discover=False)


@pytest.mark.parametrize("name", DRIVERS)
def test_cache_driver_conforms(app, name):
    cache_conformance(app.manager("cache").create(name))


def test_default_cache_is_array(app):
    from agentkit.foundation.jobs import CacheStore

    assert isinstance(app.manager("cache").driver(), CacheStore)
