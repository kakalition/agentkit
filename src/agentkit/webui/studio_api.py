"""Studio endpoints: specs, panels, actions, playground, export, activation.

The unified surface is spec-driven:

* ``GET  /api/studio/specs``                  -> ``{kind: JSON Schema}``
* ``GET  /api/studio/specs/{kind}``           -> stored definitions of that kind
* ``POST /api/studio/specs/{kind}``           -> validate + upsert a spec
* ``GET/DELETE /api/studio/specs/{kind}/{name}``
* ``GET  /api/studio/specs/{kind}/{name}/code?target=`` -> codegen
* ``POST /api/studio/specs/{kind}/{name}/run`` -> playground
* ``GET  /api/studio/panels``                 -> panel descriptors (SPI)
* ``POST /api/studio/actions/{id}``           -> named server-side action
* ``GET  /api/studio/extensions``             -> registered extensions

The legacy ``/api/studio/teams`` routes are preserved (they now read/write the
``team`` spec kind in the ``definitions`` table).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agentkit.runtime import repositories
from agentkit.specs import SPECS, RepositorySpecStore, SpecKind
from agentkit.specs.codegen import render_spec
from agentkit.studio import (
    SPEAKERS,
    TeamDefinition,
    resolve_from_app,
)
from agentkit.teams import TEAM_KINDS, TEAMS, register_team
from agentkit.webui.context import WebUIContext, get_context

router = APIRouter(tags=["studio"])


class RunBody(BaseModel):
    prompt: str = ""
    state: dict[str, Any] | None = None
    model: str | None = None


class InstallBody(BaseModel):
    into: str = "definitions"  # definitions | skills | none
    name: str | None = None


class ResumeCheckpointBody(BaseModel):
    seq: int | None = None
    target: str | None = None


class ScoreRunBody(BaseModel):
    grader: str | None = None
    dataset: str | None = None


def _catalog_source(ctx: WebUIContext, driver: str | None) -> Any:
    """Resolve the configured (or named) catalog source."""
    if ctx.app is not None and hasattr(ctx.app, "manager"):
        return ctx.app.manager("catalog").driver(driver)
    from agentkit import App

    fallback = App(settings=ctx.settings, discover=False)
    return fallback.manager("catalog").driver(driver)


def _recorder(ctx: WebUIContext, repos: Any, run_id: str) -> Any:
    """A run-trace recorder for a Studio run (repository-backed when possible)."""
    from agentkit.runs import recorder_for

    enabled = bool(getattr(ctx.settings, "run_trace_enabled", True))
    retention = int(getattr(ctx.settings, "run_events_retention", 0) or 0) or None
    return recorder_for(repos, run_id, enabled=enabled, retention=retention)


async def _run_context(ctx: WebUIContext, repos: Any) -> Any:
    if ctx.app is not None and hasattr(ctx.app, "deps"):
        try:
            return SimpleNamespace(deps=ctx.app.deps(repos))
        except Exception:  # pragma: no cover - deps are best-effort
            return None
    return None


def _team_view(record: Any) -> dict[str, Any]:
    definition = TeamDefinition.model_validate_json(record.spec)
    view = definition.model_dump()
    view["registered"] = record.name in TEAMS
    view["updated_at"] = record.updated_at.isoformat()
    return view


def _load_team(record: Any) -> TeamDefinition:
    try:
        return TeamDefinition.model_validate_json(record.spec)
    except Exception as exc:  # pragma: no cover - a corrupt stored row
        raise HTTPException(status_code=422, detail=f"stored definition is invalid: {exc}") from exc


# ---------------------------------------------------------------------------
# Spec schemas + generic definition CRUD
# ---------------------------------------------------------------------------


@router.get("/studio/specs")
async def list_spec_schemas(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    """JSON Schema per spec kind (drives the generic Studio form renderer)."""
    return {"specs": SPECS.schemas(), "kinds": SPECS.kinds()}


@router.get("/studio/specs/{kind}")
async def list_specs(
    kind: str, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    entry = SPECS.get(kind)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown spec kind {kind!r}")
    async with repositories(ctx.runtime) as repos:
        store = RepositorySpecStore(repos)
        records = await store.list(kind)
        return {"kind": kind, "specs": [store.view(record) for record in records]}


@router.post("/studio/specs/{kind}", status_code=201)
async def upsert_spec(
    kind: str, payload: dict[str, Any], ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    try:
        spec = SPECS.validate(kind, payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    async with repositories(ctx.runtime) as repos:
        store = RepositorySpecStore(repos)
        existing = await store.get(kind, spec.name)
        await store.upsert(kind, spec.name, spec)
    return {"kind": kind, "name": spec.name, "created": existing is None}


@router.get("/studio/specs/{kind}/{name}")
async def get_spec(
    kind: str, name: str, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    async with repositories(ctx.runtime) as repos:
        store = RepositorySpecStore(repos)
        record = await store.get(kind, name)
        if record is None:
            raise HTTPException(status_code=404, detail="definition not found")
        return store.view(record)


@router.delete("/studio/specs/{kind}/{name}")
async def delete_spec(
    kind: str, name: str, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    async with repositories(ctx.runtime) as repos:
        store = RepositorySpecStore(repos)
        removed = await store.remove(kind, name)
    if not removed:
        raise HTTPException(status_code=404, detail="definition not found")
    return {"kind": kind, "name": name, "removed": True}


@router.get("/studio/specs/{kind}/{name}/code")
async def spec_code(
    kind: str,
    name: str,
    target: str = Query("python"),
    ctx: WebUIContext = Depends(get_context),
) -> dict[str, Any]:
    async with repositories(ctx.runtime) as repos:
        store = RepositorySpecStore(repos)
        record = await store.get(kind, name)
        if record is None:
            raise HTTPException(status_code=404, detail="definition not found")
        spec = store.spec_of(kind, record)
    try:
        code = render_spec(spec, target)
    except Exception as exc:  # pragma: no cover - unknown target
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"kind": kind, "name": name, "target": target, "code": code}


@router.post("/studio/specs/{kind}/{name}/run")
async def run_spec(
    kind: str,
    name: str,
    body: RunBody,
    ctx: WebUIContext = Depends(get_context),
) -> dict[str, Any]:
    async with repositories(ctx.runtime) as repos:
        store = RepositorySpecStore(repos)
        record = await store.get(kind, name)
        if record is None:
            raise HTTPException(status_code=404, detail="definition not found")
        spec = store.spec_of(kind, record)
        run_ctx = await _run_context(ctx, repos)
        options: dict[str, Any] = {
            "app": ctx.app,
            "ctx": run_ctx,
            "recorder": _recorder(ctx, repos, f"{kind}:{name}"),
        }
        if body.state is not None:
            options["state"] = body.state
        try:
            result = await SPECS.run(kind, spec, body.prompt, **options)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}") from exc
    return {"kind": kind, "name": name, "result": _serialize(result)}


# ---------------------------------------------------------------------------
# Run traces (Playground v2 + trace grading)
# ---------------------------------------------------------------------------


@router.get("/studio/runs")
async def list_runs(
    limit: int = Query(50, ge=1, le=500), ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    async with repositories(ctx.runtime) as repos:
        return {"runs": await repos.run_events.list_runs(limit=limit)}


@router.get("/studio/runs/{run_id}")
async def get_run(
    run_id: str, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    async with repositories(ctx.runtime) as repos:
        rows = await repos.run_events.events(run_id)
    return {"run_id": run_id, "events": [_event_view(row) for row in rows]}


@router.post("/studio/runs/{run_id}/score")
async def score_run_endpoint(
    run_id: str,
    body: ScoreRunBody,
    ctx: WebUIContext = Depends(get_context),
) -> dict[str, Any]:
    """Grade a stored run trace with a registered grader and record the score."""
    from agentkit.scorers import score_run

    async with repositories(ctx.runtime) as repos:
        return await score_run(
            repos, run_id, grader_name=body.grader or "trace", dataset=body.dataset
        )


@router.get("/studio/runs/{run_id}/stream")
async def stream_run(
    run_id: str, ctx: WebUIContext = Depends(get_context)
) -> EventSourceResponse:
    """Replay a stored run's events as SSE (Playground v2)."""
    async with repositories(ctx.runtime) as repos:
        rows = await repos.run_events.events(run_id)

    async def _events() -> Any:
        yield {"event": "hello", "data": "{}"}
        for row in rows:
            event = _event_view(row)
            yield {"event": str(event.get("kind", "event")), "data": json.dumps(event, default=str)}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(_events())


# ---------------------------------------------------------------------------
# Checkpoints (time travel)
# ---------------------------------------------------------------------------


@router.get("/studio/checkpoints/{run_id}")
async def list_checkpoints(
    run_id: str, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    async with repositories(ctx.runtime) as repos:
        rows = await repos.checkpoints.list(run_id)
    return {"run_id": run_id, "checkpoints": [_checkpoint_view(row) for row in rows]}


@router.get("/studio/checkpoints/{run_id}/{seq}")
async def get_checkpoint(
    run_id: str, seq: int, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    async with repositories(ctx.runtime) as repos:
        record = await repos.checkpoints.get(run_id, seq)
        if record is None:
            raise HTTPException(status_code=404, detail="checkpoint not found")
        return _checkpoint_view(record)


@router.post("/studio/conversations/{conversation_id}/resume")
async def resume_conversation_from_checkpoint(
    conversation_id: str,
    body: ResumeCheckpointBody,
    ctx: WebUIContext = Depends(get_context),
) -> dict[str, Any]:
    """Restore (or branch) a conversation from a stored checkpoint."""
    app = ctx.app
    if app is None or not hasattr(app, "resume_from_checkpoint"):
        raise HTTPException(status_code=503, detail="app unavailable")
    destination = await app.resume_from_checkpoint(
        conversation_id, seq=body.seq, target=body.target
    )
    return {
        "source": conversation_id,
        "conversation_id": destination,
        "seq": body.seq,
        "branch": body.target is not None,
    }


def _event_view(record: Any) -> dict[str, Any]:
    try:
        return json.loads(record.data or "{}")
    except ValueError:  # pragma: no cover - tolerate corrupt rows
        return {"kind": record.kind, "seq": record.seq}


def _checkpoint_view(record: Any) -> dict[str, Any]:
    try:
        state = json.loads(record.state or "{}")
    except ValueError:  # pragma: no cover - tolerate corrupt rows
        state = record.state
    return {
        "run_id": record.run_id,
        "seq": record.seq,
        "label": record.label,
        "state": state,
        "created_at": record.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Extension / panel SPI
# ---------------------------------------------------------------------------


@router.get("/studio/panels")
async def list_panels(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    from agentkit.extensions.panels import PANELS

    return {"panels": [panel.to_dict() for panel in PANELS.list()]}


@router.get("/studio/app")
async def inspect_app(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    """Inspect the live app: primary agent, its tools, comms, teams, drivers.

    The Studio's "app inspector" — read-only, tolerant of partial wiring.
    """
    app = ctx.app
    settings = ctx.settings
    view: dict[str, Any] = {
        "name": getattr(app, "name", None) or getattr(settings, "agent_name", "agent"),
        "model": getattr(settings, "model_name", None),
        "posture": getattr(app, "posture_name", None)
        or getattr(settings, "agent_posture", None),
        "examples": [],
        "agent": _agent_view(app),
        "agents": _roster_view(app),
        "teams": _live_teams(),
        "comms": _driver_view(app, "comms"),
        "speaker": _driver_view(app, "speaker"),
        "graph": _driver_view(app, "graph"),
        "checkpoint": _driver_view(app, "checkpoint"),
        "vector": _driver_view(app, "vector"),
        "dataset": _driver_view(app, "dataset"),
        "working_memory": _driver_view(app, "working_memory"),
        "computer": _driver_view(app, "computer"),
        "realtime": _driver_view(app, "realtime"),
        "catalog": _driver_view(app, "catalog"),
    }
    try:
        view["drivers"] = app.drivers() if callable(getattr(app, "drivers", None)) else {}
    except Exception:  # pragma: no cover - never break inspection
        view["drivers"] = {}
    async with repositories(ctx.runtime) as repos:
        store = RepositorySpecStore(repos)
        view["specs"] = {
            kind: [record.name for record in await store.list(kind)]
            for kind in SPECS.kinds()
        }
        view["specs_kinds"] = SPECS.kinds()
    from agentkit.extensions import EXTENSIONS

    view["extensions"] = EXTENSIONS.describe()
    return view


def _agent_view(app: Any) -> dict[str, Any] | None:
    if app is None:
        return None
    try:
        agent = app.agent()
    except Exception:  # pragma: no cover - no primary agent
        return None
    if agent is None:
        return None
    model = getattr(agent, "model", None)
    return {
        "name": getattr(agent, "name", None),
        "description": getattr(agent, "description", None),
        "model": str(model) if model is not None else None,
        "tools": _tool_names(agent),
        "instructions": _instructions_of(agent),
    }


def _tool_names(agent: Any) -> list[str]:
    names: set[str] = set()
    toolset = getattr(agent, "_function_toolset", None)
    tools = getattr(toolset, "tools", None)
    if isinstance(tools, dict):
        names.update(str(name) for name in tools)
    for attribute in ("_tools", "tools"):
        value = getattr(agent, attribute, None)
        if isinstance(value, dict):
            names.update(str(name) for name in value)
        elif isinstance(value, (list, tuple)):
            for tool in value:
                name = getattr(tool, "name", None)
                if name:
                    names.add(str(name))
    return sorted(names)


def _instructions_of(agent: Any) -> str:
    instructions = getattr(agent, "_instructions", None)
    if isinstance(instructions, str):
        return instructions[:500]
    return ""


def _roster_view(app: Any) -> list[dict[str, Any]]:
    registry = getattr(app, "_agent_registry", None) if app is not None else None
    if registry is None:
        return []
    try:
        handles = registry.all() if hasattr(registry, "all") else None
        if handles is None:
            names = registry.names() if hasattr(registry, "names") else []
            handles = [registry.get(name) for name in names]
    except Exception:  # pragma: no cover - defensive
        return []
    roster: list[dict[str, Any]] = []
    for handle in handles or []:
        if handle is None:
            continue
        roster.append(
            {
                "name": getattr(handle, "name", ""),
                "description": getattr(handle, "description", ""),
                "capabilities": list(getattr(handle, "capabilities", []) or []),
                "remote": bool(getattr(handle, "is_remote", False)),
            }
        )
    return roster


def _live_teams() -> list[dict[str, Any]]:
    return [
        {"name": spec.name, "kind": spec.kind, "roster": sorted(spec.roster)}
        for spec in sorted(TEAMS.values(), key=lambda spec: spec.name)
    ]


def _driver_view(app: Any, kind: str) -> dict[str, Any] | None:
    if app is None or not hasattr(app, "manager"):
        return None
    try:
        manager = app.manager(kind)
        return {"driver": manager.configured_driver(), "available": manager.available()}
    except Exception:  # pragma: no cover - defensive
        return None


@router.get("/studio/extensions")
async def list_extensions(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    from agentkit.extensions import EXTENSIONS

    applied = ctx.app.extension_info() if ctx.app is not None else []
    return {"extensions": EXTENSIONS.describe(), "applied": applied}


@router.post("/studio/actions/{action_id}")
async def invoke_action(
    action_id: str, body: dict[str, Any], ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    from agentkit.extensions.actions import ACTIONS, run_action

    if ACTIONS.get(action_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown action {action_id!r}")
    try:
        result = await run_action(action_id, body, ctx)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}") from exc
    return {"action": action_id, "result": _serialize(result)}


# ---------------------------------------------------------------------------
# Catalog (the catalog panel)
# ---------------------------------------------------------------------------


@router.get("/studio/catalog")
async def catalog_search(
    q: str = Query(""),
    driver: str | None = Query(None),
    ctx: WebUIContext = Depends(get_context),
) -> dict[str, Any]:
    source = _catalog_source(ctx, driver)
    items = await source.search(q)
    return {"driver": source.name, "items": [item.to_dict() for item in items]}


@router.post("/studio/catalog/{item_id}/install")
async def catalog_install(
    item_id: str,
    body: InstallBody,
    driver: str | None = Query(None),
    ctx: WebUIContext = Depends(get_context),
) -> dict[str, Any]:
    source = _catalog_source(ctx, driver)
    try:
        if body.into == "none":
            return _serialize(await source.install(item_id, None))
        if body.into == "skills":
            from agentkit.catalog import SkillsTarget

            skills_target: Any = SkillsTarget(getattr(ctx.settings, "skills_dir", None) or "skills")
            return _serialize(await source.install(item_id, skills_target))
        from agentkit.catalog import DefinitionsTarget

        async with repositories(ctx.runtime) as repos:
            target: Any = DefinitionsTarget(RepositorySpecStore(repos))
            return _serialize(await source.install(item_id, target))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no catalog item {item_id!r}") from None
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}") from exc


# ---------------------------------------------------------------------------
# Back-compat: /api/studio/teams (the team spec kind)
# ---------------------------------------------------------------------------


@router.get("/studio/teams")
async def list_definitions(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    async with repositories(ctx.runtime) as repos:
        records = await repos.definitions.list(SpecKind.TEAM)
    return {
        "teams": [_team_view(record) for record in records],
        "kinds": list(TEAM_KINDS),
        "speakers": list(SPEAKERS),
    }


@router.post("/studio/teams", status_code=201)
async def upsert_definition(
    definition: TeamDefinition, ctx: WebUIContext = Depends(get_context)
) -> dict[str, Any]:
    async with repositories(ctx.runtime) as repos:
        existing = await repos.definitions.get(SpecKind.TEAM, definition.name)
        await repos.definitions.upsert(
            SpecKind.TEAM,
            definition.name,
            spec=definition.model_dump_json(),
        )
    return {"name": definition.name, "created": existing is None}


@router.delete("/studio/teams/{name}")
async def delete_definition(name: str, ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    async with repositories(ctx.runtime) as repos:
        removed = await repos.definitions.remove(SpecKind.TEAM, name)
    if not removed:
        raise HTTPException(status_code=404, detail="team definition not found")
    return {"name": name, "removed": True}


@router.get("/studio/teams/{name}/code")
async def definition_code(name: str, ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    async with repositories(ctx.runtime) as repos:
        record = await repos.definitions.get(SpecKind.TEAM, name)
    if record is None:
        raise HTTPException(status_code=404, detail="team definition not found")
    return {"name": name, "code": render_spec(_load_team(record), "python")}


@router.post("/studio/teams/{name}/activate")
async def activate_definition(name: str, ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
    """Register the definition into the in-process ``TEAMS`` registry."""
    async with repositories(ctx.runtime) as repos:
        record = await repos.definitions.get(SpecKind.TEAM, name)
    if record is None:
        raise HTTPException(status_code=404, detail="team definition not found")
    definition = _load_team(record)
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
        record = await repos.definitions.get(SpecKind.TEAM, name)
        if record is None:
            raise HTTPException(status_code=404, detail="team definition not found")
        definition = _load_team(record)
        resolve = resolve_from_app(ctx.app)
        run_ctx = await _run_context(ctx, repos)
        return await SPECS.run(
            SpecKind.TEAM,
            definition,
            body.prompt,
            resolve=resolve,
            ctx=run_ctx,
            recorder=_recorder(ctx, repos, f"team:{name}"),
        )


def _serialize(result: Any) -> Any:
    """Best-effort JSON-friendly view of a runner result."""
    if isinstance(result, (dict, list, str, int, float, bool)) or result is None:
        return result
    if hasattr(result, "render"):
        return {"rendered": result.render()}
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return str(result)
