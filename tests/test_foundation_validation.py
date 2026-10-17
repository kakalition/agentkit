"""WS5 — validation integration: DB-backed ``unique``/``exists`` rules."""

from __future__ import annotations

from sqlmodel import Field

from agentkit import App, Model, Rule, Validator
from agentkit.runtime import Runtime


class UniqueWidget(Model, table=True):
    __tablename__ = "ws5_unique_widgets"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="", index=True)


def _app(runtime: Runtime) -> App:
    app = App(name="validation", settings=runtime.settings, discover=False)
    app._runtime = runtime
    app.boot()
    return app


def test_sync_rules_still_work() -> None:
    assert Validator({"text": "stretch"}, {"text": ["required", "min:3"]}).passes()
    assert Validator({"text": ""}, {"text": ["required"]}).fails()


async def test_unique_rule_backed_by_repositories(runtime: Runtime) -> None:
    _app(runtime)
    await UniqueWidget.create(name="taken")

    assert Validator({"name": "free"}, {"name": [Rule.unique(UniqueWidget, "name")]}).passes()
    failing = Validator({"name": "taken"}, {"name": [Rule.unique(UniqueWidget, "name")]})
    assert failing.fails()
    assert "taken" in failing.first("name")


async def test_exists_rule_backed_by_repositories(runtime: Runtime) -> None:
    _app(runtime)
    await UniqueWidget.create(name="present")

    assert Validator({"name": "present"}, {"name": [Rule.exists(UniqueWidget, "name")]}).passes()
    assert Validator({"name": "absent"}, {"name": [Rule.exists(UniqueWidget, "name")]}).fails()


def test_validates_input_mixin() -> None:
    from agentkit import ValidatesInput

    class Handler(ValidatesInput):
        rules = {"text": ["required", "min:3"]}

    assert Handler().validate_input({"text": "stretch"}) == {"text": "stretch"}
    import pytest

    with pytest.raises(Exception):  # noqa: B017 - ValidationError
        Handler().validate_input({"text": ""})
