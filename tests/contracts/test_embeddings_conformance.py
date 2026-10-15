from __future__ import annotations

import pytest
from conformance import embedder_conformance

from agentkit.config import AgentSettings
from agentkit.foundation import App


@pytest.fixture
def app(tmp_path):
    return App(
        settings=AgentSettings(agent_home=tmp_path, memory_embedding_backend="hash"),
        discover=False,
    )


def test_hash_embedder_conforms(app):
    embedder_conformance(app.manager("embeddings").create("hash"))


def test_configured_embedder_follows_backend(app):
    from agentkit.embeddings import HashingEmbedder

    assert isinstance(app.manager("embeddings").driver(), HashingEmbedder)


def test_none_backend_returns_no_embedder(app):
    assert app.manager("embeddings").create("none") is None
