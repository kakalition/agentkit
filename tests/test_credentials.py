from __future__ import annotations

import asyncio

import pytest
from cryptography.fernet import Fernet
from typer.testing import CliRunner

from agentkit.cli import app as cli_app
from agentkit.config import AgentSettings, get_settings
from agentkit.runtime import build_runtime
from agentkit.security.credentials import (
    Credentials,
    VaultError,
    build_cipher,
    hydrate_credentials,
)


def _settings(tmp_path, key: str, **over):
    return AgentSettings(
        owner_id="owner",
        agent_home=tmp_path,
        memory_embedding_backend="hash",
        credentials_enabled=True,
        credentials_key=key,
        **over,
    )


def test_build_cipher_modes():
    assert build_cipher(AgentSettings(owner_id="o")) is None
    raw = Fernet.generate_key().decode()
    assert build_cipher(_settings_key(raw)) is not None
    # an arbitrary passphrase is derived into a valid key
    assert build_cipher(_settings_key("a passphrase")) is not None


def _settings_key(key: str) -> AgentSettings:
    return AgentSettings(owner_id="o", credentials_enabled=True, credentials_key=key)


def test_vault_requires_key(tmp_path):
    settings = AgentSettings(owner_id="o", agent_home=tmp_path, credentials_enabled=True)
    vault = Credentials(build_runtime(settings))
    with pytest.raises(VaultError):
        vault.encrypt("x")


async def test_vault_roundtrip_encrypts_at_rest(tmp_path):
    key = Fernet.generate_key().decode()
    runtime = build_runtime(_settings(tmp_path, key))
    vault = Credentials(runtime)

    await vault.set("telegram_bot_token", "tok-123", metadata='{"note": "tg"}')
    assert await vault.get("telegram_bot_token") == "tok-123"
    assert await vault.names() == ["telegram_bot_token"]

    from agentkit.runtime import repositories

    async with repositories(runtime) as repos:
        row = await repos.credentials.get("telegram_bot_token")
    assert row is not None
    assert row.ciphertext != "tok-123"
    assert vault.decrypt(row.ciphertext) == "tok-123"

    # upsert keeps a single row
    await vault.set("telegram_bot_token", "tok-456")
    assert await vault.names() == ["telegram_bot_token"]
    assert await vault.get("telegram_bot_token") == "tok-456"

    assert await vault.delete("telegram_bot_token") is True
    assert await vault.delete("telegram_bot_token") is False
    assert await vault.names() == []


def test_hydrate_credentials_prefers_vault(tmp_path):
    key = Fernet.generate_key().decode()
    runtime = build_runtime(_settings(tmp_path, key))
    asyncio.run(Credentials(runtime).set("telegram_bot_token", "vault-tok"))

    hydrated_settings = _settings(tmp_path, key)
    hydrated = hydrate_credentials(hydrated_settings, runtime)
    assert "telegram_bot_token" in hydrated
    assert hydrated_settings.telegram_bot_token == "vault-tok"

    # an env-provided value wins over the vault
    env_settings = _settings(tmp_path, key, telegram_bot_token="env-tok")
    assert hydrate_credentials(env_settings, runtime) == []
    assert env_settings.telegram_bot_token == "env-tok"


def test_cli_credentials_lifecycle(tmp_path, monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MEMORY_EMBEDDING_BACKEND", "hash")
    monkeypatch.setenv("CREDENTIALS_ENABLED", "true")
    monkeypatch.setenv("CREDENTIALS_KEY", key)
    get_settings.cache_clear()
    runner = CliRunner()

    stored = runner.invoke(
        cli_app, ["credentials:set", "telegram_bot_token", "--value", "tok-xyz"]
    )
    assert stored.exit_code == 0, stored.output
    assert "tok-xyz" not in stored.output

    listed = runner.invoke(cli_app, ["credentials:list"])
    assert listed.exit_code == 0
    assert "telegram_bot_token" in listed.output

    deleted = runner.invoke(cli_app, ["credentials:delete", "telegram_bot_token"])
    assert deleted.exit_code == 0, deleted.output
    assert runner.invoke(cli_app, ["credentials:list"]).output.strip() == "(no credentials)"
    get_settings.cache_clear()
