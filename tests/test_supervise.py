from __future__ import annotations

import threading

from agentkit.supervise import Service, run_all


def test_run_all_runs_services_and_stops():
    stop = threading.Event()
    ran: list[str] = []

    def first() -> None:
        ran.append("first")

    def second() -> None:
        ran.append("second")
        stop.set()

    run_all([Service("first", first), Service("second", second)], stop_event=stop)
    assert set(ran) == {"first", "second"}


def test_run_all_survives_a_crashing_service():
    stop = threading.Event()
    ran: list[str] = []

    def bad() -> None:
        raise RuntimeError("boom")

    def good() -> None:
        ran.append("good")
        stop.set()

    run_all([Service("bad", bad), Service("good", good)], stop_event=stop)
    assert ran == ["good"]
