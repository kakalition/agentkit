"""Shared conformance checkpoints every driver of a kind must satisfy.

A driver is conformant when it satisfies both its Protocol (runtime-checkable
``isinstance``) and the behavioral invariants below — the *contract*, not one
implementation's quirks. Each subsystem converts this module into a parametrized
``tests/contracts/test_<kind>_conformance.py`` run over every driver.
"""

from __future__ import annotations

from typing import Any

_MISSING = object()


def cache_conformance(store: Any) -> None:
    """Invariants shared by every cache driver (storing or not)."""
    from agentkit.contracts import CacheContract

    assert isinstance(store, CacheContract)
    store.flush()
    sentinel = object()
    # put() returns the value it was given
    assert store.put("conformance:put", 7) == 7
    # has() agrees with get()
    assert store.has("conformance:put") == (store.get("conformance:put", sentinel) is not sentinel)
    # remember() resolves and returns the factory result
    assert store.remember("conformance:remember", lambda: 42) == 42
    # a never-written key returns the caller's default
    assert store.get("conformance:absent", sentinel) is sentinel
    # forget() then get() returns the default
    store.forget("conformance:put")
    assert store.get("conformance:put", sentinel) is sentinel
    store.flush()


def prompt_conformance(store: Any) -> None:
    """Invariants shared by every prompt store."""
    from agentkit.contracts import PromptStore
    from agentkit.prompts import Prompt

    assert isinstance(store, PromptStore)
    assert store.get("conformance:prompt") is None
    store.register(Prompt(name="conformance:prompt", body="Hello {who}", version=1))
    assert store.get("conformance:prompt") is not None
    assert "conformance:prompt" in store.names()
    assert store.render("conformance:prompt", who="Ada") == "Hello Ada"


def embedder_conformance(embedder: Any) -> None:
    """Invariants shared by every embedder."""
    from agentkit.contracts import EmbedderContract

    assert isinstance(embedder, EmbedderContract)
    vectors = embedder.embed(["alpha", "beta"])
    assert len(vectors) == 2
    width = len(vectors[0])
    assert width > 0
    assert all(len(vector) == width for vector in vectors)


def pricing_conformance(provider: Any) -> None:
    from agentkit.contracts import PriceProvider

    assert isinstance(provider, PriceProvider)
    cost = provider.cost("not-a-real-model", input_tokens=100, output_tokens=100)
    assert isinstance(cost, float)
    assert cost >= 0.0


def ingest_conformance(loader: Any) -> None:
    from agentkit.contracts import DocumentLoader

    assert isinstance(loader, DocumentLoader)
    assert loader.supports(".txt") is True
    assert "hello" in loader.load(b"hello world", suffix=".txt")


def audio_conformance(speech: Any) -> None:
    from agentkit.contracts import Speech

    assert isinstance(speech, Speech)


def database_conformance(dialect: Any) -> None:
    from agentkit.contracts import Dialect

    assert isinstance(dialect, Dialect)
    assert dialect.async_url("sqlite+libsql:///x.db").startswith("sqlite+aiosqlite")


async def queue_conformance(driver: Any) -> None:
    from agentkit.contracts import QueueDriver

    assert isinstance(driver, QueueDriver)
    assert await driver.size() >= 0
    assert isinstance(await driver.failed(limit=1), list)


async def scheduler_conformance(driver: Any) -> None:
    from agentkit.contracts import SchedulerDriver

    assert isinstance(driver, SchedulerDriver)
    await driver.schedule_cron("conformance:job", "0 8 * * *", "noop")
    jobs = {job["name"]: job for job in await driver.list_jobs()}
    assert jobs["conformance:job"]["schedule"] == "0 8 * * *"
    assert await driver.set_enabled("conformance:job", False) is True
    assert await driver.remove_job("conformance:job") is True


def observability_conformance(tracer: Any) -> None:
    from agentkit.contracts import Tracer

    assert isinstance(tracer, Tracer)


def observability_off_disables(tracer: Any) -> None:
    from agentkit.config import AgentSettings

    assert tracer.setup(AgentSettings(observability="off")) is False


def storage_conformance(fs: Any) -> None:
    from agentkit.contracts import FileSystem

    assert isinstance(fs, FileSystem)
    fs.put("conformance/a.txt", "hello")
    assert fs.get("conformance/a.txt") == "hello"
    assert fs.get_bytes("conformance/a.txt") == b"hello"
    assert fs.exists("conformance/a.txt") is True
    assert "conformance/a.txt" in fs.list("conformance")
    assert fs.metadata("conformance/a.txt")["size"] == 5
    assert fs.delete("conformance/a.txt") is True
    assert fs.exists("conformance/a.txt") is False


async def ratelimit_conformance(limiter: Any) -> None:
    from agentkit.contracts import RateLimiterContract

    assert isinstance(limiter, RateLimiterContract)
    first = await limiter.hit("conformance", limit=1)
    assert first.allowed is True
    second = await limiter.hit("conformance", limit=1)
    assert second.allowed is False
    await limiter.reset("conformance")
    assert await limiter.peek("conformance") >= 0


def guardrails_conformance(scanner: Any) -> None:
    from agentkit.contracts import Scanner

    assert isinstance(scanner, Scanner)
    assert isinstance(scanner.scan("hello there"), list)
    assert isinstance(scanner.redact("email me at a@b.com"), str)


def durability_conformance(driver: Any) -> None:
    from agentkit.contracts import Durability

    assert isinstance(driver, Durability)


def auth_conformance(strategy: Any) -> None:
    from agentkit.contracts import AuthStrategy

    assert isinstance(strategy, AuthStrategy)
    assert strategy.default_actor() is not None


def vault_conformance(vault: Any) -> None:
    from agentkit.contracts import Vault

    assert isinstance(vault, Vault)


async def memory_store_conformance(store: Any) -> None:
    from agentkit.contracts import MemoryStore

    assert isinstance(store, MemoryStore)
    memory_id = await store.remember("the user likes tea", kind="preference")
    rows = await store.search("tea")
    assert any(getattr(row, "id", None) == memory_id for row in rows)
    assert await store.all()
    assert await store.forget(memory_id) is True
    assert await store.forget(memory_id) is False


def recall_strategy_conformance(strategy: Any) -> None:
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from agentkit.contracts import RecallStrategy

    assert isinstance(strategy, RecallStrategy)
    now = datetime.now(UTC)
    memory = SimpleNamespace(importance=0.5, last_used_at=now, updated_at=now, created_at=now)
    assert isinstance(strategy.score("query", 0.7, memory, now), float)


def chunker_conformance(chunker: Any) -> None:
    from agentkit.contracts import Chunker

    assert isinstance(chunker, Chunker)
    chunks = chunker.chunk("lorem ipsum " * 400)
    assert chunks and all(isinstance(chunk, str) for chunk in chunks)
    assert chunker.chunk("") == []


async def retriever_conformance(retriever: Any) -> None:
    from agentkit.contracts import Retriever

    assert isinstance(retriever, Retriever)
    if hasattr(retriever, "add"):
        retriever.add("the cat sat on the mat", source="s")
    assert isinstance(await retriever.search("cat", limit=3), list)


def reranker_conformance(reranker: Any) -> None:
    from types import SimpleNamespace

    from agentkit.contracts import Reranker

    assert isinstance(reranker, Reranker)
    hits = [SimpleNamespace(content="zzz"), SimpleNamespace(content="cat cat")]
    result = reranker.rerank("cat", hits)
    assert len(result) == 2
    assert {id(hit) for hit in result} == {id(hit) for hit in hits}


async def extractor_conformance(extractor: Any) -> None:
    from agentkit.contracts import Extractor

    assert isinstance(extractor, Extractor)
    result = await extractor.extract([], None)
    assert isinstance(result, dict)


async def learning_strategy_conformance(strategy: Any, repos: Any = None) -> None:
    from agentkit.contracts import LearningStrategy

    assert isinstance(strategy, LearningStrategy)
    result = await strategy.run(repos)
    assert isinstance(result, dict)


async def learning_sink_conformance(sink: Any, repos: Any) -> None:
    from agentkit.contracts import LearningSink

    assert isinstance(sink, LearningSink)
    assert await sink.store(repos, {}) == 0


async def topology_conformance(topology: Any) -> None:
    from agentkit.contracts import Topology

    assert isinstance(topology, Topology)
    assert isinstance(await topology.send("nobody", "ping"), bool)
    assert isinstance(await topology.broadcast("ping"), dict)


async def task_store_conformance(store: Any) -> None:
    from agentkit.contracts import TaskStore

    assert isinstance(store, TaskStore)
    await store.write([{"text": "one"}, {"text": "two"}])
    assert len(await store.read()) == 2
    todo = await store.add("three")
    assert todo["text"] == "three"
    updated = await store.update(todo["id"], status="completed")
    assert updated is not None and updated["status"] == "completed"
    assert await store.clear() == 3


async def planning_conformance(strategy: Any) -> None:
    from agentkit.contracts import PlanningStrategy

    assert isinstance(strategy, PlanningStrategy)
    steps = await strategy.plan("first; second")
    assert isinstance(steps, list)


def context_strategy_conformance(strategy: Any) -> None:
    from agentkit.contracts import ContextStrategy

    assert isinstance(strategy, ContextStrategy)
    strategy.context(None, "a task")  # must not raise


async def agent_middleware_conformance(middleware: Any) -> None:
    from agentkit.contracts import AgentMiddleware

    async def call_next() -> str:
        return "ok"

    assert isinstance(middleware, AgentMiddleware)
    await middleware.before_model(None)
    assert await middleware.after_model(None, "r") == "r"
    assert await middleware.wrap_model_call(None, call_next) == "ok"

    async def tool_next() -> str:
        return "tool-ok"

    assert await middleware.wrap_tool_call(None, "t", tool_next) == "tool-ok"


def _tiny_graph() -> Any:
    from agentkit.graph import END, StateGraph

    graph = StateGraph()
    graph.add_node("a", lambda state: {"x": 1})
    graph.add_edge("a", END)
    graph.set_entry("a")
    return graph


async def graph_executor_conformance(executor: Any) -> None:
    from agentkit.contracts import GraphExecutor

    assert isinstance(executor, GraphExecutor)
    state = await executor.run(_tiny_graph(), {})
    assert state.get("x") == 1


async def code_executor_conformance(executor: Any) -> None:
    from agentkit.contracts import CodeExecutor

    assert isinstance(executor, CodeExecutor)
    result = await executor.run("print('hi')")
    assert result.ok
    assert "hi" in result.stdout


def reporter_conformance(reporter: Any) -> None:
    from agentkit.contracts import Reporter
    from agentkit.evals import Case, CaseResult, Report

    assert isinstance(reporter, Reporter)
    report = Report(
        name="conformance",
        results=[CaseResult(case=Case(name="c", input="i"), output="o", passed=True)],
    )
    assert isinstance(reporter.render(report), str)


async def channel_conformance(channel: Any) -> None:
    from agentkit.contracts import Channel

    assert isinstance(channel, Channel)
    assert isinstance(channel.name, str)
    await channel.send("conformance:conv", "hello")
    assert channel.service() is not None


def notification_channel_conformance(channel: Any) -> None:
    from agentkit.contracts import NotificationChannel
    from agentkit.foundation.notifications import Notification

    class _Note(Notification):
        def content(self) -> str:
            return "hello"

    assert isinstance(channel, NotificationChannel)
    assert isinstance(channel.send(_Note()), str)


async def checkpoint_store_conformance(store: Any) -> None:
    from agentkit.contracts import CheckpointStore

    assert isinstance(store, CheckpointStore)
    await store.put("conformance:run", 0, {"x": 1}, label="n0")
    await store.put("conformance:run", 1, {"x": 2}, label="n1")
    latest = await store.latest("conformance:run")
    assert latest is not None
    assert len(await store.list("conformance:run")) == 2
    assert await store.get("conformance:run", 0) is not None
    assert await store.delete("conformance:run") == 2
    assert await store.latest("conformance:run") is None


def run_recorder_conformance(recorder: Any) -> None:
    from agentkit.contracts import RunRecorder
    from agentkit.runs import RunEvent

    assert isinstance(recorder, RunRecorder)
    event = recorder.record(RunEvent(kind="start", text="hi"))
    assert event.seq == 0
    assert recorder.events[0].kind == "start"


def spec_conformance(spec: Any) -> None:
    from agentkit.contracts import Spec

    assert isinstance(spec, Spec)
    assert isinstance(spec.spec_kind, str) and spec.spec_kind
    assert isinstance(spec.name, str)
    assert isinstance(spec.model_dump_json(), str)
    assert isinstance(spec.json_schema(), dict)
    assert isinstance(spec.render("json"), str)
    assert isinstance(spec.render("yaml"), str)


async def computer_conformance(computer: Any) -> None:
    from agentkit.contracts import Computer

    assert isinstance(computer, Computer)
    assert isinstance(await computer.goto("https://example.test"), str)
    assert isinstance(await computer.snapshot(), str)
    assert isinstance(await computer.click("#a"), str)
    assert isinstance(await computer.type("#a", "x"), str)
    assert await computer.evaluate("1 + 1") is not None
    await computer.close()


async def grader_conformance(grader: Any, case: Any, output: Any) -> None:
    from agentkit.contracts import Grader
    from agentkit.graders import run_grader

    assert isinstance(grader, Grader)
    assert isinstance(grader.name, str) and grader.name
    await run_grader(grader, case, output)  # must not raise


async def catalog_conformance(catalog: Any) -> None:
    from agentkit.contracts import Catalog

    assert isinstance(catalog, Catalog)
    assert isinstance(catalog.name, str)
    assert isinstance(await catalog.search(""), list)
    assert await catalog.get("does-not-exist") is None

