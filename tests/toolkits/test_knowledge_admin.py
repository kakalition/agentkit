from __future__ import annotations

import json
from types import SimpleNamespace

from agentkit.deps import Deps
from agentkit.foundation.agent import Agent
from agentkit.knowledge import chunk_text


def _fn(agent, name):
    return agent._function_toolset.tools[name].function


def _ctx(deps: Deps) -> SimpleNamespace:
    return SimpleNamespace(deps=deps)


def _agent():
    return Agent.make("kb").instructions("x").knowledge_admin().output(str).build()


def test_knowledge_admin_approval_flags():
    agent = _agent()
    assert agent._function_toolset.tools["replace_document"].requires_approval is True
    assert agent._function_toolset.tools["forget_document"].requires_approval is True
    assert agent._function_toolset.tools["index_document"].requires_approval is False
    assert agent._function_toolset.tools["list_documents"].requires_approval is False


async def test_knowledge_admin_lifecycle(repos, deps: Deps):
    agent = _agent()
    ctx = _ctx(deps)

    assert await _fn(agent, "list_documents")(ctx) == "(no indexed documents)"

    long_text = " ".join(f"sentence {index} about cats." for index in range(200))
    assert "indexed" in await _fn(agent, "index_document")(ctx, long_text, "cats")
    expected = len(chunk_text(long_text))
    listed = json.loads(await _fn(agent, "list_documents")(ctx))
    assert listed == [{"source": "cats", "chunks": expected}]

    replaced = await _fn(agent, "replace_document")(ctx, "cats", "a short replacement")
    assert "replaced" in replaced
    listed = json.loads(await _fn(agent, "list_documents")(ctx))
    assert listed == [{"source": "cats", "chunks": 1}]

    removed = await _fn(agent, "forget_document")(ctx, "cats")
    assert "removed" in removed
    assert await _fn(agent, "list_documents")(ctx) == "(no indexed documents)"
    assert await repos.knowledge.sources() == []


async def test_knowledge_admin_rejects_empty(deps: Deps):
    agent = _agent()
    assert (await _fn(agent, "index_document")(_ctx(deps), "   ", "blank")).startswith("ERROR")
