from __future__ import annotations

from types import SimpleNamespace

from pydantic_ai.messages import ModelResponse, TextPart

from agentkit.deps import Deps
from agentkit.foundation.agent import Agent
from agentkit.session import serialize_message


def _fn(agent, name):
    return agent._function_toolset.tools[name].function


def _ctx(deps: Deps) -> SimpleNamespace:
    return SimpleNamespace(deps=deps)


def _agent():
    return Agent.make("h").instructions("x").history().output(str).build()


async def test_history_reads(repos, deps: Deps):
    await repos.conversations.get_or_create("cli:one")
    await repos.messages.append("cli:one", [serialize_message(ModelResponse(parts=[TextPart("the sky is blue")]))])
    agent = _agent()
    ctx = _ctx(deps)

    assert "cli:one" in await _fn(agent, "list_conversations")(ctx)
    transcript = await _fn(agent, "read_conversation")(ctx, "cli:one")
    assert "the sky is blue" in transcript
    assert "sky" in await _fn(agent, "search_history")(ctx, "sky")
    assert await _fn(agent, "read_conversation")(ctx, "missing") == "(not found)"
    assert await _fn(agent, "search_history")(ctx, "") == "ERROR: empty query"


async def test_history_is_owner_scoped(repos, deps: Deps):
    from agentkit.db.models import Conversation

    repos.session.add(Conversation(id="cli:other", owner_id="other", channel="cli"))
    await repos.session.flush()
    agent = _agent()
    assert await _fn(agent, "read_conversation")(_ctx(deps), "cli:other") == "(not found)"
