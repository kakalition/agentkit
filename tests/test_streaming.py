from __future__ import annotations

from pydantic_ai.models.function import FunctionModel

from agentkit import App, StreamEvent
from agentkit.foundation.agent import Agent
from agentkit.runtime import Runtime


def _stream_model(chunks: list[str]) -> FunctionModel:
    def stream_fn(messages, info):  # noqa: ANN001
        async def gen():
            for chunk in chunks:
                yield chunk

        return gen()

    def model_fn(messages, info):  # noqa: ANN001
        from pydantic_ai.messages import ModelResponse, TextPart

        return ModelResponse(parts=[TextPart("".join(chunks))])

    return FunctionModel(function=model_fn, stream_function=stream_fn)


def _app(runtime: Runtime, model) -> App:  # noqa: ANN001
    app = App(name="stream", settings=runtime.settings, discover=False, model=model)
    app._runtime = runtime
    app.agent(Agent.make("stream").instructions("x").output(str))
    app.boot()
    return app


async def test_app_stream_yields_text_and_final(runtime: Runtime):
    app = _app(runtime, _stream_model(["Hel", "lo ", "world"]))
    events = [event async for event in app.stream("hi")]
    assert all(isinstance(event, StreamEvent) for event in events)
    text = "".join(event.text for event in events if event.kind == "text")
    assert text == "Hello world"
    finals = [event for event in events if event.kind == "final"]
    assert finals and finals[-1].result is not None
    assert finals[-1].result.output == "Hello world"
    assert finals[-1].result.history_length >= 2


async def test_stream_persists_history(runtime: Runtime):
    app = _app(runtime, _stream_model(["ok"]))
    await app.run("first")
    async for _ in app.stream("second"):
        pass
    async with app.repositories() as repos:
        assert await repos.messages.list("cli:default")


async def test_send_and_stream_agree(runtime: Runtime):
    app = _app(runtime, _stream_model(["a", "b"]))
    via_stream = [e async for e in app.stream("x")]
    stream_text = "".join(e.text for e in via_stream if e.kind == "text")
    result = await app.run("y")
    assert stream_text == "ab"
    assert result.output == "ab"
