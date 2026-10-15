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

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agentkit import scheduler
from agentkit.config import AgentSettings
from agentkit.health import db_check, run_checks
from agentkit.runtime import Runtime, repositories
from agentkit.webui import (
    artifacts_api,
    config_api,
    introspect,
    scheduler_api,
    soul_api,
    workflows_api,
)
from agentkit.webui.context import Answer, WebUIContext, get_context

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
) -> FastAPI:
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
    app.state.webui = WebUIContext(runtime=runtime, settings=settings, answer=answer)

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
    ):
        app.include_router(module.router, prefix="/api")

    @app.get("/api/health", tags=["core"])
    async def health(ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
        ok, results = await run_checks([db_check(ctx.runtime)])
        return {"ok": ok, "checks": results}

    @app.post("/api/chat", tags=["core"])
    async def chat(body: ChatBody, ctx: WebUIContext = Depends(get_context)) -> dict[str, Any]:
        if ctx.answer is None:
            raise HTTPException(status_code=501, detail="chat is not enabled for this agent")
        result = await ctx.answer(body.conversation_id, body.text)
        return {
            "conversation_id": body.conversation_id,
            "output": result.output,
            "artifacts": result.artifacts,
            "usage": result.usage,
            "history_length": result.history_length,
        }

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
