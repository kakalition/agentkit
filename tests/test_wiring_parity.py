"""WS0.2/WS1.2 — wiring parity: driver selection is honored, defaults unchanged."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from agentkit.config import AgentSettings
from agentkit.foundation.application import App
from agentkit.foundation.facade import using
from agentkit.knowledge import (
    FixedChunker,
    IdentityReranker,
    InMemoryRetriever,
    KnowledgeBase,
    LexicalReranker,
    RepositoryRetriever,
    SemanticChunker,
)
from agentkit.learning import (
    HeuristicExtractor,
    LearningExtractorManager,
    NoopStrategy,
    _driver,
    reflect,
)
from agentkit.memory import (
    HybridRecall,
    InMemoryStore,
    KeywordRecall,
    _current_store,
)
from agentkit.runtime import Runtime


def _app(runtime: Runtime, **updates: Any) -> App:
    settings: AgentSettings = (
        runtime.settings.model_copy(update=updates) if updates else runtime.settings
    )
    app = App(name="parity", settings=settings, discover=False)
    app._runtime = runtime
    return app


# -- memory recall ---------------------------------------------------------


async def test_memory_recall_default_is_hybrid(runtime: Runtime, repos: Any) -> None:
    with using(_app(runtime)):
        assert isinstance(repos.memories._recall_strategy(), HybridRecall)


async def test_memory_recall_driver_keyword(runtime: Runtime, repos: Any) -> None:
    with using(_app(runtime, memory_recall_driver="keyword")):
        assert isinstance(repos.memories._recall_strategy(), KeywordRecall)


async def test_memory_recall_default_matches_fallback(runtime: Runtime, repos: Any) -> None:
    repo = repos.memories
    await repo.add("alpha note", kind="fact", importance=0.0)
    await repo.add("beta note", kind="preference", importance=0.0)
    baseline = [memory.id for memory in await repo.search("note")]
    with using(_app(runtime)):
        under = [memory.id for memory in await repo.search("note")]
    assert under == baseline


async def test_memory_recall_keyword_changes_order(runtime: Runtime, repos: Any) -> None:
    repo = repos.memories
    await repo.add("alpha note", kind="fact", importance=0.0)
    await repo.add("alpha note", kind="preference", importance=1.0)
    with using(_app(runtime)):
        hybrid = await repo.search("alpha note")
    assert hybrid[0].kind == "preference"
    with using(_app(runtime, memory_recall_driver="keyword")):
        keyword = await repo.search("alpha note")
    assert keyword[0].kind == "fact"


async def test_memory_driver_in_memory_backs_capability(runtime: Runtime, repos: Any) -> None:
    deps = SimpleNamespace(repos=repos, settings=runtime.settings)
    assert _current_store(deps) is repos.memories
    with using(_app(runtime, memory_driver="in_memory")):
        assert isinstance(_current_store(deps), InMemoryStore)


# -- RAG chunker / retriever / reranker ------------------------------------


def test_rag_drivers_defaults(runtime: Runtime) -> None:
    with using(_app(runtime)):
        kb = KnowledgeBase()
        assert isinstance(kb._driver("chunker"), SemanticChunker)
        assert isinstance(kb._driver("retriever"), RepositoryRetriever)
        assert isinstance(kb._driver("reranker"), IdentityReranker)


def test_rag_drivers_non_default(runtime: Runtime) -> None:
    app = _app(runtime, chunker_driver="fixed", retriever_driver="memory", reranker_driver="lexical")
    with using(app):
        kb = KnowledgeBase()
        assert isinstance(kb._driver("chunker"), FixedChunker)
        assert isinstance(kb._driver("retriever"), InMemoryRetriever)
        assert isinstance(kb._driver("reranker"), LexicalReranker)


async def test_knowledge_retriever_driver_changes_behavior(runtime: Runtime, repos: Any) -> None:
    await repos.knowledge.add("doc", ["the quick brown fox jumps over the lazy dog"])
    await repos.session.commit()
    with using(_app(runtime)):
        kb = KnowledgeBase(app=_app(runtime))
        assert await kb.search("quick")
    with using(_app(runtime, retriever_driver="memory")):
        kb = KnowledgeBase(app=_app(runtime, retriever_driver="memory"))
        assert await kb.search("quick") == []


# -- learning --------------------------------------------------------------


def test_learning_defaults_and_non_default(runtime: Runtime) -> None:
    with using(_app(runtime)):
        assert _driver("learning_extractor") is not None
        assert not isinstance(_driver("learning_strategy"), NoopStrategy)
    with using(_app(runtime, learning_extractor_driver="heuristic", learning_strategy_driver="none")):
        assert isinstance(_driver("learning_extractor"), HeuristicExtractor)
        assert isinstance(_driver("learning_strategy"), NoopStrategy)


async def test_learning_strategy_none_skips(runtime: Runtime, repos: Any) -> None:
    with using(_app(runtime, learning_strategy_driver="none")):
        result = await reflect(repos)
    assert result.get("skipped") is True


def test_embedder_manager_default_matches_direct_build(runtime: Runtime) -> None:
    from agentkit.embeddings import build_embedder, get_default_embedder
    from agentkit.runtime import _configured_embedder

    assert type(_configured_embedder(runtime.settings)) is type(build_embedder(runtime.settings))
    assert get_default_embedder() is not None


def test_learning_managers_are_registered() -> None:
    assert LearningExtractorManager.default_driver == "model"
