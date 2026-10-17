"""Export, import, and inspect specs (``agentkit spec …``) — class-based."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from agentkit.foundation import Command
from agentkit.specs import SPECS, RepositorySpecStore


async def _with_store(fn):
    from agentkit.runtime import build_runtime, repositories

    runtime = build_runtime()
    async with repositories(runtime) as repos:
        return await fn(RepositorySpecStore(repos))


class SpecListCommand(Command):
    group = 'spec'
    signature = "spec:list {--kind=}"
    description = "List stored definitions."

    async def handle(self, kind: str | None = None) -> None:
        async def _run(store: RepositorySpecStore):
            return await store.list(kind)

        records = await _with_store(_run)
        if not records:
            self.info("no definitions")
            return
        for record in records:
            self.info(f"{record.kind}\t{record.name}\tv{record.version}")


class SpecSchemaCommand(Command):
    group = 'spec'
    signature = "spec:schema {kind}"
    description = "Print the JSON Schema for a spec kind."

    def handle(self, kind: str) -> None:
        import json

        try:
            schema = SPECS.schema_for(kind)
        except Exception as exc:  # noqa: BLE001 - surface as a CLI parameter error
            raise typer.BadParameter(str(exc)) from exc
        self.info(json.dumps(schema, indent=2))


class SpecExportCommand(Command):
    group = 'spec'
    signature = "spec:export {kind} {name} {--target=yaml} {--output=}"
    description = "Export a stored definition to a codegen target."

    async def handle(
        self,
        kind: str,
        name: str,
        target: str = "yaml",
        output: Path | None = None,
    ) -> None:
        from agentkit.specs.codegen import render_spec

        async def _run(store: RepositorySpecStore):
            record = await store.get(kind, name)
            return store.spec_of(kind, record) if record is not None else None

        spec = await _with_store(_run)
        if spec is None:
            self.error(f"no {kind} definition named {name!r}")
            raise typer.Exit(code=1)
        code = render_spec(spec, target)
        if output is not None:
            output.write_text(code, encoding="utf-8")
            self.info(f"wrote {output}")
        else:
            self.info(code)


class SpecImportCommand(Command):
    group = 'spec'
    signature = "spec:import {path} {--kind=}"
    description = "Import a definition from a JSON/YAML file into the spec store."

    async def handle(self, path: Path, kind: str | None = None) -> None:
        import json

        text = path.read_text(encoding="utf-8")
        if path.suffix in {".yaml", ".yml"}:
            import yaml

            payload: Any = yaml.safe_load(text)
        else:
            payload = json.loads(text)
        resolved_kind = kind or payload.get("spec_kind") or payload.get("kind")
        if resolved_kind not in SPECS.kinds():
            self.error(
                f"cannot infer spec kind; pass --kind (have: {', '.join(SPECS.kinds())})"
            )
            raise typer.Exit(code=2)
        try:
            spec = SPECS.validate(resolved_kind, payload)
        except Exception as exc:  # noqa: BLE001 - surface validation failures
            self.error(f"invalid spec: {exc}")
            raise typer.Exit(code=2) from exc

        async def _run(store: RepositorySpecStore):
            await store.upsert(resolved_kind, spec.name, spec)

        await _with_store(_run)
        self.info(f"imported {resolved_kind} {spec.name!r}")


COMMANDS: list[type] = [
    SpecListCommand,
    SpecSchemaCommand,
    SpecExportCommand,
    SpecImportCommand,
]
