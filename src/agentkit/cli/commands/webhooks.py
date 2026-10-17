"""Manage outbound webhook subscriptions (class-based)."""

from __future__ import annotations

import contextlib

import typer

from agentkit.foundation import Command


@contextlib.asynccontextmanager
async def _webhook_scope():
    from agentkit.runtime import build_runtime, repositories

    runtime = build_runtime()
    async with repositories(runtime) as repos:
        yield repos


class WebhookAddCommand(Command):
    group = 'webhook'
    signature = "webhook:add {url} {--events=\"*\"} {--secret=}"
    description = "Register an outbound webhook."

    async def handle(self, url: str, events: str = "*", secret: str = "") -> None:
        names = [part.strip() for part in events.replace(",", " ").split() if part.strip()]
        async with _webhook_scope() as repos:
            row = await repos.webhooks.add(url, events=names or ["*"], secret=secret)
        self.info(f"added webhook #{row.id} -> {url}")


class WebhookListCommand(Command):
    group = 'webhook'
    signature = "webhook:list"
    description = "List outbound webhooks."

    async def handle(self) -> None:
        async with _webhook_scope() as repos:
            rows = await repos.webhooks.list()
        if not rows:
            self.info("(no webhooks)")
            return
        for row in rows:
            state = "on" if row.enabled else "off"
            self.info(f"#{row.id} [{state}] {row.url} events={row.events}")


class WebhookDeleteCommand(Command):
    group = 'webhook'
    signature = "webhook:delete {webhook_id}"
    description = "Delete an outbound webhook."

    async def handle(self, webhook_id: int) -> None:
        async with _webhook_scope() as repos:
            deleted = await repos.webhooks.delete(webhook_id)
        if deleted:
            self.info(f"deleted #{webhook_id}")
        else:
            self.error(f"no webhook #{webhook_id}")
            raise typer.Exit(code=1)


COMMANDS: list[type] = [
    WebhookAddCommand,
    WebhookListCommand,
    WebhookDeleteCommand,
]
