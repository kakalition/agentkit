"""Run several long-lived services in one process (for a single `up` command).

Each service is a blocking callable; ``run_all`` starts them on daemon threads
and blocks until SIGINT/SIGTERM (or a supplied stop event).
"""

from __future__ import annotations

import contextlib
import signal
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agentkit.logging import get_logger

if TYPE_CHECKING:
    from agentkit.config import AgentSettings
    from agentkit.runtime import Runtime
    from agentkit.webui.context import Answer

log = get_logger("agentkit.supervise")


@dataclass
class Service:
    name: str
    run: Callable[[], None]


def run_all(
    services: list[Service],
    *,
    stop_event: threading.Event | None = None,
    settings: AgentSettings | None = None,
    runtime: Runtime | None = None,
    webui_answer: Answer | None = None,
    webui: bool = True,
    app: object | None = None,
) -> None:
    """Start every service on its own thread; block until shutdown.

    When ``settings`` is supplied and its ``webui_enabled`` flag is set, the
    in-core web UI is appended automatically (unless ``webui=False`` or a
    service named ``webui`` is already present).

    When ``app`` is supplied it becomes the *current app* inside every worker
    thread, so facades resolve even though a contextvar would not cross the
    thread boundary.
    """
    if (
        webui
        and settings is not None
        and getattr(settings, "webui_enabled", False)
        and not any(service.name == "webui" for service in services)
    ):
        from agentkit.webui.server import webui_service

        services = [
            *services,
            webui_service(runtime=runtime, settings=settings, answer=webui_answer),
        ]
    stop = stop_event or threading.Event()
    threads: list[threading.Thread] = []
    for service in services:
        thread = threading.Thread(
            target=_guarded, args=(service, app), name=service.name, daemon=True
        )
        thread.start()
        threads.append(thread)
        log.info("started service %s", service.name)

    def _on_signal(signum: int, frame: object) -> None:
        log.info("signal %s received; shutting down", signum)
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(ValueError, OSError):
            signal.signal(sig, _on_signal)

    while not stop.is_set():
        stop.wait(0.25)


def _guarded(service: Service, app: object | None = None) -> None:
    if app is not None:
        from agentkit.foundation.facade import set_current_app

        set_current_app(app)
    try:
        service.run()
    except (KeyboardInterrupt, SystemExit):  # normal during shutdown
        return
    except BaseException:  # pragma: no cover - a crashing service must not kill others
        with contextlib.suppress(Exception):  # stream may be closed during shutdown
            log.exception("service %s crashed", service.name)
