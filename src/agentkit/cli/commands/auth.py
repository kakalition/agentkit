"""Auth commands: manage hashed API keys and report the caller identity (class-based)."""

from __future__ import annotations

import contextlib
import secrets
from typing import Any

import typer

from agentkit.foundation import Command


@contextlib.asynccontextmanager
async def _auth_scope():
    from agentkit.runtime import build_runtime, repositories

    runtime = build_runtime()
    async with repositories(runtime) as repos:
        yield repos


def _split_roles(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").replace(",", " ").split() if part]


class AuthKeyCreateCommand(Command):
    group = 'auth:key'
    signature = "auth:key:create {name} {--owner=} {--roles=}"
    description = "Create an API key. The plaintext key is shown once and never stored."

    async def handle(
        self, name: str, owner: str | None = None, roles: str | None = None
    ) -> None:
        from agentkit.security.keys import hash_key, key_prefix

        token = secrets.token_urlsafe(32)
        async with _auth_scope() as repos:
            row = await repos.api_keys.create(
                name=name,
                key_hash=hash_key(token),
                prefix=key_prefix(token),
                roles=_split_roles(roles),
                owner_id=owner,
            )
        self.info(f"created key #{row.id} ({row.name}) for owner {row.owner_id}")
        self.info(token)


class AuthKeyListCommand(Command):
    group = 'auth:key'
    signature = "auth:key:list {--all}"
    description = "List API keys (never prints the secret)."

    async def handle(self, all_keys: bool = False) -> None:
        async with _auth_scope() as repos:
            rows: list[Any] = await repos.api_keys.list(include_revoked=all_keys)
        if not rows:
            self.info("(no keys)")
            return
        for row in rows:
            state = "revoked" if row.revoked_at else "active"
            self.info(f"#{row.id} {row.name} [{state}] prefix={row.prefix} roles={row.roles}")


class AuthKeyRevokeCommand(Command):
    group = 'auth:key'
    signature = "auth:key:revoke {ident}"
    description = "Revoke an API key by id or name."

    async def handle(self, ident: str) -> None:
        async with _auth_scope() as repos:
            revoked = await repos.api_keys.revoke(ident)
        if revoked:
            self.info(f"revoked {ident}")
        else:
            self.error(f"no active key {ident!r}")
            raise typer.Exit(code=1)


class AuthWhoamiCommand(Command):
    signature = "auth:whoami"
    description = "Show the configured identity and auth mode."

    def handle(self) -> None:
        from agentkit.config import get_settings
        from agentkit.security.authenticator import Authenticator

        settings = get_settings()
        authenticator = Authenticator(settings)
        self.info(f"owner_id: {settings.owner_id}")
        self.info(f"auth_enabled: {authenticator.enabled}")
        self.info(f"api_keys_configured: {len(authenticator._static)}")
        self.info(f"jwks: {settings.auth_jwks_url or '(none)'}")


COMMANDS: list[type] = [
    AuthKeyCreateCommand,
    AuthKeyListCommand,
    AuthKeyRevokeCommand,
    AuthWhoamiCommand,
]
