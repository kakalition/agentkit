from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from agentkit.config import AgentSettings
from agentkit.db.repositories import Repositories
from agentkit.deps import Deps
from agentkit.runtime import Runtime, build_runtime, repositories


@pytest.fixture
def runtime(tmp_path) -> Runtime:
    settings = AgentSettings(
        owner_id="owner", agent_home=tmp_path, memory_embedding_backend="hash"
    )
    return build_runtime(settings)


@pytest.fixture
async def repos(runtime: Runtime) -> AsyncIterator[Repositories]:
    async with repositories(runtime) as opened:
        yield opened


@pytest.fixture
def deps(runtime: Runtime, repos: Repositories) -> Deps:
    return Deps(settings=runtime.settings, repos=repos)
