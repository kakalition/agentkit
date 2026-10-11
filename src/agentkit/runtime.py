"""Process runtime: settings -> engine -> repositories -> deps."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session

from agentkit.config import AgentSettings, get_settings
from agentkit.db.engine import DB_LOCK, create_db_engine, make_session_factory
from agentkit.db.migrations import init_db
from agentkit.db.repositories import Repositories
from agentkit.deps import ApprovalCallback, Deps
from agentkit.embeddings import build_embedder, configure


@dataclass
class Runtime:
    settings: AgentSettings
    engine: Engine
    session_factory: Any
    repos_factory: type[Repositories] = Repositories


def build_runtime(
    settings: AgentSettings | None = None,
    *,
    repos_factory: type[Repositories] = Repositories,
) -> Runtime:
    settings = settings or get_settings()
    settings.ensure_dirs()
    engine = create_db_engine(settings.resolved_database_url, auth_token=settings.libsql_auth_token)
    with DB_LOCK:
        init_db(engine)
    configure(build_embedder(settings))
    return Runtime(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        repos_factory=repos_factory,
    )


@contextmanager
def repositories(runtime: Runtime) -> Iterator[Repositories]:
    with DB_LOCK:
        session: Session = runtime.session_factory()
        try:
            yield runtime.repos_factory(session, runtime.settings.owner_id)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def build_deps(
    runtime: Runtime,
    repos: Repositories,
    *,
    model: Any = None,
    mcp: Any = None,
    a2a: Any = None,
    approve: ApprovalCallback | None = None,
    clock: Any = None,
) -> Deps:
    return Deps(
        settings=runtime.settings,
        repos=repos,
        model=model,
        mcp=mcp,
        a2a=a2a,
        approve=approve,
        clock=clock or (lambda: datetime.now(UTC)),
    )
