"""Auth commands: manage hashed API keys and report the caller identity."""

from __future__ import annotations

import contextlib
import secrets
from typing import Any

import typer

from agentkit.cli._app import app, auth_key_app


@contextlib.asynccontextmanager
async def _auth_scope():
    from agentkit.runtime import build_runtime, repositories

    runtime = build_runtime()
    async with repositories(runtime) as repos:
        yield repos


def _split_roles(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").replace(",", " ").split() if part]


@auth_key_app.command("create")
def auth_key_create(
    name: str = typer.Argument(..., help="A label for the key."),
    owner: str | None = typer.Option(None, "--owner", help="Owner id (default: settings owner)."),
    roles: str | None = typer.Option(None, "--roles", help="Comma-separated roles."),
) -> None:
    """Create an API key. The plaintext key is shown once and never stored."""
    import asyncio

    from agentkit.security.keys import hash_key, key_prefix

    token = secrets.token_urlsafe(32)

    async def _run() -> Any:
        async with _auth_scope() as repos:
            return await repos.api_keys.create(
                name=name,
                key_hash=hash_key(token),
                prefix=key_prefix(token),
                roles=_split_roles(roles),
                owner_id=owner,
            )

    row = asyncio.run(_run())
    typer.echo(f"created key #{row.id} ({row.name}) for owner {row.owner_id}")
    typer.echo(token)


@auth_key_app.command("list")
def auth_key_list(
    all_keys: bool = typer.Option(False, "--all", help="Include revoked keys."),
) -> None:
    """List API keys (never prints the secret)."""
    import asyncio

    async def _run() -> list[Any]:
        async with _auth_scope() as repos:
            return await repos.api_keys.list(include_revoked=all_keys)

    rows = asyncio.run(_run())
    if not rows:
        typer.echo("(no keys)")
        return
    for row in rows:
        state = "revoked" if row.revoked_at else "active"
        typer.echo(f"#{row.id} {row.name} [{state}] prefix={row.prefix} roles={row.roles}")


@auth_key_app.command("revoke")
def auth_key_revoke(
    ident: str = typer.Argument(..., help="The key id or name to revoke."),
) -> None:
    """Revoke an API key by id or name."""
    import asyncio

    async def _run() -> bool:
        async with _auth_scope() as repos:
            return await repos.api_keys.revoke(ident)

    if asyncio.run(_run()):
        typer.echo(f"revoked {ident}")
    else:
        typer.echo(f"no active key {ident!r}", err=True)
        raise typer.Exit(code=1)


@app.command("auth:whoami")
def auth_whoami() -> None:
    """Show the configured identity and auth mode."""
    from agentkit.config import get_settings
    from agentkit.security.authenticator import Authenticator

    settings = get_settings()
    authenticator = Authenticator(settings)
    typer.echo(f"owner_id: {settings.owner_id}")
    typer.echo(f"auth_enabled: {authenticator.enabled}")
    typer.echo(f"api_keys_configured: {len(authenticator._static)}")
    typer.echo(f"jwks: {settings.auth_jwks_url or '(none)'}")
