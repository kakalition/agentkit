"""Credential-vault commands: set, list (names only), and delete secrets."""

from __future__ import annotations

import contextlib

import typer

from agentkit.cli._app import app


@contextlib.contextmanager
def _vault():
    from agentkit.runtime import build_runtime
    from agentkit.security.credentials import Credentials

    yield Credentials(build_runtime())


@app.command("credentials:set")
def credentials_set(
    name: str = typer.Argument(..., help="The credential name (e.g. telegram_bot_token)."),
    value: str | None = typer.Option(None, "--value", help="The secret (else prompt, hidden)."),
    kind: str = typer.Option("secret", "--kind", help="A label for the credential kind."),
) -> None:
    """Encrypt and store a credential. The value is never echoed."""
    import asyncio

    from agentkit.security.credentials import VaultError

    secret = value if value is not None else typer.prompt("value", hide_input=True)
    try:
        with _vault() as vault:
            asyncio.run(vault.set(name, secret, kind=kind))
    except VaultError as exc:
        typer.echo(f"vault unavailable: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"stored {name}")


@app.command("credentials:list")
def credentials_list() -> None:
    """List credential names (never values)."""
    import asyncio

    from agentkit.security.credentials import VaultError

    try:
        with _vault() as vault:
            names = asyncio.run(vault.names())
    except VaultError as exc:
        typer.echo(f"vault unavailable: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if not names:
        typer.echo("(no credentials)")
        return
    for name in names:
        typer.echo(name)


@app.command("credentials:delete")
def credentials_delete(name: str = typer.Argument(..., help="The credential name.")) -> None:
    """Delete a stored credential."""
    import asyncio

    from agentkit.security.credentials import VaultError

    try:
        with _vault() as vault:
            removed = asyncio.run(vault.delete(name))
    except VaultError as exc:
        typer.echo(f"vault unavailable: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if removed:
        typer.echo(f"deleted {name}")
    else:
        typer.echo(f"no credential {name!r}", err=True)
        raise typer.Exit(code=1)
