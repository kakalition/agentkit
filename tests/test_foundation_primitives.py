from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from sqlmodel import Field

from agentkit import (
    App,
    Cache,
    CacheStore,
    Filesystem,
    Job,
    Listener,
    Middleware,
    Model,
    Notification,
    Repository,
    Storage,
    ValidationError,
    validate,
)
from agentkit.db.repositories import Repositories
from agentkit.runtime import Runtime


class Primitive(Model, table=True):
    __tablename__ = "primitive_notes"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: str = Field(index=True)
    text: str
    pinned: bool = False


class PrimitiveRepo(Repository[Primitive]):
    model = Primitive


class PrimitiveRepositories(Repositories):
    repositories = {"primitives": PrimitiveRepo}


def _app(runtime: Runtime, repos_factory=Repositories) -> App:
    return App(name="prims", settings=runtime.settings, discover=False, repos_factory=repos_factory)


# -- Repository base --------------------------------------------------------
async def test_repository_crud(runtime: Runtime):
    app = _app(runtime, PrimitiveRepositories)
    app.boot()
    async with app.repositories() as repos:
        repo = repos.primitives
        assert isinstance(repo, PrimitiveRepo)

        note = await repo.create(text="hello", pinned=True)
        assert note.owner_id == "owner"
        assert await repo.count() == 1

        got = await repo.get(note.id)
        assert got is not None and got.text == "hello"
        assert await repo.exists(note.id) is True
        assert (await repo.find(note.id)).text == "hello"
        first = await repo.where(pinned=True).first()
        assert first is not None and first.text == "hello"
        assert await repo.where(pinned=True).count() == 1

        updated = await repo.update(note.id, text="hi")
        assert updated is not None and updated.text == "hi"
        assert await repo.first(text="hi") is not None

        page = await repo.paginate(page=1, per_page=10)
        assert page["total"] == 1 and page["pages"] == 1

        assert await repo.delete(note.id) is True
        assert await repo.delete(note.id) is False
        assert await repo.count() == 0


async def test_repository_update_or_create(runtime: Runtime):
    app = _app(runtime, PrimitiveRepositories)
    app.boot()
    async with app.repositories() as repos:
        repo = repos.primitives
        created, was_created = await repo.update_or_create(defaults={"pinned": True}, text="a")
        assert was_created is True
        again, was_created = await repo.update_or_create(defaults={"pinned": False}, text="a")
        assert was_created is False
        assert again.id == created.id and again.pinned is False


# -- fluent Schedule --------------------------------------------------------
async def test_fluent_schedule_applies_to_db(runtime: Runtime):
    app = _app(runtime)
    app.schedule("ping").every_minute()
    app.schedule("digest", args={"period": "week"}).daily_at("08:00")
    app.boot()

    async with app.repositories() as repos:
        jobs = {job.name: job for job in await repos.schedules.list()}
    assert jobs["schedule:ping"].schedule == "* * * * *"
    assert jobs["schedule:digest"].schedule == "0 8 * * *"
    assert jobs["schedule:digest"].task == "digest"


async def test_fluent_schedule_one_off(runtime: Runtime):
    app = _app(runtime)
    app.schedule("welcome").at("2030-01-01T09:00")
    app.boot()
    async with app.repositories() as repos:
        job = (await repos.schedules.list())[0]
    assert job.kind == "once"


# -- Notifications ----------------------------------------------------------
class ReminderDue(Notification):
    channels = ("log", "conversation")

    def __init__(self, message: str) -> None:
        self.message = message

    def content(self) -> str:
        return self.message

    def to_conversation(self) -> str:
        return f"⏰ Reminder: {self.message}"


async def test_notification_delivers_to_conversation(runtime: Runtime):
    app = _app(runtime)
    app.boot()
    sent = app.notify(ReminderDue("stretch"), conversation_id="cli:1")

    assert {item.channel for item in sent} == {"log", "conversation"}
    async with app.repositories() as repos:
        messages = await repos.messages.list("cli:1")
    assert messages and "Reminder: stretch" in messages[0].payload


def test_notifier_custom_channel(runtime: Runtime):
    app = _app(runtime)
    app.boot()
    inbox: list[str] = []
    app.notifier.channel(
        "inbox", lambda notification, conversation_id=None: inbox.append(notification.content())
    )

    class Ping(Notification):
        channels = ("inbox",)

        def content(self) -> str:
            return "pong"

    app.notify(Ping())
    assert inbox == ["pong"]


# -- Jobs + cache -----------------------------------------------------------
async def test_job_dispatch(runtime: Runtime):
    app = _app(runtime)
    ran: list[str] = []

    class Work(Job):
        def handle(self, app) -> None:
            ran.append("ok")

    await app.dispatch(Work())
    assert ran == ["ok"]


def test_cache_store_ttl_and_remember():
    cache = CacheStore()
    cache.put("a", 1)
    assert cache.get("a") == 1
    assert cache.has("a") is True
    assert cache.remember("b", lambda: 2) == 2
    assert cache.remember("b", lambda: 99) == 2
    cache.forget("a")
    assert cache.get("a") is None
    cache.flush()
    assert cache.has("b") is False


def test_cache_facade(runtime: Runtime):
    app = _app(runtime)
    app.boot()
    Cache.put("k", 5)
    assert Cache.get("k") == 5
    assert Cache.remember("k", lambda: 1) == 5


# -- Storage ----------------------------------------------------------------
def test_filesystem_and_storage_facade(tmp_path: Path, runtime: Runtime):
    store = Filesystem(tmp_path / "files")
    store.put("reports/q4.md", "hello")
    assert store.get("reports/q4.md") == "hello"
    assert store.exists("reports/q4.md") is True
    assert "reports/q4.md" in store.list("reports")
    assert store.delete("reports/q4.md") is True

    app = _app(runtime)
    app.boot()
    Storage.put("note.txt", "hi")
    assert Storage.get("note.txt") == "hi"


# -- Validation -------------------------------------------------------------
def test_validate_ok_and_errors():
    assert validate({"text": "stretch"}, {"text": ["required", "min:3"]}) == {"text": "stretch"}
    with pytest.raises(ValidationError) as excinfo:
        validate({"text": ""}, {"text": ["required"]})
    assert "errors" in excinfo.value.detail


def test_validate_callable_rule():
    def even(value: int) -> str | None:
        return None if value % 2 == 0 else "must be even"

    assert validate({"n": 4}, {"n": [even]}) == {"n": 4}
    with pytest.raises(ValidationError):
        validate({"n": 3}, {"n": [even]})


# -- Listener + Middleware bases -------------------------------------------
def test_listener_base(runtime: Runtime):
    app = _app(runtime)
    app.boot()
    seen: list[str] = []

    class Ping(Listener):
        event = "ping"

        def handle(self, event) -> None:
            seen.append(event.get("detail"))

    app.on("ping", Ping())
    app.events.dispatch("ping", detail="hi")
    assert seen == ["hi"]


async def test_middleware_base(runtime: Runtime):
    app = _app(runtime)
    app._model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("ok")]))
    from agentkit import Agent as _Agent

    app.agent(_Agent.make("prims").instructions("x").output(str))
    calls: list[str] = []

    class Counter(Middleware):
        async def handle(self, turn, call_next):
            calls.append(turn.text)
            return await call_next()

    app.middleware(Counter())
    app.boot()
    await app.run("hi")
    assert calls == ["hi"]


# -- Queue ------------------------------------------------------------------
_ran: list[str] = []


class _WriteJob(Job):
    def __init__(self, value: str) -> None:
        self.value = value

    def handle(self, app) -> None:  # noqa: ANN001
        _ran.append(self.value)


class _BoomJob(Job):
    max_retries = 3

    def handle(self, app) -> None:  # noqa: ANN001
        raise RuntimeError("boom")


def test_job_serialize_roundtrip():
    from agentkit.foundation.queue import deserialize_job, serialize_job

    payload = serialize_job(_WriteJob("a"))
    assert payload["kwargs"] == {"value": "a"}
    assert payload["job"].endswith(":_WriteJob")
    assert deserialize_job(payload).value == "a"


async def test_queue_push_and_run_once(runtime: Runtime):
    app = _app(runtime)
    app.boot()
    _ran.clear()
    await app.queue.push(_WriteJob("q"))
    assert await app.queue.size() >= 1
    assert await app.queue.run_once() is True
    assert _ran == ["q"]
    assert await app.queue.run_once() is False  # queue drained


async def test_app_dispatch_honours_queue_enabled(runtime: Runtime):
    runtime.settings.queue_enabled = True
    try:
        app = _app(runtime)
        app.boot()
        _ran.clear()
        job_id = await app.dispatch(_WriteJob("d"))
        assert isinstance(job_id, int)
        assert _ran == []                 # not run inline; it was queued
        assert await app.queue.run_once() is True
        assert _ran == ["d"]
    finally:
        runtime.settings.queue_enabled = False


async def test_queue_marks_failed_after_retries(runtime: Runtime):
    app = _app(runtime)
    app.boot()
    await app.queue.push(_BoomJob())
    # Each run retries the failing job until max_retries is reached.
    for _ in range(_BoomJob.max_retries):
        assert await app.queue.run_once() is True
    assert await app.queue.run_once() is False   # failed jobs are not eligible
    failed = await app.queue.failed()
    assert failed and failed[0].error
