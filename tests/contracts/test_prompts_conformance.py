from __future__ import annotations

import pytest
from conformance import prompt_conformance

from agentkit.config import AgentSettings
from agentkit.foundation import App

DRIVERS = ["file", "memory"]


@pytest.fixture
def app(tmp_path):
    return App(settings=AgentSettings(agent_home=tmp_path), discover=False)


@pytest.mark.parametrize("name", DRIVERS)
def test_prompt_driver_conforms(app, name):
    prompt_conformance(app.manager("prompts").create(name))


def test_default_prompt_driver_is_file(app):
    assert app.manager("prompts").configured_driver() == "file"
