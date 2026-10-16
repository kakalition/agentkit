from __future__ import annotations

import pytest
from pydantic_ai.messages import ModelRequest, UserPromptPart

from agentkit.contracts.search import SearchHit, SearchIndex
from agentkit.db.repositories import Repositories
from agentkit.foundation.application import App
from agentkit.runtime import Runtime
from agentkit.search import FtsSearchIndex, ScanSearchIndex
from agentkit.session import serialize_message


async def _seed(repos: Repositories) -> None:
    await repos.conversations.get_or_create("cli:s1", channel="cli")
    await repos.messages.append(
        "cli:s1",
        [
            serialize_message(
                ModelRequest(parts=[UserPromptPart("the launch codename is zebra nine")])
            )
        ],
    )
    await repos.conversations.get_or_create("cli:s2", channel="cli")
    await repos.messages.append(
        "cli:s2",
        [serialize_message(ModelRequest(parts=[UserPromptPart("unrelated chatter about weather")]))],
    )


@pytest.mark.parametrize("index", [FtsSearchIndex(), ScanSearchIndex()])
async def test_search_finds_hits(repos: Repositories, index):
    await _seed(repos)
    hits = await index.search(repos, "zebra", limit=5)
    assert hits and hits[0].conversation_id == "cli:s1"
    assert isinstance(hits[0], SearchHit)
    assert "zebra" in hits[0].text


async def test_search_empty_query(repos: Repositories):
    await _seed(repos)
    assert await FtsSearchIndex().search(repos, "   ") == []


async def test_search_ignores_unrelated(repos: Repositories):
    await _seed(repos)
    assert await FtsSearchIndex().search(repos, "platypus") == []


async def test_message_repo_search_text(repos: Repositories):
    await _seed(repos)
    rows = await repos.messages.search_text("zebra", limit=5)
    assert rows and rows[0][0] == "cli:s1"


def test_search_driver_conformance():
    assert isinstance(FtsSearchIndex(), SearchIndex)
    assert isinstance(ScanSearchIndex(), SearchIndex)


def test_search_manager_default_is_fts(runtime: Runtime):
    app = App(name="s", settings=runtime.settings, discover=False)
    assert isinstance(app.search, FtsSearchIndex)
    assert set(app.manager("search").available()) >= {"fts", "scan"}


def test_search_driver_from_settings(runtime: Runtime):
    settings = runtime.settings.model_copy(update={"search_driver": "scan"})
    app = App(name="s", settings=settings, discover=False)
    assert isinstance(app.search, ScanSearchIndex)
