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

from agentkit.logging import get_logger

log = get_logger("agentkit.supervise")


@dataclass
class Service:
    name: str
    run: Callable[[], None]


def run_all(services: list[Service], *, stop_event: threading.Event | None = None) -> None:
    """Start every service on its own thread; block until shutdown."""
    stop = stop_event or threading.Event()
    threads: list[threading.Thread] = []
    for service in services:
        thread = threading.Thread(target=_guarded, args=(service,), name=service.name, daemon=True)
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


def _guarded(service: Service) -> None:
    try:
        service.run()
    except (KeyboardInterrupt, SystemExit):  # normal during shutdown
        return
    except BaseException:  # pragma: no cover - a crashing service must not kill others
        with contextlib.suppress(Exception):  # stream may be closed during shutdown
            log.exception("service %s crashed", service.name)
