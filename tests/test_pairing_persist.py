"""T3 — repository-backed gateway pairing (persistent) + PairingDriver."""

from __future__ import annotations

from typing import Any

from agentkit.foundation.application import App
from agentkit.foundation.facade import using
from agentkit.gateways.base import Gateway
from agentkit.gateways.pairing import PairingRegistry, RepositoryPairingRegistry
from agentkit.runtime import Runtime


class _Gateway(Gateway):
    name = "test"

    async def start(self) -> None:  # pragma: no cover - never started here
        return None

    async def send(self, conversation_id: str, text: str) -> None:  # pragma: no cover
        return None


def _app(runtime: Runtime, **updates: Any) -> App:
    settings = runtime.settings.model_copy(update=updates) if updates else runtime.settings
    app = App(name="pairing", settings=settings, discover=False)
    app._runtime = runtime
    return app


def test_default_registry_is_memory(runtime: Runtime) -> None:
    app = _app(runtime)
    with using(app):
        assert app.manager("pairing").configured_driver() == "memory"
        assert isinstance(app.pairing, PairingRegistry)


def test_repository_registry_survives_a_new_instance(runtime: Runtime) -> None:
    app = _app(runtime, pairing_driver="repository")
    with using(app):
        registry = app.pairing
        assert isinstance(registry, RepositoryPairingRegistry)
        code = registry.request("u1")
        assert registry.is_paired("u1") is False
        assert registry.confirm("u1", "999999") is False
        assert registry.confirm("u1", code) is True
        assert registry.is_paired("u1") is True
    # a fresh registry/scope (simulated restart) still sees the committed pairing
    restarted = RepositoryPairingRegistry(app)
    assert restarted.is_paired("u1") is True
    assert restarted.paired() == ["u1"]
    assert restarted.unpair("u1") is True
    assert restarted.is_paired("u1") is False


def test_scope_isolates_external_ids(runtime: Runtime) -> None:
    app = _app(runtime, pairing_driver="repository")
    telegram = RepositoryPairingRegistry(app, scope="telegram")
    slack = RepositoryPairingRegistry(app, scope="slack")
    code = telegram.request("42")
    assert telegram.confirm("42", code) is True
    assert telegram.is_paired("42") is True
    assert slack.is_paired("42") is False


def test_expired_code_is_rejected(runtime: Runtime) -> None:
    app = _app(runtime, pairing_driver="repository")
    registry = RepositoryPairingRegistry(app, code_ttl_s=-1.0)
    code = registry.request("u")
    assert registry.confirm("u", code) is False
    assert registry.is_paired("u") is False


def test_gateway_pairing_is_opt_in(runtime: Runtime) -> None:
    app = _app(runtime)
    with using(app):
        gateway = _Gateway(app)
        assert gateway.pairing is None
        assert gateway.is_allowed("anyone") is True


def test_gateway_uses_repository_pairing_when_enabled(runtime: Runtime) -> None:
    app = _app(runtime, channel_pairing_enabled=True, pairing_driver="repository")
    with using(app):
        first = _Gateway(app)
        assert isinstance(first.pairing, RepositoryPairingRegistry)
        code = first.pair("u9")
        assert first.confirm_pairing("u9", code) is True
        second = _Gateway(app)
        assert second.is_allowed("u9") is True
        assert second.is_allowed("stranger") is False
