"""Native database toolkit: owner-scoped, allow-listed CRUD over app models.

Nothing is exposed unless the app names it (``Agent.database(models={...})`` or
``App.models({...})``). Reads are always available for an exposed model; writes
(``db_create``/``db_update``/``db_delete``) require approval, emit an audit entry
and a ``db.*`` event, and are validated against the SQLModel schema.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic_ai import RunContext

from agentkit.deps import Deps
from agentkit.foundation.repository import Repository
from agentkit.toolkits._common import actor_label, emit_event, repos_of, resolve_allow_list

__all__ = ["_attach_database"]

MAX_LIMIT = 100
_PREVIEW = 200


def _model_class(target: Any) -> type:
    if isinstance(target, type) and issubclass(target, Repository):
        return target.model
    return target


def _model_name(target: Any) -> str:
    return getattr(_model_class(target), "__name__", str(target))


def _repo(target: Any, repos: Any) -> Any:
    if isinstance(target, Repository):
        return target
    if isinstance(target, type) and issubclass(target, Repository):
        return target(repos.session, repos.owner_id)
    repo: Any = Repository(repos.session, repos.owner_id)
    repo.model = target
    return repo


def _resolve(models: dict[str, Any], name: str) -> Any:
    target = models.get(name)
    if target is None:
        known = ", ".join(sorted(models)) or "(none)"
        raise ValueError(f"unknown model {name!r}; available: {known}")
    return target


def _validate(model: type, values: dict[str, Any], *, allow_id: bool = False) -> dict[str, Any]:
    fields = set(getattr(model, "model_fields", {}))
    cleaned = dict(values or {})
    if "owner_id" in cleaned:
        raise ValueError("owner_id cannot be set through the database toolkit")
    if not allow_id:
        cleaned.pop("id", None)
    unknown = sorted(set(cleaned) - fields)
    if unknown:
        raise ValueError(f"unknown field(s) {', '.join(unknown)} for {model.__name__}")
    return cleaned


def _row_view(row: Any) -> dict[str, Any]:
    try:
        data = row.model_dump(mode="json")
    except Exception:  # pragma: no cover - defensive
        data = {key: getattr(row, key, None) for key in ("id",)}
    for key, value in list(data.items()):
        if isinstance(value, str) and len(value) > _PREVIEW:
            data[key] = value[:_PREVIEW] + "…"
    return data


async def _audit(
    repos: Any, action: str, target: str, detail: dict[str, Any], *, actor: str = ""
) -> None:
    try:
        audit = getattr(repos, "audit", None)
        if audit is not None:
            await audit.append(
                action, target=target, detail=detail, actor=actor or repos.owner_id
            )
    except Exception:  # pragma: no cover - audit must not break a tool
        pass


def _attach_database(
    agent: Any, models: dict[str, Any] | None = None, *, flag: str = "db_tools_enabled"
) -> Any:
    """Register the database tools on a built PydanticAI agent (idempotent)."""
    if getattr(agent, "_agentkit_database_attached", False):
        return agent
    fallback = dict(models or {})

    def _models(ctx: RunContext[Deps]) -> dict[str, Any]:
        return resolve_allow_list(ctx, fallback, "_agent_models")

    @agent.tool
    async def db_list_models(ctx: RunContext[Deps]) -> str:
        """List the database models the agent is allowed to read and write."""
        models = _models(ctx)
        if not models:
            return "(no models exposed; ask the operator to allow-list models)"
        return "\n".join(f"- {name} ({_model_name(target)})" for name, target in sorted(models.items()))

    @agent.tool
    async def db_describe(ctx: RunContext[Deps], model: str) -> str:
        """Describe an exposed model's columns and their types.

        Args:
            model: The model name (from db_list_models).
        """
        repos = repos_of(ctx)
        try:
            target = _resolve(_models(ctx), model)
        except ValueError as exc:
            return f"ERROR: {exc}"
        klass = _model_class(target)
        lines = [f"{_model_name(target)}:"]
        for field, info in getattr(klass, "model_fields", {}).items():
            lines.append(f"- {field}: {getattr(info, 'annotation', 'any')}")
        return "\n".join(lines) if repos is not None else "ERROR: no repositories"

    @agent.tool
    async def db_find(
        ctx: RunContext[Deps], model: str, filters: dict[str, Any] | None = None, limit: int = 20
    ) -> str:
        """Find rows matching simple column equality filters.

        Args:
            model: The model name (from db_list_models).
            filters: Column -> value equality filters.
            limit: Maximum rows to return (capped at 100).
        """
        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        try:
            target = _resolve(_models(ctx), model)
            klass = _model_class(target)
            clean = _validate(klass, filters or {})
        except ValueError as exc:
            return f"ERROR: {exc}"
        repo = _repo(target, repos)
        rows = await repo.where(**clean).limit(max(1, min(int(limit), MAX_LIMIT))).all()
        if not rows:
            return "(no rows)"
        return json.dumps([_row_view(row) for row in rows], default=str)

    @agent.tool
    async def db_get(ctx: RunContext[Deps], model: str, id: Any) -> str:
        """Fetch one row by primary key.

        Args:
            model: The model name (from db_list_models).
            id: The primary key value.
        """
        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        try:
            target = _resolve(_models(ctx), model)
        except ValueError as exc:
            return f"ERROR: {exc}"
        row = await _repo(target, repos).get(id)
        return json.dumps(_row_view(row), default=str) if row is not None else "(not found)"

    @agent.tool
    async def db_count(ctx: RunContext[Deps], model: str, filters: dict[str, Any] | None = None) -> str:
        """Count rows matching simple column equality filters.

        Args:
            model: The model name (from db_list_models).
            filters: Column -> value equality filters.
        """
        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        try:
            target = _resolve(_models(ctx), model)
            clean = _validate(_model_class(target), filters or {})
        except ValueError as exc:
            return f"ERROR: {exc}"
        return str(await _repo(target, repos).count(**clean))

    @agent.tool(requires_approval=True)
    async def db_create(ctx: RunContext[Deps], model: str, values: dict[str, Any]) -> str:
        """Create a row (owner-scoped; requires approval).

        Args:
            model: The model name (from db_list_models).
            values: Column -> value pairs for the new row.
        """
        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        try:
            target = _resolve(_models(ctx), model)
            clean = _validate(_model_class(target), values)
        except ValueError as exc:
            return f"ERROR: {exc}"
        row = await _repo(target, repos).create(**clean)
        await _audit(
            repos,
            "db.create",
            f"{model}:{getattr(row, 'id', '')}",
            {"values": clean},
            actor=actor_label(ctx),
        )
        await emit_event("db.create", model=model, id=getattr(row, "id", None))
        return f"created {model} #{getattr(row, 'id', '?')}"

    @agent.tool(requires_approval=True)
    async def db_update(ctx: RunContext[Deps], model: str, id: Any, values: dict[str, Any]) -> str:
        """Update a row by primary key (requires approval).

        Args:
            model: The model name (from db_list_models).
            id: The primary key value.
            values: Column -> value pairs to change.
        """
        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        try:
            target = _resolve(_models(ctx), model)
            clean = _validate(_model_class(target), values)
        except ValueError as exc:
            return f"ERROR: {exc}"
        row = await _repo(target, repos).update(id, **clean)
        if row is None:
            return "(not found)"
        await _audit(
            repos, "db.update", f"{model}:{id}", {"values": clean}, actor=actor_label(ctx)
        )
        await emit_event("db.update", model=model, id=id)
        return f"updated {model} #{id}"

    @agent.tool(requires_approval=True)
    async def db_delete(ctx: RunContext[Deps], model: str, id: Any) -> str:
        """Delete a row by primary key (requires approval).

        Args:
            model: The model name (from db_list_models).
            id: The primary key value.
        """
        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        try:
            target = _resolve(_models(ctx), model)
        except ValueError as exc:
            return f"ERROR: {exc}"
        deleted = await _repo(target, repos).delete(id)
        if not deleted:
            return "(not found)"
        await _audit(repos, "db.delete", f"{model}:{id}", {}, actor=actor_label(ctx))
        await emit_event("db.delete", model=model, id=id)
        return f"deleted {model} #{id}"

    agent._agentkit_database_attached = True  # type: ignore[attr-defined]
    return agent
