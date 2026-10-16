"""Studio endpoints: author, run, export, and activate declarative teams.

Complements the read-only ``/api/teams`` (live, code-registered teams) with the
persisted, editable :class:`~agentkit.studio.TeamDefinition` surface: a team
builder (CRUD + JSON), a playground (``/run`` returning the transcript + ledger for
a message-flow view), Python export, and in-process activation.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agentkit.runtime import repositories
from agentkit.studio import (
    SPEAKERS,
    TeamDefinition,
    render_team_code,
    resolve_from_app,
    run_team_definition,
)
from agentkit.teams import TEAM_KINDS, TEAMS, register_team
from agentkit.webui.context import WebUIContext, get_context

router = APIRouter(tags=["studio"])


class RunBody(BaseModel):
    prompt: str


def _view(record: Any) -> dict[str, Any]:
    definition = TeamDefinition.model_validate_json(record.definition)
    view = definition.model_dump()
    view["registered"] = record.name in TEAMS
    view["updated_at"] = record.updated_at.isoformat()
    return view


def _load(record: Any) -> TeamDefinition:
    try:
        return TeamDefinition.model_validate_json(record.definition)
    except Exception as exc:  # pragma: no cover - a corrupt stored row
        raise HTTPException(status_code=422, detail=f"stored definition is invalid: {exc}") from exc


@router.get("/studio/teams")
async def list_definitions(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    async with repositories(ctx.runtime) as repos:
        records = await repos.team_specs.list()
    return {
        "teams": [_view(record) for record in records],
        "kinds": list(TEAM_KINDS),
        "speakers": list(SPEAKERS),
    }


@router.post("/studio/teams", status_code=201)
async def upsert_definition(
    definition: TeamDefinition, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    async with repositories(ctx.runtime) as repos:
        existing = await repos.team_specs.get(definition.name)
        await repos.team_specs.upsert(
            definition.name,
            kind=definition.kind,
            definition=definition.model_dump_json(),
        )
    return {"name": definition.name, "created": existing is None}


@router.delete("/studio/teams/{name}")
async def delete_definition(name: str, ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    async with repositories(ctx.runtime) as repos:
        removed = await repos.team_specs.remove(name)
    if not removed:
        raise HTTPException(status_code=404, detail="team definition not found")
    return {"name": name, "removed": True}


@router.get("/studio/teams/{name}/code")
async def definition_code(name: str, ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    async with repositories(ctx.runtime) as repos:
        record = await repos.team_specs.get(name)
    if record is None:
        raise HTTPException(status_code=404, detail="team definition not found")
    return {"name": name, "code": render_team_code(_load(record))}


@router.post("/studio/teams/{name}/activate")
async def activate_definition(name: str, ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    """Register the definition into the in-process ``TEAMS`` registry."""
    async with repositories(ctx.runtime) as repos:
        record = await repos.team_specs.get(name)
    if record is None:
        raise HTTPException(status_code=404, detail="team definition not found")
    definition = _load(record)
    resolve = resolve_from_app(ctx.app)
    roster = {member.name: resolve(member.name) for member in definition.members}
    register_team(definition.name, roster, kind=definition.kind)
    return {
        "name": definition.name,
        "registered": True,
        "tool": f"team_{definition.name}",
        "note": "in-process only; use the exported Python to persist it",
    }


@router.post("/studio/teams/{name}/run")
async def run_definition(
    name: str, body: RunBody, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    """Playground: run the definition and return the transcript + ledger."""
    async with repositories(ctx.runtime) as repos:
        record = await repos.team_specs.get(name)
        if record is None:
            raise HTTPException(status_code=404, detail="team definition not found")
        definition = _load(record)
        resolve = resolve_from_app(ctx.app)
        run_ctx = None
        if ctx.app is not None and hasattr(ctx.app, "deps"):
            try:
                run_ctx = SimpleNamespace(deps=ctx.app.deps(repos))
            except Exception:  # pragma: no cover - deps are best-effort
                run_ctx = None
        return await run_team_definition(
            definition, body.prompt, resolve=resolve, ctx=run_ctx
        )
