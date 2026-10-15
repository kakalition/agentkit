"""Manage outbound webhook subscriptions."""

from __future__ import annotations

import contextlib

import typer

from agentkit.cli._app import webhook_app


@contextlib.asynccontextmanager
async def _webhook_scope():
    from agentkit.runtime import build_runtime, repositories

    runtime = build_runtime()
    async with repositories(runtime) as repos:
        yield repos


@webhook_app.command("add")
def webhook_add(
    url: str = typer.Argument(..., help="The delivery URL."),
    events: str = typer.Option("*", "--events", help="Comma-separated event names ('*' = all)."),
    secret: str = typer.Option("", "--secret", help="HMAC signing secret."),
) -> None:
    """Register an outbound webhook."""
    import asyncio

    names = [part.strip() for part in events.replace(",", " ").split() if part.strip()]

    async def _run() -> int | None:
        async with _webhook_scope() as repos:
            row = await repos.webhooks.add(url, events=names or ["*"], secret=secret)
            return row.id

    typer.echo(f"added webhook #{asyncio.run(_run())} -> {url}")


@webhook_app.command("list")
def webhook_list() -> None:
    """List outbound webhooks."""
    import asyncio

    async def _run() -> list:
        async with _webhook_scope() as repos:
            return await repos.webhooks.list()

    rows = asyncio.run(_run())
    if not rows:
        typer.echo("(no webhooks)")
        return
    for row in rows:
        state = "on" if row.enabled else "off"
        typer.echo(f"#{row.id} [{state}] {row.url} events={row.events}")


@webhook_app.command("delete")
def webhook_delete(webhook_id: int = typer.Argument(..., help="The webhook id.")) -> None:
    """Delete an outbound webhook."""
    import asyncio

    async def _run() -> bool:
        async with _webhook_scope() as repos:
            return await repos.webhooks.delete(webhook_id)

    if asyncio.run(_run()):
        typer.echo(f"deleted #{webhook_id}")
    else:
        typer.echo(f"no webhook #{webhook_id}", err=True)
        raise typer.Exit(code=1)
