"""Durable A2A ``TaskStore`` backed by the app's async SQLAlchemy database."""

from __future__ import annotations

from a2a import types as t
from a2a.server.context import ServerCallContext
from a2a.server.tasks import TaskStore
from google.protobuf import json_format

from agentkit.runtime import Runtime, repositories


class SQLAlchemyTaskStore(TaskStore):
    def __init__(self, runtime: Runtime) -> None:
        self._runtime = runtime
        self._owner = runtime.settings.owner_id

    @staticmethod
    def _state(task: t.Task) -> str:
        if task.HasField("status"):
            return t.TaskState.Name(task.status.state)
        return "TASK_STATE_UNSPECIFIED"

    async def _save(self, task: t.Task) -> None:
        payload = json_format.MessageToJson(task)
        async with repositories(self._runtime) as repos:
            await repos.a2a.upsert(
                task.id, self._owner, task.context_id or None, self._state(task), payload
            )

    async def _get(self, task_id: str) -> str | None:
        async with repositories(self._runtime) as repos:
            record = await repos.a2a.get(task_id)
            return record.payload if record is not None else None

    async def _delete(self, task_id: str) -> None:
        async with repositories(self._runtime) as repos:
            await repos.a2a.delete(task_id)

    async def _list(self) -> list[str]:
        async with repositories(self._runtime) as repos:
            return [record.payload for record in await repos.a2a.list()]

    async def save(self, task: t.Task, context: ServerCallContext) -> None:
        await self._save(task)

    async def get(self, task_id: str, context: ServerCallContext) -> t.Task | None:
        payload = await self._get(task_id)
        return json_format.Parse(payload, t.Task()) if payload else None

    async def delete(self, task_id: str, context: ServerCallContext) -> None:
        await self._delete(task_id)

    async def list(self, params: t.ListTasksRequest, context: ServerCallContext) -> t.ListTasksResponse:
        payloads = await self._list()
        tasks = []
        for payload in payloads:
            task = json_format.Parse(payload, t.Task())
            if params.context_id and task.context_id != params.context_id:
                continue
            tasks.append(task)
        total = len(tasks)
        page_size = params.page_size or total or 1
        page = tasks[:page_size]
        return t.ListTasksResponse(tasks=page, page_size=len(page), total_size=total)
