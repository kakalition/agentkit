from __future__ import annotations

import json
from types import SimpleNamespace

from agentkit.deps import Deps
from agentkit.foundation.agent import Agent


def _fn(agent, name):
    return agent._function_toolset.tools[name].function


def _ctx(deps: Deps) -> SimpleNamespace:
    return SimpleNamespace(deps=deps)


def _agent():
    return Agent.make("u").instructions("x").usage().output(str).build()


async def test_usage_summary_and_audit(repos, deps: Deps):
    await repos.usage.add(requests=2, input_tokens=10, output_tokens=5, total_tokens=15)
    await repos.audit.append("thing.done", target="t", actor="owner")
    agent = _agent()
    ctx = _ctx(deps)

    totals = json.loads(await _fn(agent, "usage_summary")(ctx, "all"))
    assert totals["requests"] == 2
    assert json.loads(await _fn(agent, "usage_summary")(ctx, "24h"))["requests"] == 2

    trail = json.loads(await _fn(agent, "audit_trail")(ctx, 10))
    assert trail[0]["action"] == "thing.done"
    assert await _fn(agent, "verify_audit")(ctx) == "audit log intact"


async def test_usage_empty(repos, deps: Deps):
    agent = _agent()
    assert await _fn(agent, "audit_trail")(_ctx(deps)) == "(empty audit log)"
