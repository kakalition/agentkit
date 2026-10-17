"""Testing helpers (``agentkit.testing``): fakes and a ``TestCase`` base.

Re-exports :mod:`agentkit.foundation.testing` for a friendly import path::

    from agentkit.testing import TestCase, fake_queue, boot_test_app
"""

from __future__ import annotations

from agentkit.foundation.testing import (
    FakeCache,
    FakeNotifier,
    FakeQueue,
    FakeStorage,
    TestCase,
    assert_allows,
    assert_denies,
    boot_test_app,
    create,
    fake_cache,
    fake_events,
    fake_notifications,
    fake_queue,
    fake_storage,
    freeze_time,
    make,
    run_pending,
    travel,
    travel_back,
)

__all__ = [
    "FakeCache",
    "FakeNotifier",
    "FakeQueue",
    "FakeStorage",
    "TestCase",
    "assert_allows",
    "assert_denies",
    "boot_test_app",
    "create",
    "fake_cache",
    "fake_events",
    "fake_notifications",
    "fake_queue",
    "fake_storage",
    "freeze_time",
    "make",
    "run_pending",
    "travel",
    "travel_back",
]
