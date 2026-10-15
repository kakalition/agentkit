from __future__ import annotations

import pytest
from sqlmodel import Field

from agentkit import (
    App,
    Container,
    DeferrableProvider,
    Model,
    Notification,
    Provider,
    Section,
)
from agentkit import app as app_helper
from agentkit import cache as cache_helper
from agentkit import config as config_helper
from agentkit import dispatch as dispatch_helper
from agentkit import env as env_helper
from agentkit import event as event_helper
from agentkit import notify as notify_helper
from agentkit import storage as storage_helper
from agentkit.foundation.queue import Job
from agentkit.runtime import Runtime


# -- Container autowiring ---------------------------------------------------
class _Dep:
    pass


class _Service:
    def __init__(self, dep: _Dep) -> None:
        self.dep = dep


def test_container_autowires_classes():
    container = Container()
    service = container.make(_Service)
    assert isinstance(service, _Service)
    assert isinstance(service.dep, _Dep)


class _Impl:
    pass


class _Iface:
    pass


class _BindingsProvider(Provider):
    bindings = {_Iface: _Impl}
    singletons = {_Service: _Service}

    def register(self, app):  # noqa: ANN001
        pass


def test_provider_bindings_and_singletons(tmp_path, runtime: Runtime):
    app = App(name="p", settings=runtime.settings, discover=False)
    app.providers([_BindingsProvider])
    app.boot()
    assert isinstance(app.make(_Iface), _Impl)
    assert app.make(_Service) is app.make(_Service)   # singleton


# -- Deferred providers -----------------------------------------------------
_DEFERRED_BUILT: list[str] = []


class _DeferredProvider(DeferrableProvider):
    def provides(self):  # noqa: ANN201
        return ["deferred.thing"]

    def register(self, app):  # noqa: ANN001
        _DEFERRED_BUILT.append("registered")
        app.bind("deferred.thing", lambda c: "value")


def test_deferred_provider_loads_on_demand(runtime: Runtime):
    _DEFERRED_BUILT.clear()
    app = App(name="d", settings=runtime.settings, discover=False)
    app.providers([_DeferredProvider])
    app.boot()
    assert _DEFERRED_BUILT == []          # not registered at boot
    assert app.make("deferred.thing") == "value"
    assert _DEFERRED_BUILT == ["registered"]   # loaded on first use


# -- Global helpers ---------------------------------------------------------
class _AppSection(Section):
    env_prefix = "HELPERS_"
    greeting: str = "Hi!"


class _Note(Model, table=True):
    __tablename__ = "helper_notes"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: str = Field(index=True)
    text: str


class _Echo(Notification):
    channels = ("log",)

    def __init__(self, message: str) -> None:
        self.message = message

    def content(self) -> str:
        return self.message


class _Touch(Job):
    ran: list[str] = []

    def handle(self, app) -> None:  # noqa: ANN001
        _Touch.ran.append("touched")


async def test_global_helpers(runtime: Runtime, tmp_path, monkeypatch):
    monkeypatch.setenv("HELPERS_MARKER", "yes")
    app = App(name="h", settings=runtime.settings, discover=False)
    app.boot()

    assert env_helper("HELPERS_MARKER") == "yes"
    assert app_helper() is app
    assert app_helper("app") is app  # 'app' is bound to the app itself

    app.config("greeting", _AppSection)
    assert config_helper("greeting.greeting") == "Hi!"
    assert config_helper("greeting.missing", "fallback") == "fallback"
    assert config_helper("agent_name") == app.settings.agent_name

    cache_helper().put("k", 1)
    assert cache_helper().get("k") == 1

    storage_helper("local").put("hello.txt", "hi")
    assert storage_helper("local").get("hello.txt") == "hi"

    seen: list[str] = []
    app.on("greeting", lambda e: seen.append(e.get("detail")))
    event_helper("greeting", detail="hi")
    assert seen == ["hi"]

    notify_helper(_Echo("ping"))          # log channel; no error
    assert await dispatch_helper(_Touch()) is None
    assert _Touch.ran == ["touched"]


# -- Eloquent-style model helpers ------------------------------------------
async def test_model_first_or_create_and_find_or_fail(runtime: Runtime):
    app = App(name="m", settings=runtime.settings, discover=False)
    app.boot()

    created = await _Note.first_or_create(text="a")
    assert created.id is not None
    again = await _Note.first_or_create(text="a")
    assert again.id == created.id

    updated = await _Note.update_or_create(defaults={"text": "b"}, text="a")
    assert updated.id == created.id and updated.text == "b"

    assert (await _Note.find_or_fail(created.id)).text == "b"
    from agentkit.errors import NotFound

    with pytest.raises(NotFound):
        await _Note.find_or_fail(999999)
    with pytest.raises(NotFound):
        await _Note.first_or_fail(text="nope")


# -- Queue retry / flush ----------------------------------------------------
class _Boom(Job):
    max_retries = 1

    def handle(self, app) -> None:  # noqa: ANN001
        raise RuntimeError("boom")


async def test_queue_retry_and_flush(runtime: Runtime):
    app = App(name="q", settings=runtime.settings, discover=False)
    app.boot()
    await app.queue.push(_Boom())
    await app.queue.run_once()
    failed = await app.queue.failed()
    assert failed
    job_id = failed[0].id

    assert await app.queue.retry(job_id) is True
    assert await app.queue.failed() == []
    assert await app.queue.flush() == 0


# -- Fluent schedule extras -------------------------------------------------
def test_schedule_builder_flags(runtime: Runtime):
    app = App(name="s", settings=runtime.settings, discover=False)
    spec = (
        app.schedule("sync")
        .every_minute()
        .timezone("UTC")
        .description("sync notes")
        .without_overlapping()
        .on_one_server()
        .run_in_background()
        .build()
    )
    assert spec["cron"] == "* * * * *"
    assert spec["timezone"] == "UTC"
    assert spec["without_overlapping"] is True
    assert spec["run_in_background"] is True
    app.boot()   # persists without error
