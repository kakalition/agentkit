from __future__ import annotations

from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agentkit import App, KnowledgeBase, chunk_text
from agentkit.foundation.agent import Agent
from agentkit.runtime import Runtime


def _app(runtime: Runtime) -> App:
    app = App(name="kb", settings=runtime.settings, discover=False)
    app._runtime = runtime
    app.boot()
    return app


def test_chunk_text_splits_with_overlap():
    text = "\n\n".join(f"Paragraph {i} " + ("x" * 200) for i in range(6))
    chunks = chunk_text(text, chunk_chars=400, overlap=50)
    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)
    assert chunk_text("short", chunk_chars=400) == ["short"]


async def test_knowledge_crud(runtime: Runtime):
    app = _app(runtime)
    kb = KnowledgeBase(app)
    added = await kb.add("The capital of France is Paris. " * 60, source="geo.txt")
    assert added >= 1
    assert await kb.sources() == ["geo.txt"]
    assert await kb.count("geo.txt") == added

    hits = await kb.search("Paris", limit=3)
    assert hits and "Paris" in hits[0].content
    assert "geo.txt" in await kb.index()
    assert "geo.txt" in kb.format_hits(hits)

    assert await kb.clear("geo.txt") == added
    assert await kb.count() == 0


async def test_knowledge_add_many_and_directory(runtime: Runtime, tmp_path):
    app = _app(runtime)
    kb = KnowledgeBase(app)
    total = await kb.add_many({"a.md": "alpha " * 50, "b.md": "beta " * 50})
    assert total >= 2
    assert set(await kb.sources()) == {"a.md", "b.md"}

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "c.md").write_text("gamma " * 40, encoding="utf-8")
    assert await kb.add_directory(docs) >= 1
    sources = await kb.sources()
    assert "c.md" in sources or any("c.md" in s for s in sources)


async def test_builder_knowledge_tool(runtime: Runtime):
    app = _app(runtime)
    kb = KnowledgeBase(app)
    await kb.add("Mochi is a grey cat that lives in Lisbon.", source="pets.md")

    def _tool_return(messages: list[ModelMessage]) -> str | None:
        for message in messages:
            for part in getattr(message, "parts", []):
                if isinstance(part, ToolReturnPart):
                    return str(part.content)
        return None

    def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        returned = _tool_return(messages)
        if returned is not None:
            return ModelResponse(parts=[TextPart(returned)])
        return ModelResponse(parts=[ToolCallPart("search_knowledge", {"query": "Mochi"})])

    agent = Agent.make("kb").instructions("x").knowledge(kb).output(str).build()
    assert "search_knowledge" in set(agent._function_toolset.tools.keys())

    result = await agent.run("where is the cat", model=FunctionModel(model_fn))
    assert "Mochi" in result.output
