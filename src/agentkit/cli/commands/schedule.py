"""Durable scheduling commands (class-based)."""

from __future__ import annotations

from agentkit.foundation import Command
from agentkit.foundation.commands import load_bootstrap


class ScheduleListCommand(Command):
    signature = "schedule:list {--bootstrap=}"
    description = "List the booted app's durable scheduled jobs."

    async def handle(self, bootstrap: str | None = None) -> None:
        from agentkit import Schedule

        booted = load_bootstrap(bootstrap)
        booted.boot()
        jobs = await Schedule.list()
        if not jobs:
            self.info("(no scheduled jobs)")
            return
        for job in jobs:
            state = "on" if job["enabled"] else "off"
            self.info(f"  {job['name']:<20} {job['schedule']:<16} -> {job['task']} [{state}]")


class ScheduleRunCommand(Command):
    signature = "schedule:run {--bootstrap=}"
    description = "Run any due scheduled jobs right now (catch-up)."

    async def handle(self, bootstrap: str | None = None) -> None:
        from agentkit import Schedule

        booted = load_bootstrap(bootstrap)
        booted.boot()
        ran = await Schedule.run_due()
        self.info(f"ran {len(ran)} job(s)" + (f": {', '.join(ran)}" if ran else ""))


COMMANDS: list[type] = [
    ScheduleListCommand,
    ScheduleRunCommand,
]
