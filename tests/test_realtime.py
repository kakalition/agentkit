from __future__ import annotations

from agentkit.config import AgentSettings
from agentkit.contracts import RealtimeSession
from agentkit.foundation import App
from agentkit.realtime import LoopbackRealtime


def _app(tmp_path) -> App:
    return App(settings=AgentSettings(agent_home=tmp_path), discover=False)


def test_manager_resolves_loopback(tmp_path):
    assert isinstance(_app(tmp_path).manager("realtime").driver(), LoopbackRealtime)


async def test_loopback_round_trips_events():
    session = LoopbackRealtime(model="loop")
    assert isinstance(session, RealtimeSession)
    await session.connect()
    await session.send_text("hello")
    events = []
    async for event in session.stream_events():
        events.append(event)
        if len(events) == 3:
            break
    assert events[0]["type"] == "connected"
    assert events[1]["type"] == "text"
    assert events[2]["type"] == "transcript"


async def test_loopback_interrupt_and_close():
    session = LoopbackRealtime()
    await session.connect()
    await session.interrupt()
    await session.close()
    assert session.interruptions == 1
    assert session.closed is True
