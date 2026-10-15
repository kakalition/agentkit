"""Encrypted credential vault (Fernet) for channel/provider secrets.

Secrets are encrypted at rest and looked up by name. The vault is opt-in and
refuses to operate without ``AGENTKIT_CREDENTIALS_KEY``; values are never logged
or echoed. Channels prefer a vault entry over the environment (see
:func:`hydrate_credentials`).
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from agentkit.contracts.vault import Vault
from agentkit.errors import ConfigurationError
from agentkit.support import register_driver
from agentkit.support.kinds import DriverKind, VaultDriver
from agentkit.support.manager import Manager

SECRET_SETTINGS = (
    "telegram_bot_token",
    "slack_bot_token",
    "slack_app_token",
    "discord_bot_token",
    "email_imap_password",
    "openai_api_key",
    "anthropic_api_key",
    "google_api_key",
    "groq_api_key",
    "mistral_api_key",
)


class VaultError(ConfigurationError):
    """Raised when the vault is used without a valid key."""


def build_cipher(settings: Any) -> Any:
    """Build a Fernet cipher from ``credentials_key`` (or ``None`` if unset)."""
    key = getattr(settings, "credentials_key", None)
    if not key:
        return None
    from cryptography.fernet import Fernet

    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        derived = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
        return Fernet(derived)


class Credentials:
    """Owner-scoped encrypted secret store backed by the ``credentials`` table."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self.settings = runtime.settings
        self._fernet = build_cipher(runtime.settings)

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.settings, "credentials_enabled", False))

    def _cipher(self) -> Any:
        if self._fernet is None:
            raise VaultError("credentials_key is not set; refusing to use the vault")
        return self._fernet

    def encrypt(self, value: str) -> str:
        return self._cipher().encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        return self._cipher().decrypt(token.encode("ascii")).decode("utf-8")

    async def set(
        self,
        name: str,
        value: str,
        *,
        kind: str = "secret",
        metadata: str = "{}",
        owner_id: str | None = None,
    ) -> Any:
        from agentkit.runtime import repositories

        async with repositories(self.runtime, owner_id) as repos:
            return await repos.credentials.set(
                name, kind=kind, ciphertext=self.encrypt(value), metadata=metadata
            )

    async def get(self, name: str, *, owner_id: str | None = None) -> str | None:
        from agentkit.runtime import repositories

        async with repositories(self.runtime, owner_id) as repos:
            row = await repos.credentials.get(name)
        return self.decrypt(row.ciphertext) if row is not None else None

    async def names(self, *, owner_id: str | None = None) -> list[str]:
        from agentkit.runtime import repositories

        async with repositories(self.runtime, owner_id) as repos:
            return [row.name for row in await repos.credentials.list()]

    async def delete(self, name: str, *, owner_id: str | None = None) -> bool:
        from agentkit.runtime import repositories

        async with repositories(self.runtime, owner_id) as repos:
            return await repos.credentials.delete(name)


def hydrate_credentials(settings: Any, runtime: Any) -> list[str]:
    """Load vault secrets into settings fields that have no env value.

    Returns the names hydrated. A no-op (empty list) when the vault is disabled
    or misconfigured — enabling the vault must never break boot.
    """
    if not getattr(settings, "credentials_enabled", False):
        return []
    vault = Credentials(runtime)
    if vault._fernet is None:  # pragma: no cover - defensive
        return []
    from agentkit._sync import run_sync

    async def _load(names: list[str]) -> dict[str, str]:
        from agentkit.runtime import repositories

        async with repositories(runtime) as repos:
            out: dict[str, str] = {}
            for name in names:
                row = await repos.credentials.get(name)
                if row is not None:
                    out[name] = vault.decrypt(row.ciphertext)
            return out

    wanted = [name for name in SECRET_SETTINGS if not getattr(settings, name, None)]
    if not wanted:
        return []
    values = run_sync(_load(wanted))
    for name, value in values.items():
        setattr(settings, name, value)
    return sorted(values)


class EnvVault:
    """A read-only vault backed by the settings/environment (no persistence)."""

    def __init__(self, settings: Any) -> None:
        self.settings = settings

    async def set(self, name: str, value: str, **options: Any) -> Any:
        raise VaultError("the env vault is read-only; set the value in the environment")

    async def get(self, name: str, **options: Any) -> str | None:
        return getattr(self.settings, name, None)

    async def names(self, **options: Any) -> list[str]:
        return [name for name in SECRET_SETTINGS if getattr(self.settings, name, None)]

    async def delete(self, name: str, **options: Any) -> bool:
        return False


class VaultManager(Manager):
    """Resolves the configured secret vault (``vault_driver``, default ``fernet``)."""

    kind = DriverKind.VAULT
    default_driver = VaultDriver.FERNET


@register_driver(DriverKind.VAULT, VaultDriver.FERNET)
def _fernet_vault_driver(app: Any) -> Credentials:
    return Credentials(app.runtime)


@register_driver(DriverKind.VAULT, VaultDriver.ENV)
def _env_vault_driver(app: Any) -> EnvVault:
    return EnvVault(app.settings)


__all__ = [
    "Credentials",
    "EnvVault",
    "SECRET_SETTINGS",
    "Vault",
    "VaultError",
    "VaultManager",
    "build_cipher",
    "hydrate_credentials",
]
