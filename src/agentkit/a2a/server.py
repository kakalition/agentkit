"""Turn an app's answer function into an A2A server (task-based flow)."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from a2a import types as t
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import TaskUpdater
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from agentkit.guardrails import warn_if_exposed

Answer = Callable[[str], Awaitable[str]]


class _AuthMiddleware:
    """Enforce bearer auth on the JSON-RPC route; keep the card/healthz public."""

    def __init__(self, app: Any, authenticator: Any) -> None:
        self.app = app
        self.authenticator = authenticator

    @staticmethod
    def _public(path: str) -> bool:
        return path == "/healthz" or path.startswith("/.well-known/") or "agent-card" in path

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or self._public(scope.get("path", "")):
            await self.app(scope, receive, send)
            return
        from agentkit.security.authenticator import AuthError, ForbiddenError

        try:
            actor = await self.authenticator.authenticate_request(Request(scope))
        except (AuthError, ForbiddenError) as exc:
            response = JSONResponse(
                {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.http_status
            )
            await response(scope, receive, send)
            return
        scope.setdefault("state", {})["actor"] = actor
        await self.app(scope, receive, send)


class TaskAgentExecutor(AgentExecutor):
    """Generic executor: enqueue a Task, run ``answer``, attach the reply."""

    def __init__(self, answer: Answer) -> None:
        self._answer = answer
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or str(uuid.uuid4())
        context_id = context.context_id or ""
        await event_queue.enqueue_event(
            t.Task(
                id=task_id,
                context_id=context_id,
                status=t.TaskStatus(state=t.TaskState.TASK_STATE_SUBMITTED),
            )
        )
        updater = TaskUpdater(event_queue, task_id, context_id)
        await updater.start_work()
        work = asyncio.ensure_future(self._answer(context.get_user_input()))
        self._tasks[task_id] = work
        try:
            text = await work
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await updater.cancel()
            return
        except Exception as exc:
            await updater.failed(
                message=t.Message(
                    message_id=str(uuid.uuid4()),
                    role=t.Role.ROLE_AGENT,
                    parts=[t.Part(text=f"error: {type(exc).__name__}")],
                    task_id=task_id,
                    context_id=context_id,
                )
            )
            return
        finally:
            self._tasks.pop(task_id, None)
        await updater.add_artifact([t.Part(text=text)], name="result")
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel an in-flight task and report the canceled status."""
        task_id = context.task_id or ""
        work = self._tasks.pop(task_id, None)
        if work is not None and not work.done():
            work.cancel()
        updater = TaskUpdater(event_queue, task_id, context.context_id or "")
        with contextlib.suppress(Exception):
            await updater.cancel()


def _card_defaults(settings: Any) -> tuple[str, str]:
    if settings is None:
        try:
            from agentkit.config import get_settings

            settings = get_settings()
        except Exception:  # pragma: no cover - defensive
            settings = None
    name = str(getattr(settings, "a2a_card_name", "") or "Agent")
    url = str(getattr(settings, "a2a_public_url", "") or "http://127.0.0.1:9000")
    return name, url


def build_card(
    *,
    name: str | None = None,
    description: str,
    url: str | None = None,
    version: str = "1.0.0",
    skills: list[dict[str, Any]] | None = None,
    input_modes: list[str] | None = None,
    output_modes: list[str] | None = None,
    settings: Any = None,
) -> t.AgentCard:
    if name is None or url is None:
        default_name, default_url = _card_defaults(settings)
        name = name if name is not None else default_name
        url = url if url is not None else default_url
    skill_models = [
        t.AgentSkill(
            id=skill["id"],
            name=skill.get("name", skill["id"]),
            description=skill.get("description", ""),
            tags=list(skill.get("tags", [])),
        )
        for skill in (skills or [])
    ]
    return t.AgentCard(
        name=name,
        description=description,
        version=version,
        supported_interfaces=[
            t.AgentInterface(url=url, protocol_binding="JSONRPC", protocol_version="1.0")
        ],
        default_input_modes=input_modes or ["text/plain"],
        default_output_modes=output_modes or ["text/plain"],
        capabilities=t.AgentCapabilities(),
        skills=skill_models,
    )


def build_a2a_app(
    *,
    card: t.AgentCard,
    executor: AgentExecutor,
    task_store: Any,
    lifespan: Callable[[Starlette], Any] | None = None,
    healthz: Callable[[], bool] | None = None,
    auth: Any = None,
) -> Starlette:
    """Build the Starlette A2A app (agent card + JSON-RPC + optional /healthz)."""
    handler = DefaultRequestHandler(
        agent_executor=executor, task_store=task_store, agent_card=card
    )
    routes: list[Any] = []
    if healthz is not None:
        async def _healthz(request: Any) -> JSONResponse:
            try:
                ok = healthz()
            except Exception as exc:  # pragma: no cover - defensive
                return JSONResponse({"status": "error", "detail": str(exc)}, status_code=503)
            return JSONResponse({"status": "ok" if ok else "error"}, status_code=200 if ok else 503)

        routes.append(Route("/healthz", _healthz))
    routes += create_agent_card_routes(card) + create_jsonrpc_routes(handler, "/")

    @asynccontextmanager
    async def default_lifespan(app: Starlette):
        yield

    starlette_app = Starlette(routes=routes, lifespan=lifespan or default_lifespan)
    if auth is not None and getattr(auth, "enabled", False):
        starlette_app.add_middleware(_AuthMiddleware, authenticator=auth)
    return starlette_app


def serve_a2a(app: Starlette, *, host: str = "127.0.0.1", port: int = 9000) -> None:
    import uvicorn

    warn_if_exposed(host, "the A2A server")
    uvicorn.run(app, host=host, port=port)
