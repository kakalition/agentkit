"""Export, import, and inspect specs (``agentkit spec …``)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from agentkit.cli._app import app
from agentkit.specs import SPECS, RepositorySpecStore

__all__ = ["spec_app"]

spec_app = typer.Typer(no_args_is_help=True, help="Export, import, and inspect specs.")
app.add_typer(spec_app, name="spec")


async def _with_store(fn):
    from agentkit.runtime import build_runtime, repositories

    runtime = build_runtime()
    async with repositories(runtime) as repos:
        return await fn(RepositorySpecStore(repos))


@spec_app.command("list")
def spec_list(kind: str | None = typer.Option(None, "--kind", help="Filter by spec kind.")) -> None:
    """List stored definitions."""

    async def _run(store: RepositorySpecStore):
        return await store.list(kind)

    records = asyncio.run(_with_store(_run))
    if not records:
        typer.echo("no definitions")
        return
    for record in records:
        typer.echo(f"{record.kind}\t{record.name}\tv{record.version}")


@spec_app.command("schema")
def spec_schema(kind: str = typer.Argument(..., help="Spec kind (agent/team/workflow/eval).")) -> None:
    """Print the JSON Schema for a spec kind."""
    import json

    try:
        schema = SPECS.schema_for(kind)
    except Exception as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(schema, indent=2))


@spec_app.command("export")
def spec_export(
    kind: str = typer.Argument(..., help="Spec kind."),
    name: str = typer.Argument(..., help="Definition name."),
    target: str = typer.Option("yaml", "--target", help="python | yaml | json."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write to a file."),
) -> None:
    """Export a stored definition to a codegen target."""
    from agentkit.specs.codegen import render_spec

    async def _run(store: RepositorySpecStore):
        record = await store.get(kind, name)
        return store.spec_of(kind, record) if record is not None else None

    spec = asyncio.run(_with_store(_run))
    if spec is None:
        typer.echo(f"no {kind} definition named {name!r}", err=True)
        raise typer.Exit(code=1)
    code = render_spec(spec, target)
    if output is not None:
        output.write_text(code, encoding="utf-8")
        typer.echo(f"wrote {output}")
    else:
        typer.echo(code)


@spec_app.command("import")
def spec_import(
    path: Path = typer.Argument(..., help="A spec file (.json/.yaml)."),
    kind: str | None = typer.Option(None, "--kind", help="Override the spec kind."),
) -> None:
    """Import a definition from a JSON/YAML file into the spec store."""
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".yaml", ".yml"}:
        import yaml

        payload = yaml.safe_load(text)
    else:
        import json

        payload = json.loads(text)
    resolved_kind = kind or payload.get("spec_kind") or payload.get("kind")
    if resolved_kind not in SPECS.kinds():
        typer.echo(f"cannot infer spec kind; pass --kind (have: {', '.join(SPECS.kinds())})", err=True)
        raise typer.Exit(code=2)
    try:
        spec = SPECS.validate(resolved_kind, payload)
    except Exception as exc:
        typer.echo(f"invalid spec: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    async def _run(store: RepositorySpecStore):
        await store.upsert(resolved_kind, spec.name, spec)

    asyncio.run(_with_store(_run))
    typer.echo(f"imported {resolved_kind} {spec.name!r}")
