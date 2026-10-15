"""Inspect a booted app (agent, tools, channels, config, stack)."""

from __future__ import annotations

import json

import typer

from agentkit.cli._app import app
from agentkit.foundation.commands import load_bootstrap


@app.command()
def inspect(
    bootstrap: str | None = typer.Option(None, "--bootstrap"),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show the booted app's agent, tools, channels, commands and config."""
    from agentkit.webui.introspect import stack_view

    booted = load_bootstrap(bootstrap)
    booted.boot()
    agent = booted.agent()
    toolset = getattr(agent, "_function_toolset", None)
    data = {
        "name": booted.name,
        "agent": getattr(agent, "name", None),
        "tools": sorted(getattr(toolset, "tools", {}).keys()),
        "channels": sorted(booted.channels()),
        "commands": sorted(booted._commands),
        "config": sorted(booted._config_schemas),
        "stack": stack_view(booted.settings, app=booted),
    }
    if as_json:
        typer.echo(json.dumps(data, indent=2))
        return
    typer.echo(f"app: {data['name']}")
    typer.echo(f"agent: {data['agent']}")
    typer.echo(f"tools: {', '.join(data['tools']) or '(none)'}")
    typer.echo(f"channels: {', '.join(data['channels']) or '(none)'}")
    typer.echo(f"commands: {', '.join(data['commands']) or '(none)'}")
    typer.echo(f"config: {', '.join(data['config']) or '(none)'}")
    stack = data["stack"]
    active = [name for name, on in stack["channels"].items() if on]
    typer.echo(f"model: {stack['model_name']} (providers: {', '.join(stack['model_providers'])})")
    typer.echo(f"memory: {'on' if stack['memory']['enabled'] else 'off'} ({stack['memory']['embedding_backend']})")
    typer.echo(f"subagents: {'on' if stack['subagents']['enabled'] else 'off'}")
    native = stack["native_tools"]
    typer.echo(f"native toolkits: {', '.join(native['enabled']) or '(none)'}")
    if native["models"] or native["tasks"] or native["jobs"]:
        typer.echo(
            f"  exposed models: {', '.join(native['models']) or '(none)'}; "
            f"tasks: {', '.join(native['tasks']) or '(none)'}; "
            f"jobs: {', '.join(native['jobs']) or '(none)'}"
        )
    typer.echo(f"learning: {'on' if stack['learning']['enabled'] else 'off'}")
    typer.echo(f"active channels: {', '.join(active) or '(none)'}")
