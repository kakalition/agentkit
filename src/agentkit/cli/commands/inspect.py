"""Inspect a booted app (agent, tools, channels, config, stack) — class-based."""

from __future__ import annotations

import json

from agentkit.foundation import Command
from agentkit.foundation.commands import load_bootstrap


class InspectCommand(Command):
    signature = "inspect {--bootstrap=} {--json}"
    description = "Show the booted app's agent, tools, channels, commands and config."

    def handle(self, bootstrap: str | None = None, as_json: bool = False) -> None:
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
            self.info(json.dumps(data, indent=2))
            return
        stack = data["stack"]
        self.info(f"app: {data['name']}")
        self.info(f"agent: {data['agent']}")
        self.info(f"posture: {stack['posture']['name']}")
        self.info(f"tools: {', '.join(data['tools']) or '(none)'}")
        self.info(f"channels: {', '.join(data['channels']) or '(none)'}")
        self.info(f"commands: {', '.join(data['commands']) or '(none)'}")
        self.info(f"config: {', '.join(data['config']) or '(none)'}")
        active = [name for name, on in stack["channels"].items() if on]
        drivers = stack.get("drivers", {})
        if drivers:
            summary = ", ".join(
                f"{kind}={info['driver']}" for kind, info in sorted(drivers.items())
            )
            self.info(f"drivers: {summary}")
        self.info(
            f"model: {stack['model_name']} (providers: {', '.join(stack['model_providers'])})"
        )
        self.info(
            f"memory: {'on' if stack['memory']['enabled'] else 'off'} "
            f"({stack['memory']['embedding_backend']})"
        )
        self.info(f"subagents: {'on' if stack['subagents']['enabled'] else 'off'}")
        native = stack["native_tools"]
        self.info(f"native toolkits: {', '.join(native['enabled']) or '(none)'}")
        if native["models"] or native["tasks"] or native["jobs"]:
            self.info(
                f"  exposed models: {', '.join(native['models']) or '(none)'}; "
                f"tasks: {', '.join(native['tasks']) or '(none)'}; "
                f"jobs: {', '.join(native['jobs']) or '(none)'}"
            )
        self.info(f"learning: {'on' if stack['learning']['enabled'] else 'off'}")
        if stack.get("teams"):
            self.info(f"teams: {', '.join(stack['teams'])}")
        self.info(f"active channels: {', '.join(active) or '(none)'}")


COMMANDS: list[type] = [
    InspectCommand,
]
