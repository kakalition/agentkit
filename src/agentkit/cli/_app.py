"""Shared Typer applications for the agentkit CLI."""

from __future__ import annotations

import typer

app = typer.Typer(
    add_completion=False,
    help="agentkit — workspace management, the operator web UI, and app scaffolding.",
    no_args_is_help=True,
)
workspace_app = typer.Typer(no_args_is_help=True, help="Inspect and migrate agent workspaces.")
skills_app = typer.Typer(no_args_is_help=True, help="Inspect discovered skills.")
knowledge_app = typer.Typer(no_args_is_help=True, help="Index and search knowledge (RAG).")
app.add_typer(workspace_app, name="workspace")
app.add_typer(skills_app, name="skills")
app.add_typer(knowledge_app, name="knowledge")

__all__ = ["app", "knowledge_app", "skills_app", "workspace_app"]
