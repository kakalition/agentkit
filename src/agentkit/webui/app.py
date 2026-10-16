"""FastAPI application factory for the operator web UI.

The app is built once (at agent startup or by the standalone ``agentkit webui``
command) and holds the agent's :class:`~agentkit.runtime.Runtime` plus an
optional chat ``answer`` callable. All ``/api`` routes read through the shared
process-wide DB lock; the SPA is served from ``web/dist`` (or the packaged
``static/``) with a minimal fallback page when no build exists.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agentkit import scheduler
from agentkit.config import AgentSettings
from agentkit.health import readiness_checks, run_checks
from agentkit.runtime import Runtime, repositories
from agentkit.security import system_actor
from agentkit.security.authenticator import AuthError, ForbiddenError
from agentkit.webui import (
    artifacts_api,
    config_api,
    data_api,
    introspect,
    learning_api,
    openai_api,
    scheduler_api,
    soul_api,
    workflows_api,
)
from agentkit.webui.auth import install_auth, install_rate_limit
from agentkit.webui.context import Answer, WebUIContext, get_actor, get_context

FALLBACK_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>agentkit web UI</title>
<style>
  body { font-family: ui-sans-serif, system-ui, sans-serif; margin: 0;
         display: grid; place-items: center; min-height: 100vh; background: #0b0b0c; color: #e7e7ea; }
  main { max-width: 40rem; padding: 2rem; line-height: 1.5; }
  code { background: #1c1c1f; padding: .15rem .4rem; border-radius: .3rem; }
</style>
</head>
<body>
<main>
  <h1>agentkit web UI</h1>
  <p>The UI bundle has not been built yet. The API is available under <code>/api</code>.</p>
  <p>Build the frontend with:</p>
  <pre><code>cd web &amp;&amp; bun install &amp;&amp; bun run build</code></pre>
</main>
</body>
</html>
"""


class ChatBody(BaseModel):
    conversation_id: str = "webui:default"
    text: str
    ephemeral: bool = False


class CancelBody(BaseModel):
    conversation_id: str = "webui:default"


def _static_candidates() -> list[Path]:
    here = Path(__file__).resolve()
    repo_dist = here.parents[3] / "web" / "dist"
    packaged = here.parent / "static"
    return [repo_dist, packaged]


def find_build() -> Path | None:
    for candidate in _static_candidates():
        if (candidate / "index.html").is_file():
            return candidate
    return None


def _index_response(build: Path | None) -> Any:
    if build is not None:
        return FileResponse(build / "index.html")
    return HTMLResponse(FALLBACK_HTML)


def build_webui_app(
    *,
    runtime: Runtime,
    settings: AgentSettings | None = None,
    answer: Answer | None = None,
    app: Any = None,
) -> FastAPI:
    agent_app = app
    settings = settings or runtime.settings
    # The scheduler only touches the shared ``scheduled_jobs`` table, so it uses
    # agentkit's base repositories — an app's domain factory need not provide it.
    scheduler.ensure_configured(settings)

    app = FastAPI(
        title=f"{settings.agent_name} web UI",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.webui = WebUIContext(
        runtime=runtime,
        settings=settings,
        answer=answer,
        actor=system_actor(settings),
        app=agent_app,
    )
    install_rate_limit(app, runtime=runtime, settings=settings)
    install_auth(app, runtime=runtime, settings=settings)

    @app.exception_handler(AuthError)
    async def _unauthorized(_request: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.http_status)

    @app.exception_handler(ForbiddenError)
    async def _forbidden(_request: Request, exc: ForbiddenError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.http_status)

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        # Surface the real error to the operator console instead of a blank 500.
        return JSONResponse(
            status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"}
        )

    for module in (
        config_api,
        introspect,
        scheduler_api,
        workflows_api,
        soul_api,
        artifacts_api,
        learning_api,
        data_api,
    ):
        app.include_router(module.router, prefix="/api")
    app.include_router(openai_api.router)

    if getattr(settings, "metrics_enabled", False):
        from agentkit import metrics

        metrics.enable(settings)
        metrics_path = getattr(settings, "metrics_path", "/metrics") or "/metrics"

        @app.get(metrics_path, include_in_schema=False)
        async def _metrics() -> Response:
            return Response(metrics.render(), media_type=metrics.content_type())

    @app.get("/api/health", tags=["core"])
    async def health(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
        ok, results = await run_checks(readiness_checks(ctx.runtime, ctx.settings))
        return {"ok": ok, "checks": results}

    @app.get("/api/whoami", tags=["core"])
    async def whoami(request: Request) -> dict[str, Any]:
        actor = getattr(request.state, "actor", None) or system_actor(settings)
        return {
            "owner_id": actor.owner_id,
            "subject": actor.subject,
            "roles": sorted(actor.roles),
            "method": actor.method,
            "authenticated": actor.authenticated,
        }

    @app.post("/api/chat", tags=["core"])
    async def chat(
        body: ChatBody,
        ctx: WebUIContext = Depends(get_context),
        actor: Any = Depends(get_actor),
    ) -> dict[str, Any]:
        if ctx.answer is None:
            raise HTTPException(status_code=501, detail="chat is not enabled for this agent")
        result = await ctx.answer(
            body.conversation_id, body.text, actor=actor, ephemeral=body.ephemeral
        )
        return {
            "conversation_id": body.conversation_id,
            "output": result.output,
            "artifacts": result.artifacts,
            "usage": result.usage,
            "history_length": result.history_length,
        }

    @app.post("/api/chat/stream", tags=["core"])
    async def chat_stream(
        body: ChatBody,
        ctx: WebUIContext = Depends(get_context),
        actor: Any = Depends(get_actor),
    ) -> Any:
        if ctx.app is None or not hasattr(ctx.app, "stream"):
            raise HTTPException(status_code=501, detail="streaming is not enabled for this agent")

        async def _stream() -> Any:
            yield {"event": "hello", "data": "{}"}
            async for event in ctx.app.stream(
                body.text,
                conversation_id=body.conversation_id,
                actor=actor,
                ephemeral=body.ephemeral,
            ):
                kind = getattr(event, "kind", "text")
                payload = getattr(event, "text", None)
                if kind == "final":
                    result = getattr(event, "result", None)
                    payload = json.dumps(
                        {
                            "output": getattr(result, "output", ""),
                            "history_length": getattr(result, "history_length", 0),
                            "usage": getattr(result, "usage", None),
                        }
                    )
                yield {"event": kind, "data": payload or ""}
            yield {"event": "done", "data": "{}"}

        return EventSourceResponse(_stream())

    @app.post("/api/chat/cancel", tags=["core"])
    async def chat_cancel(body: CancelBody, ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
        if ctx.app is None or not hasattr(ctx.app, "cancel"):
            raise HTTPException(status_code=501, detail="cancellation is not enabled")
        return {"cancelled": bool(ctx.app.cancel(body.conversation_id))}

    @app.get("/api/approvals", tags=["core"])
    async def list_approvals(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
        if ctx.app is None or not hasattr(ctx.app, "approvals"):
            return {"approvals": []}
        pending = ctx.app.approvals.pending()
        return {
            "approvals": [
                {"tool_call_id": r.tool_call_id, "tool_name": r.tool_name, "args": r.args}
                for r in pending
            ]
        }

    @app.post("/api/approvals/{tool_call_id}", tags=["core"])
    async def decide_approval(
        tool_call_id: str, body: dict[str, Any], ctx: WebUIContext = Depends(get_context)
    ) -> dict[str, Any]:
        if ctx.app is None or not hasattr(ctx.app, "approvals"):
            raise HTTPException(status_code=501, detail="approvals are not enabled")
        decided = ctx.app.approvals.decide(tool_call_id, bool(body.get("approved", False)))
        if not decided:
            raise HTTPException(status_code=404, detail="no such pending approval")
        return {"tool_call_id": tool_call_id, "approved": bool(body.get("approved", False))}

    @app.get("/api/events", tags=["core"])
    async def events(ctx: WebUIContext = Depends(get_context)) -> EventSourceResponse:
        async def stream():
            yield {"event": "hello", "data": "{}"}
            while True:
                snapshot = await _snapshot(ctx)
                yield {"event": "tick", "data": json.dumps(snapshot)}
                await asyncio.sleep(5)

        return EventSourceResponse(stream())

    _install_spa(app)
    return app


async def _snapshot(ctx: WebUIContext) -> dict[str, Any]:
    try:
        async with repositories(ctx.runtime) as repos:
            conversations = len(await repos.conversations.list(limit=1000))
            totals = await repos.usage.totals()
        schedules = len(await scheduler.list_jobs())
    except Exception as exc:  # pragma: no cover - defensive
        return {"error": str(exc)}
    return {"conversations": conversations, "schedules": schedules, "usage": totals}


def _install_spa(app: FastAPI) -> None:
    build = find_build()
    if build is not None and (build / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=build / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def _index() -> Any:
        return _index_response(build)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa(full_path: str) -> Any:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        if build is not None:
            root = build.resolve()
            candidate = (root / full_path).resolve()
            if candidate.is_file() and root in candidate.parents:
                return FileResponse(candidate)
        return _index_response(build)
