"""T1 — Temporal durability driver, validated with a stub (no live server)."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from agentkit.config import AgentSettings
from agentkit.durability import DBOSDurability, TemporalDurability
from agentkit.errors import ConfigurationError
from agentkit.foundation.application import App
from agentkit.foundation.facade import using
from agentkit.runtime import Runtime


class _Handle:
    def __init__(self, workflow_id: str) -> None:
        self.id = workflow_id


class _Schedule:
    def __init__(self, *, action: Any, spec: Any) -> None:
        self.action = action
        self.spec = spec


class _ScheduleActionStartWorkflow:
    def __init__(self, workflow: str, arg: Any, *, id: str, task_queue: str) -> None:
        self.workflow = workflow
        self.arg = arg
        self.id = id
        self.task_queue = task_queue


class _ScheduleSpec:
    def __init__(self, *, cron_expressions: list[str], time_zone_name: str | None = None) -> None:
        self.cron_expressions = cron_expressions
        self.time_zone_name = time_zone_name


class _ScheduleHandle:
    def __init__(self, name: str, client: _StubClient) -> None:
        self.name = name
        self.client = client

    async def describe(self) -> Any:
        if self.name not in self.client.schedule_names:
            raise RuntimeError("schedule not found")
        return self

    async def update(self, _update: Any) -> None:
        self.client.updated.append(self.name)


class _StubClient:
    instances: list[_StubClient] = []

    def __init__(self) -> None:
        self.address = ""
        self.namespace = ""
        self.started: list[tuple[Any, Any, str, str]] = []
        self.created: list[tuple[str, Any]] = []
        self.updated: list[str] = []
        self.schedule_names: set[str] = set()

    @classmethod
    async def connect(cls, address: str, *, namespace: str = "default", **_: Any) -> _StubClient:
        client = cls()
        client.address = address
        client.namespace = namespace
        cls.instances.append(client)
        return client

    async def start_workflow(self, workflow: Any, arg: Any, *, id: str, task_queue: str, **_: Any) -> _Handle:
        self.started.append((workflow, arg, id, task_queue))
        return _Handle(id)

    def get_schedule_handle(self, name: str) -> _ScheduleHandle:
        return _ScheduleHandle(name, self)

    async def create_schedule(self, name: str, schedule: Any) -> None:
        self.created.append((name, schedule))
        self.schedule_names.add(name)


@pytest.fixture
def stub_temporal(monkeypatch: pytest.MonkeyPatch) -> type[_StubClient]:
    _StubClient.instances = []
    module = types.ModuleType("temporalio")
    client_module = types.ModuleType("temporalio.client")
    client_module.Client = _StubClient
    client_module.Schedule = _Schedule
    client_module.ScheduleActionStartWorkflow = _ScheduleActionStartWorkflow
    client_module.ScheduleSpec = _ScheduleSpec
    module.client = client_module
    monkeypatch.setitem(sys.modules, "temporalio", module)
    monkeypatch.setitem(sys.modules, "temporalio.client", client_module)
    return _StubClient


def _flow(qualified: str) -> Any:
    module, _, qualname = qualified.rpartition(".")

    def flow(*args: Any, **kwargs: Any) -> Any:
        return None

    flow.__module__ = module or "myapp"
    flow.__qualname__ = qualname or qualified
    return flow


def test_enqueue_delegates_by_qualified_name(stub_temporal: type[_StubClient], tmp_path: Any) -> None:
    settings = AgentSettings(agent_home=tmp_path)
    driver = TemporalDurability(None, settings=settings)
    driver.init(settings, queues=["agentkit"])
    flow = _flow("myapp.flows")
    assert driver.enqueue("agentkit", flow, 5, workflow_id="wf-1") == "wf-1"
    client = stub_temporal.instances[-1]
    assert client.started == [("myapp.flows", 5, "wf-1", "agentkit")]


def test_enqueue_generates_a_workflow_id(stub_temporal: type[_StubClient], tmp_path: Any) -> None:
    settings = AgentSettings(agent_home=tmp_path)
    driver = TemporalDurability(None, settings=settings)
    driver.init(settings, queues=["agentkit"])
    flow = _flow("myapp.flows")
    workflow_id = driver.enqueue("agentkit", flow, [1, 2])
    assert workflow_id.startswith("agentkit:myapp.flows:")
    client = stub_temporal.instances[-1]
    assert client.started[0][1] == [1, 2]


def test_apply_schedules_creates_then_updates(stub_temporal: type[_StubClient], tmp_path: Any) -> None:
    settings = AgentSettings(agent_home=tmp_path)
    driver = TemporalDurability(None, settings=settings)
    driver.init(settings, queues=["agentkit"])
    tick = _flow("myapp.sched")
    schedule = [{"schedule_name": "tick", "workflow_fn": tick, "schedule": "* * * * *"}]
    driver.apply_schedules(schedule)
    client = stub_temporal.instances[-1]
    assert client.created[0][0] == "tick"
    assert client.created[0][1].spec.cron_expressions == ["* * * * *"]
    assert client.created[0][1].action.workflow == "myapp.sched"
    driver.apply_schedules(schedule)
    assert client.updated == ["tick"]


def test_missing_temporalio_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setitem(sys.modules, "temporalio", None)
    monkeypatch.setitem(sys.modules, "temporalio.client", None)
    settings = AgentSettings(agent_home=tmp_path)
    driver = TemporalDurability(None, settings=settings)
    with pytest.raises(ConfigurationError, match="agentkit\\[temporal\\]"):
        driver.init(settings, queues=["agentkit"])


def _app(runtime: Runtime, **updates: Any) -> App:
    settings = runtime.settings.model_copy(update=updates) if updates else runtime.settings
    app = App(name="dur", settings=settings, discover=False)
    app._runtime = runtime
    return app


def test_default_driver_is_dbos(runtime: Runtime) -> None:
    app = _app(runtime)
    with using(app):
        assert isinstance(app.manager("durability").driver(), DBOSDurability)


def test_temporal_driver_selected_from_settings(runtime: Runtime) -> None:
    app = _app(runtime, durability_driver="temporal")
    with using(app):
        assert app.manager("durability").configured_driver() == "temporal"
        driver = app.manager("durability").driver()
    assert isinstance(driver, TemporalDurability)
    assert driver.address == runtime.settings.temporal_address


def test_init_scheduler_routes_through_temporal(
    stub_temporal: type[_StubClient], runtime: Runtime, tmp_path: Any
) -> None:
    from agentkit import scheduler

    settings = runtime.settings.model_copy(update={"durability_driver": "temporal"})
    app = App(name="dur", settings=settings, discover=False)
    app._runtime = runtime
    with using(app):
        scheduler.init_scheduler(settings, tick_cron="*/5 * * * *", app=app)
    client = stub_temporal.instances[-1]
    assert client.created[-1][0] == scheduler.TICK_SCHEDULE_NAME
    assert client.created[-1][1].spec.cron_expressions == ["*/5 * * * *"]
