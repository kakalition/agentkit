from __future__ import annotations

import pytest
from conformance import (
    agent_middleware_conformance,
    audio_conformance,
    auth_conformance,
    channel_conformance,
    chunker_conformance,
    code_executor_conformance,
    context_strategy_conformance,
    database_conformance,
    durability_conformance,
    extractor_conformance,
    graph_executor_conformance,
    guardrails_conformance,
    ingest_conformance,
    learning_sink_conformance,
    learning_strategy_conformance,
    memory_store_conformance,
    notification_channel_conformance,
    observability_conformance,
    observability_off_disables,
    planning_conformance,
    pricing_conformance,
    queue_conformance,
    ratelimit_conformance,
    recall_strategy_conformance,
    reporter_conformance,
    reranker_conformance,
    retriever_conformance,
    scheduler_conformance,
    storage_conformance,
    task_store_conformance,
    topology_conformance,
    vault_conformance,
)

from agentkit.config import AgentSettings
from agentkit.contracts import Topology
from agentkit.foundation import App


@pytest.fixture
def app(tmp_path):
    return App(
        settings=AgentSettings(agent_home=tmp_path, memory_embedding_backend="hash"),
        discover=False,
    )


def test_pricing_drivers_conform(app):
    for name in ["genai", "static"]:
        pricing_conformance(app.manager("pricing").create(name))


def test_ingest_drivers_conform(app):
    for name in ["default", "text"]:
        ingest_conformance(app.manager("ingest").create(name))


def test_audio_driver_conforms(app):
    audio_conformance(app.manager("audio").create("openai"))


def test_database_drivers_conform(app):
    for name in ["sqlite", "postgres"]:
        database_conformance(app.manager("database").create(name))


async def test_queue_drivers_conform(app):
    for name in ["database", "sync"]:
        await queue_conformance(app.manager("queue").create(name))


async def test_scheduler_memory_driver_conforms(app):
    await scheduler_conformance(app.manager("scheduler").create("memory"))


def test_observability_drivers_conform(app):
    for name in ["phoenix", "console", "otlp", "off"]:
        observability_conformance(app.manager("observability").create(name))
    observability_off_disables(app.manager("observability").create("off"))


def test_defaults_are_the_existing_classes(app):
    from agentkit.audio import OpenAISpeech
    from agentkit.db.engine import SQLiteDialect
    from agentkit.foundation.queue import Queue
    from agentkit.ingest import DefaultDocumentLoader
    from agentkit.pricing import Pricing

    assert isinstance(app.pricing, Pricing)
    assert isinstance(app.ingest, DefaultDocumentLoader)
    assert isinstance(app.speech, OpenAISpeech)
    assert isinstance(app.dialect, SQLiteDialect)
    assert isinstance(app.queue, Queue)


def test_storage_drivers_conform(tmp_path, app):
    storage_conformance(app.manager("storage").create("memory"))
    storage_conformance(app.manager("storage").driver())


async def test_ratelimit_drivers_conform(app):
    await ratelimit_conformance(app.manager("ratelimit").create("memory"))
    await ratelimit_conformance(app.manager("ratelimit").create("database"))


def test_guardrails_drivers_conform(app):
    for name in ["regex", "moderation"]:
        guardrails_conformance(app.manager("guardrails").create(name))


def test_durability_and_auth_and_vault_conform(app):
    durability_conformance(app.manager("durability").create("dbos"))
    auth_conformance(app.manager("auth").create("default"))
    auth_conformance(app.manager("auth").create("anonymous"))
    vault_conformance(app.manager("vault").create("fernet"))
    vault_conformance(app.manager("vault").create("env"))


async def test_memory_drivers_conform(app):
    await memory_store_conformance(app.manager("memory").create("in_memory"))
    await memory_store_conformance(app.memory)


def test_recall_strategies_conform(app):
    for name in ["hybrid", "keyword", "recency"]:
        recall_strategy_conformance(app.manager("memory_recall").create(name))


def test_rag_drivers_conform(app):
    for name in ["semantic", "fixed"]:
        chunker_conformance(app.manager("chunker").create(name))
    for name in ["identity", "lexical"]:
        reranker_conformance(app.manager("reranker").create(name))


async def test_in_memory_retriever_conforms(app):
    await retriever_conformance(app.manager("retriever").create("memory"))


async def test_learning_drivers_conform(app, repos):
    await extractor_conformance(app.manager("learning_extractor").create("model"))
    await extractor_conformance(app.manager("learning_extractor").create("heuristic"))
    await learning_strategy_conformance(app.manager("learning_strategy").create("none"))
    await learning_strategy_conformance(app.manager("learning_strategy").create("reflect_apply"), repos)
    await learning_sink_conformance(app.manager("learning_sink").create("memory"), repos)
    assert app.settings.learning_require_review is True


COMMS_DRIVERS = [
    "mailbox",
    "broadcast",
    "swarm",
    "pipeline",
    "handoff",
    "hub",
    "mesh",
    "hierarchy",
    "outbox",
    "blackboard",
    "pubsub",
    "groupchat",
]


async def test_comms_topologies_conform(app):
    for name in COMMS_DRIVERS:
        await topology_conformance(app.manager("comms").create(name))
    assert isinstance(app.comms, Topology)


async def test_pipeline_topology_feeds_stages(app):
    from agentkit.contracts import Topology

    topology = app.manager("comms").create("pipeline")
    calls: list[str] = []

    async def first(message: str) -> str:
        calls.append(f"first:{message}")
        return "second"

    async def second(message: str) -> str:
        calls.append(f"second:{message}")
        return "done"

    topology.register("one", first).register("two", second)
    result = await topology.broadcast("start", to=["one", "two"])
    assert result == {"one": "second", "two": "done"}
    assert calls == ["first:start", "second:second"]
    assert isinstance(topology, Topology)


async def test_task_and_planning_drivers_conform(app):
    await task_store_conformance(app.manager("tasks").create("memory"))
    await planning_conformance(app.manager("planning").create("single"))
    await planning_conformance(app.manager("planning").create("batched"))


def test_context_strategies_conform(app):
    for name in ["isolated", "shared", "summarized"]:
        context_strategy_conformance(app.manager("context").create(name))


async def test_middleware_graph_code_and_reporters_conform(app):
    await agent_middleware_conformance(app.manager("agent_middleware").create("noop"))
    await agent_middleware_conformance(app.manager("agent_middleware").create("logging"))
    for name in ["sequential", "parallel", "checkpointed"]:
        await graph_executor_conformance(app.manager("graph").create(name))
    await code_executor_conformance(app.manager("codeexec").create("local"))
    for name in ["text", "json", "pydantic"]:
        reporter_conformance(app.manager("evals_reporter").create(name))


def test_assert_trajectory(app):
    from types import SimpleNamespace

    from agentkit.evals import assert_trajectory

    result = SimpleNamespace(tool_calls=["search", "write", "publish"])
    assert_trajectory(result, calls=["search"], forbid=["delete"], order=["search", "publish"])
    import pytest

    with pytest.raises(AssertionError):
        assert_trajectory(result, calls=["missing"])
    with pytest.raises(AssertionError):
        assert_trajectory(result, order=["publish", "search"])


async def test_channel_drivers_conform(app):
    await channel_conformance(app.manager("channel").create("log"))
    assert {"log", "telegram", "slack", "email", "discord"} <= set(
        app.manager("channel").available()
    )


def test_notification_channel_drivers_conform(app):
    for name in ["log", "conversation", "telegram"]:
        notification_channel_conformance(app.manager("notification_channel").create(name))







