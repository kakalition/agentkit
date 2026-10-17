from __future__ import annotations

from fastapi.testclient import TestClient

from agentkit.config import AgentSettings
from agentkit.runtime import build_runtime, repositories
from agentkit.session import ChatResult
from agentkit.webui.app import build_webui_app


async def _stub_answer(conversation_id: str, text: str, *, actor=None) -> ChatResult:
    return ChatResult(
        output=f"echo:{text}",
        artifacts=[],
        history_length=2,
        usage={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
    )


def _client(tmp_path, **over):
    settings = AgentSettings(
        owner_id="owner", agent_home=tmp_path, memory_embedding_backend="hash", **over
    )
    runtime = build_runtime(settings)
    app = build_webui_app(runtime=runtime, settings=settings, answer=_stub_answer)
    return TestClient(app), runtime


def test_openai_api_disabled_by_default(tmp_path):
    client, _ = _client(tmp_path)
    assert client.get("/v1/models").status_code == 404
    assert client.post("/v1/chat/completions", json={"messages": []}).status_code == 404


def test_openai_models_and_completion(tmp_path):
    client, runtime = _client(tmp_path, openai_api_enabled=True)

    models = client.get("/v1/models").json()
    assert models["object"] == "list"
    assert models["data"][0]["id"] == runtime.settings.model_name

    response = client.post(
        "/v1/chat/completions",
        json={"model": "x", "messages": [{"role": "user", "content": "hi"}]},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "echo:hi"
    assert body["usage"]["total_tokens"] == 5


def test_openai_streaming_sse(tmp_path):
    client, _ = _client(tmp_path, openai_api_enabled=True)
    response = client.post(
        "/v1/chat/completions",
        json={"stream": True, "messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "data: [DONE]" in response.text
    assert "chat.completion.chunk" in response.text


def test_openai_records_usage(tmp_path):
    client, runtime = _client(tmp_path, openai_api_enabled=True)
    client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]})

    import asyncio

    async def _totals():
        async with repositories(runtime) as repos:
            return await repos.usage.totals()

    totals = asyncio.run(_totals())
    assert totals["requests"] == 1
    assert totals["total_tokens"] == 5


def test_openai_true_token_streaming(tmp_path):
    import asyncio
    from types import SimpleNamespace

    from agentkit.security import system_actor
    from agentkit.session import ChatResult, StreamEvent
    from agentkit.webui.openai_api import ChatCompletionRequest, chat_completions

    settings = AgentSettings(
        owner_id="owner",
        agent_home=tmp_path,
        memory_embedding_backend="hash",
        openai_api_enabled=True,
    )
    runtime = build_runtime(settings)
    actor = system_actor(settings)

    class FakeApp:
        def stream(self, conversation_id, prompt, *, actor=None):  # noqa: ANN001
            async def gen():  # noqa: ANN202
                yield StreamEvent("text", text="Hel")
                yield StreamEvent("text", text="lo")
                yield StreamEvent(
                    "final",
                    result=ChatResult(
                        output="Hello",
                        usage={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
                    ),
                )

            return gen()

    ctx = SimpleNamespace(settings=settings, runtime=runtime, answer=None, app=FakeApp())
    body = ChatCompletionRequest(stream=True, messages=[{"role": "user", "content": "hi"}])
    response = asyncio.run(chat_completions(body, None, ctx, actor))

    async def _collect() -> str:
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        return "".join(chunks)

    text = asyncio.run(_collect())
    assert '"content": "Hel"' in text
    assert '"content": "lo"' in text
    assert "data: [DONE]" in text
