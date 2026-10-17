"""Database seeders (Laravel's ``Seeder``) and a small runner.

    class UserSeeder(Seeder):
        async def run(self):
            await User.create(name="Ada")

    await SeederRunner([UserSeeder, DemoSeeder]).run()

Seeders may be sync or async; the runner awaits whichever they return.
"""

from __future__ import annotations

import inspect
from typing import Any

__all__ = ["Seeder", "SeederRunner", "run_seeders"]


class Seeder:
    """Base class for a seeder (override :meth:`run`)."""

    def run(self) -> Any:
        return None

    async def __call__(self) -> Any:
        result = self.run()
        if inspect.isawaitable(result):
            return await result
        return result


class SeederRunner:
    """Runs a list of seeders in order."""

    def __init__(self, seeders: list[Any]) -> None:
        self.seeders = seeders

    async def run(self) -> list[Any]:
        results: list[Any] = []
        for seeder in self.seeders:
            instance = seeder() if isinstance(seeder, type) else seeder
            results.append(await instance())
        return results


async def run_seeders(seeders: list[Any]) -> list[Any]:
    """Convenience runner for a list of seeder classes/instances."""
    return await SeederRunner(seeders).run()
