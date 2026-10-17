from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from agentkit.config import AgentSettings
from agentkit.db.repositories import Repositories
from agentkit.deps import Deps
from agentkit.foundation.events import Listener
from agentkit.runtime import Runtime, build_runtime, repositories


class Recorder(Listener):
    """Test listener base: subclass with ``event`` and an optional ``transform``."""

    event: object = ()
    transform = None

    def __init__(self, seen: list) -> None:
        self.seen = seen

    def handle(self, event) -> None:  # noqa: ANN001
        value = self.transform(event) if self.transform else event
        self.seen.append(value)


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
