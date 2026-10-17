"""WS6 — Gate/Policy integration: registration, discovery, tool policy, helpers."""

from __future__ import annotations

from typing import Any

import pytest

from agentkit import App, GateManager, PermissionDenied, Policy, Provider
from agentkit.foundation.facade import using
from agentkit.policy import ToolPolicy
from agentkit.runtime import Runtime


class Doc:
    def __init__(self, owner: str) -> None:
        self.owner = owner


class DocPolicy(Policy):
    model = Doc

    def view(self, actor: Any, doc: Doc) -> bool:
        return doc.owner == actor

    def update(self, actor: Any, doc: Doc) -> bool:
        return doc.owner == actor


def _app(runtime: Runtime) -> App:
    app = App(name="gate", settings=runtime.settings, discover=False)
    app._runtime = runtime
    app.boot()
    return app


def test_app_registers_policy_class(runtime: Runtime) -> None:
    app = _app(runtime)
    app.policies([DocPolicy])
    assert app.gate.allows("view", Doc("ada"), actor="ada") is True
    assert app.gate.denies("update", Doc("bob"), actor="ada") is True


def test_provider_contributes_policies(runtime: Runtime) -> None:
    class DocProvider(Provider):
        def register(self, app: App) -> None:  # noqa: ARG002
            return None

        def policies(self) -> list[Any]:
            return [DocPolicy]

    app = App(name="gate", settings=runtime.settings, discover=False)
    app.providers([DocProvider])
    app.boot()
    assert app.gate.allows("view", Doc("ada"), actor="ada") is True


def test_tool_policy_integration(runtime: Runtime) -> None:
    app = _app(runtime)
    app.tool_policy(ToolPolicy(deny={"danger"}, require_approval={"write"}))
    assert app.gate.allows("run", "safe") is True
    assert app.gate.denies("run", "danger") is True
    assert app.gate.can_run("danger") is False
    assert app.gate.can_run("safe") is True
    # approval-gated tools are not outright denied
    assert app.gate.allows("run", "write") is True


def test_helpers_can_authorize_policy(runtime: Runtime) -> None:
    from agentkit import authorize, can, policy

    app = _app(runtime)
    with using(app):
        policy(Doc, DocPolicy)
        assert can("view", Doc("ada"), actor="ada") is True
        with pytest.raises(PermissionDenied):
            authorize("view", Doc("bob"), actor="ada")


def test_gate_tool_policy_adapter_default_negative() -> None:
    gate = GateManager()
    gate.tool_policy(ToolPolicy(allow={"ok"}))
    assert gate.allows("run", "ok") is True
    assert gate.allows("run", "other") is False
