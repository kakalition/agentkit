from __future__ import annotations

from conformance import computer_conformance, run_recorder_conformance

from agentkit.computer import LoopbackComputer
from agentkit.runs import CompositeRecorder, InMemoryRecorder


async def test_loopback_computer_conforms():
    await computer_conformance(LoopbackComputer())


def test_recorders_conform():
    run_recorder_conformance(InMemoryRecorder("run-1"))
    run_recorder_conformance(CompositeRecorder(InMemoryRecorder("run-1"), run_id="run-1"))
