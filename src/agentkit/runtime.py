"""Process runtime: settings -> async engine -> repositories -> deps."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from agentkit.config import AgentSettings, get_settings
from agentkit.db.engine import create_async_db_engine, make_async_session_factory
from agentkit.db.migrations import init_db
from agentkit.db.repositories import Repositories
from agentkit.deps import ApprovalCallback, Deps
from agentkit.embeddings import build_embedder, configure
from agentkit.security import Actor


@dataclass
class Runtime:
    settings: AgentSettings
    engine: AsyncEngine
    session_factory: Any
    repos_factory: type[Repositories] = Repositories
    initialized: bool = field(default=False)
    init_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def build_runtime(
    settings: AgentSettings | None = None,
    *,
    repos_factory: type[Repositories] = Repositories,
) -> Runtime:
    settings = settings or get_settings()
    settings.ensure_dirs()
    engine = create_async_db_engine(
        settings.resolved_database_url, auth_token=settings.libsql_auth_token
    )
    configure(build_embedder(settings))
    return Runtime(
        settings=settings,
        engine=engine,
        session_factory=make_async_session_factory(engine),
        repos_factory=repos_factory,
    )


async def ensure_initialized(runtime: Runtime) -> None:
    """Create the schema once per runtime (async, guarded against concurrency)."""
    if runtime.initialized:
        return
    async with runtime.init_lock:
        if not runtime.initialized:
            await init_db(runtime.engine)
            runtime.initialized = True


@asynccontextmanager
async def repositories(
    runtime: Runtime, owner_id: str | None = None
) -> AsyncIterator[Repositories]:
    """Open an async repository scope (commits on success, rolls back on error).

    ``owner_id`` selects the tenant; when omitted it defaults to
    ``runtime.settings.owner_id`` (today's single-operator behavior).
    """
    await ensure_initialized(runtime)
    session = runtime.session_factory()
    resolved_owner = owner_id if owner_id is not None else runtime.settings.owner_id
    try:
        yield runtime.repos_factory(session, resolved_owner)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def run_repositories_sync(
    runtime: Runtime, function: Callable[[Repositories], Any]
) -> Any:
    """Run ``function(repos)`` inside a repository scope from a sync context.

    The documented sync seam (e.g. DBOS workflow/step bodies that cannot be async):
    it drives the async scope to completion on a private event loop, so database
    work never runs on the caller's loop.
    """

    async def _run() -> Any:
        async with repositories(runtime) as repos:
            result = function(repos)
            if inspect.isawaitable(result):
                result = await result
            return result

    return asyncio.run(_run())


def build_deps(
    runtime: Runtime,
    repos: Repositories,
    *,
    model: Any = None,
    mcp: Any = None,
    a2a: Any = None,
    approve: ApprovalCallback | None = None,
    clock: Any = None,
    actor: Actor | None = None,
) -> Deps:
    return Deps(
        settings=runtime.settings,
        repos=repos,
        model=model,
        mcp=mcp,
        a2a=a2a,
        approve=approve,
        actor=actor,
        clock=clock or (lambda: datetime.now(UTC)),
    )
