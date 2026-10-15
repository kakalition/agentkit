from __future__ import annotations

from fastapi.testclient import TestClient

from agentkit.config import AgentSettings
from agentkit.ratelimit import build_limiter
from agentkit.runtime import build_runtime
from agentkit.webui.app import build_webui_app
from agentkit.webui.introspect import stack_view


def _runtime(tmp_path, **over):
    settings = AgentSettings(
        owner_id="owner", agent_home=tmp_path, memory_embedding_backend="hash", **over
    )
    return settings, build_runtime(settings)


async def test_limiter_allows_then_denies(tmp_path):
    settings, runtime = _runtime(tmp_path, rate_limit_enabled=True, rate_limit_per_minute=2)
    limiter = build_limiter(settings, runtime)
    assert limiter is not None
    first = await limiter.hit("http:GET")
    second = await limiter.hit("http:GET")
    third = await limiter.hit("http:GET")
    assert first.allowed and second.allowed
    assert third.allowed is False
    assert third.remaining == 0
    assert third.retry_after > 0
    # the in-process cache short-circuits a fourth call too
    assert (await limiter.hit("http:GET")).allowed is False


async def test_limiter_burst_and_reset(tmp_path):
    settings, runtime = _runtime(
        tmp_path, rate_limit_enabled=True, rate_limit_per_minute=1, rate_limit_burst=1
    )
    limiter = build_limiter(settings, runtime)
    assert limiter is not None
    assert (await limiter.hit("k")).allowed is True
    assert (await limiter.hit("k")).allowed is True  # limit + burst
    assert (await limiter.hit("k")).allowed is False
    await limiter.reset("k")


def test_build_limiter_disabled(tmp_path):
    settings, runtime = _runtime(tmp_path)
    assert build_limiter(settings, runtime) is None
    assert stack_view(settings)["rate_limit"]["enabled"] is False


def test_webui_returns_429_with_retry_after(tmp_path):
    settings, runtime = _runtime(
        tmp_path, rate_limit_enabled=True, rate_limit_per_minute=2
    )
    client = TestClient(build_webui_app(runtime=runtime, settings=settings))
    assert client.get("/api/whoami").status_code == 200
    assert client.get("/api/whoami").status_code == 200
    blocked = client.get("/api/whoami")
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"].isdigit()
    # health is public and never counted
    assert client.get("/api/health").status_code == 200
