"""Serve the web UI, standalone or as a supervised service."""

from __future__ import annotations

from agentkit.config import AgentSettings, get_settings
from agentkit.guardrails import warn_if_exposed
from agentkit.runtime import Runtime, build_runtime
from agentkit.supervise import Service
from agentkit.webui.app import build_webui_app
from agentkit.webui.context import Answer


def serve_webui(
    *,
    runtime: Runtime | None = None,
    settings: AgentSettings | None = None,
    answer: Answer | None = None,
    host: str | None = None,
    port: int | None = None,
) -> None:
    """Run the web UI with uvicorn (blocking)."""
    settings = settings or (runtime.settings if runtime is not None else get_settings())
    runtime = runtime or build_runtime(settings)
    host = host or settings.webui_host
    port = port or settings.webui_port
    app = build_webui_app(runtime=runtime, settings=settings, answer=answer)
    warn_if_exposed(host, "the webui")

    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level=str(settings.log_level).lower())


def webui_service(
    *,
    runtime: Runtime | None = None,
    settings: AgentSettings | None = None,
    answer: Answer | None = None,
) -> Service:
    """A :class:`~agentkit.supervise.Service` factory for ``run_all``."""
    return Service(
        "webui",
        lambda: serve_webui(runtime=runtime, settings=settings, answer=answer),
    )
