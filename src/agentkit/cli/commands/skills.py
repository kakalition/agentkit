"""Inspect discovered skills (class-based)."""

from __future__ import annotations

from pathlib import Path

import typer

from agentkit.foundation import Command


class SkillsListCommand(Command):
    group = 'skills'
    signature = "skills:list {--path=}"
    description = "List the skills discovered under the configured roots."

    def handle(self, path: list[Path] | None = None) -> None:
        from agentkit.skills import SkillRegistry

        registry = (
            SkillRegistry.from_paths(path) if path else SkillRegistry.from_settings()
        ).discover()
        if len(registry) == 0:
            self.info("(no skills found)")
            return
        for skill in registry.all():
            self.info(f"  {skill.name:<24} {skill.description}  ({skill.path})")


class SkillsShowCommand(Command):
    group = 'skills'
    signature = "skills:show {name} {--path=}"
    description = "Show one skill's full instructions (and bundled files)."

    def handle(self, name: str, path: list[Path] | None = None) -> None:
        from agentkit.skills import SkillRegistry

        registry = (
            SkillRegistry.from_paths(path) if path else SkillRegistry.from_settings()
        ).discover()
        skill = registry.get(name)
        if skill is None:
            self.error(f"no skill named {name!r}")
            raise typer.Exit(code=1)
        self.info(skill.render())


COMMANDS: list[type] = [
    SkillsListCommand,
    SkillsShowCommand,
]
