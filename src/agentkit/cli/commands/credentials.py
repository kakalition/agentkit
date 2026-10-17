"""Credential-vault commands: set, list (names only), and delete secrets (class-based)."""

from __future__ import annotations

import contextlib

import typer

from agentkit.foundation import Command


@contextlib.contextmanager
def _vault():
    from agentkit.runtime import build_runtime
    from agentkit.security.credentials import Credentials

    yield Credentials(build_runtime())


class CredentialsSetCommand(Command):
    signature = "credentials:set {name} {--value=} {--kind=secret}"
    description = "Encrypt and store a credential. The value is never echoed."

    async def handle(self, name: str, value: str | None = None, kind: str = "secret") -> None:
        from agentkit.security.credentials import VaultError

        secret = value if value is not None else typer.prompt("value", hide_input=True)
        try:
            with _vault() as vault:
                await vault.set(name, secret, kind=kind)
        except VaultError as exc:
            self.error(f"vault unavailable: {exc}")
            raise typer.Exit(code=1) from exc
        self.info(f"stored {name}")


class CredentialsListCommand(Command):
    signature = "credentials:list"
    description = "List credential names (never values)."

    async def handle(self) -> None:
        from agentkit.security.credentials import VaultError

        try:
            with _vault() as vault:
                names = await vault.names()
        except VaultError as exc:
            self.error(f"vault unavailable: {exc}")
            raise typer.Exit(code=1) from exc
        if not names:
            self.info("(no credentials)")
            return
        for name in names:
            self.info(name)


class CredentialsDeleteCommand(Command):
    signature = "credentials:delete {name}"
    description = "Delete a stored credential."

    async def handle(self, name: str) -> None:
        from agentkit.security.credentials import VaultError

        try:
            with _vault() as vault:
                removed = await vault.delete(name)
        except VaultError as exc:
            self.error(f"vault unavailable: {exc}")
            raise typer.Exit(code=1) from exc
        if removed:
            self.info(f"deleted {name}")
        else:
            self.error(f"no credential {name!r}")
            raise typer.Exit(code=1)


COMMANDS: list[type] = [
    CredentialsSetCommand,
    CredentialsListCommand,
    CredentialsDeleteCommand,
]
