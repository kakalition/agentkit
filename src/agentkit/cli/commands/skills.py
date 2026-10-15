"""Inspect discovered skills."""

from __future__ import annotations

from pathlib import Path

import typer

from agentkit.cli._app import skills_app


@skills_app.command("list")
def skills_list(
    path: list[Path] | None = typer.Option(
        None, "--path", help="Skill root (repeatable; default: settings roots)."
    ),
) -> None:
    """List the skills discovered under the configured roots."""
    from agentkit.skills import SkillRegistry

    registry = (
        SkillRegistry.from_paths(path) if path else SkillRegistry.from_settings()
    ).discover()
    if len(registry) == 0:
        typer.echo("(no skills found)")
        return
    for skill in registry.all():
        typer.echo(f"  {skill.name:<24} {skill.description}  ({skill.path})")


@skills_app.command("show")
def skills_show(
    name: str = typer.Argument(..., help="Skill name."),
    path: list[Path] | None = typer.Option(None, "--path", help="Skill root (repeatable)."),
) -> None:
    """Show one skill's full instructions (and bundled files)."""
    from agentkit.skills import SkillRegistry

    registry = (
        SkillRegistry.from_paths(path) if path else SkillRegistry.from_settings()
    ).discover()
    skill = registry.get(name)
    if skill is None:
        typer.echo(f"no skill named {name!r}", err=True)
        raise typer.Exit(code=1)
    typer.echo(skill.render())
