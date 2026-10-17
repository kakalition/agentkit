"""Browse and install catalog items (``agentkit catalog …``) — class-based."""

from __future__ import annotations

import typer

from agentkit.foundation import Command


def _source(name: str | None = None):
    from agentkit import App

    agent_app = App(discover=False)
    return agent_app.manager("catalog").driver(name)


class CatalogListCommand(Command):
    group = 'catalog'
    signature = "catalog:list {--query=} {--driver=}"
    description = "List catalog items from the configured source."

    async def handle(self, query: str = "", driver: str | None = None) -> None:
        source = _source(driver)
        items = await source.search(query)
        if not items:
            self.info("no items")
            return
        for item in items:
            self.info(f"{item.id}\t{item.kind}\t{item.description}")


class CatalogInstallCommand(Command):
    group = 'catalog'
    signature = "catalog:install {item_id} {--into=definitions} {--driver=}"
    description = "Install a catalog item into the definitions store or the skills dir."

    async def handle(
        self, item_id: str, into: str = "definitions", driver: str | None = None
    ) -> None:
        source = _source(driver)
        try:
            if into == "none":
                result = await source.install(item_id, None)
            elif into == "skills":
                from agentkit.catalog import SkillsTarget

                result = await source.install(item_id, SkillsTarget())
            else:
                from agentkit.catalog import DefinitionsTarget
                from agentkit.runtime import build_runtime, repositories
                from agentkit.specs import RepositorySpecStore

                runtime = build_runtime()
                async with repositories(runtime) as repos:
                    result = await source.install(
                        item_id, DefinitionsTarget(RepositorySpecStore(repos))
                    )
        except KeyError:
            self.error(f"no item {item_id!r}")
            raise typer.Exit(code=1) from None
        except Exception as exc:  # noqa: BLE001 - surface any install failure
            self.error(f"install failed: {exc}")
            raise typer.Exit(code=1) from exc
        self.info(f"installed {item_id} -> {result}")


COMMANDS: list[type] = [
    CatalogListCommand,
    CatalogInstallCommand,
]
