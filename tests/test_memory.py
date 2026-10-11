from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agentkit.db.repositories import MemoryRepo, Repositories
from agentkit.deps import Deps
from agentkit.memory import attach_memory, memory_digest


def test_memory_repo_crud(repos: Repositories):
    first = repos.memories.add("My name is Ada", kind="person")
    repos.memories.add("Prefers metric units", kind="preference")
    assert isinstance(repos.memories, MemoryRepo)

    assert len(repos.memories.list()) == 2
    assert repos.memories.get(first.id) is not None
    assert first.embedding is not None
    # Semantic ranking puts the lexically-closest memory first.
    assert repos.memories.search("ada")[0].content == "My name is Ada"

    assert repos.memories.update(first.id, "My name is Ada Lovelace") is True
    assert repos.memories.search("lovelace")[0].content == "My name is Ada Lovelace"

    assert repos.memories.forget(first.id) is True
    assert repos.memories.forget(first.id) is False
    assert repos.memories.clear() == 1
    assert repos.memories.list() == []


def test_memory_search_keyword_fallback(repos: Repositories):
    repo = MemoryRepo(repos.session, "owner", embedder=None)
    repo.add("My name is Ada")
    repo.add("Prefers metric units")
    assert repo.search("ada")[0].content == "My name is Ada"
    assert repo.search("nomatch") == []


def test_memory_search_uses_embeddings(repos: Repositories):
    """A stub embedder proves ranking is by vector similarity, not keywords."""

    class StubEmbedder:
        def __init__(self) -> None:
            self.vectors = {
                "The user keeps a cat named Mochi": [1.0, 0.0, 0.0],
                "The user commutes by train": [0.0, 1.0, 0.0],
                "kitten": [0.9, 0.1, 0.0],
                "train": [0.0, 1.0, 0.0],
            }

        def embed(self, texts: list[str]) -> list[list[float]]:
            return [self.vectors[text] for text in texts]

    repo = MemoryRepo(repos.session, "owner", embedder=StubEmbedder())
    repo.add("The user keeps a cat named Mochi")
    repo.add("The user commutes by train")
    # "kitten" appears in neither memory as a keyword, yet ranks the cat first.
    hits = repo.search("kitten")
    assert hits[0].content == "The user keeps a cat named Mochi"


def test_memory_digest(repos: Repositories):
    assert memory_digest(repos) is None
    repos.memories.add("My name is Ada")
    digest = memory_digest(repos)
    assert digest is not None and "My name is Ada" in digest


def _has_tool_return(messages: list[ModelMessage]) -> bool:
    return any(
        isinstance(part, ToolReturnPart)
        for message in messages
        for part in getattr(message, "parts", [])
    )


def test_attach_memory_registers_tools_and_is_idempotent():
    agent: Agent[Deps, str] = Agent(name="m", deps_type=Deps, output_type=str, instructions="x")
    attach_memory(agent)
    attach_memory(agent)
    tools = set(agent._function_toolset.tools.keys())
    assert {"remember", "recall", "forget_memory"} <= tools


async def test_agent_remembers_via_tool(deps: Deps):
    agent: Agent[Deps, str] = Agent(name="m", deps_type=Deps, output_type=str, instructions="x")
    attach_memory(agent)

    def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if _has_tool_return(messages):
            return ModelResponse(parts=[TextPart("noted")])
        return ModelResponse(parts=[ToolCallPart("remember", {"fact": "My name is Ada"})])

    deps.model = FunctionModel(model_fn)
    result = await agent.run("my name is Ada", deps=deps, model=deps.model)
    assert result.output == "noted"
    saved = deps.repos.memories.list()
    assert [m.content for m in saved] == ["My name is Ada"]
