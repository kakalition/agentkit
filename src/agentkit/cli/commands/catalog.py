"""Browse and install catalog items (``agentkit catalog …``)."""

from __future__ import annotations

import asyncio

import typer

from agentkit.cli._app import app

__all__ = ["catalog_app"]

catalog_app = typer.Typer(no_args_is_help=True, help="Browse and install catalog items.")
app.add_typer(catalog_app, name="catalog")


def _source(name: str | None = None):
    from agentkit import App

    agent_app = App(discover=False)
    return agent_app.manager("catalog").driver(name)


@catalog_app.command("list")
def catalog_list(
    query: str = typer.Option("", "--query", "-q", help="Filter the catalog."),
    driver: str | None = typer.Option(None, "--driver", help="Catalog driver name."),
) -> None:
    """List catalog items from the configured source."""
    source = _source(driver)
    items = asyncio.run(source.search(query))
    if not items:
        typer.echo("no items")
        return
    for item in items:
        typer.echo(f"{item.id}\t{item.kind}\t{item.description}")


@catalog_app.command("install")
def catalog_install(
    item_id: str = typer.Argument(..., help="The catalog item id."),
    into: str = typer.Option("definitions", "--into", help="definitions | skills | none."),
    driver: str | None = typer.Option(None, "--driver", help="Catalog driver name."),
) -> None:
    """Install a catalog item into the definitions store or the skills dir."""

    async def _run():
        source = _source(driver)
        if into == "none":
            return await source.install(item_id, None)
        if into == "skills":
            from agentkit.catalog import SkillsTarget

            return await source.install(item_id, SkillsTarget())
        from agentkit.catalog import DefinitionsTarget
        from agentkit.runtime import build_runtime, repositories
        from agentkit.specs import RepositorySpecStore

        runtime = build_runtime()
        async with repositories(runtime) as repos:
            return await source.install(item_id, DefinitionsTarget(RepositorySpecStore(repos)))

    try:
        result = asyncio.run(_run())
    except KeyError:
        typer.echo(f"no item {item_id!r}", err=True)
        raise typer.Exit(code=1) from None
    except Exception as exc:
        typer.echo(f"install failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"installed {item_id} -> {result}")
