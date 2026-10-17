from __future__ import annotations

from pydantic_ai.messages import BinaryContent, ImageUrl, ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from agentkit import App
from agentkit.audio import synthesize, transcribe
from agentkit.foundation.agent import Agent
from agentkit.multimodal import collect_artifacts, content, document, image, text
from agentkit.runtime import Runtime


def test_image_url_and_binary_parts(tmp_path):
    url_part = image("https://example.com/cat.png")
    assert isinstance(url_part, ImageUrl)

    file = tmp_path / "cat.png"
    file.write_bytes(b"\x89PNG")
    binary = image(file)
    assert isinstance(binary, BinaryContent)
    assert binary.media_type == "image/png"

    assert isinstance(document(b"pdf"), BinaryContent)
    parts = content(text("look"), image(b"img"))
    assert len(parts) == 2


def test_collect_artifacts_from_messages():
    message = ModelResponse(parts=[BinaryContent(b"img", media_type="image/png")])
    artifacts = collect_artifacts([message])
    assert artifacts and artifacts[0]["kind"] == "image"


async def test_app_run_accepts_multimodal_content(runtime: Runtime):
    app = App(name="mm", settings=runtime.settings, discover=False)
    app._runtime = runtime
    app._model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("seen")]))
    app.agent(Agent.make("mm").instructions("x").output(str))
    app.boot()

    result = await app.run(content(text("describe"), image(b"\x89PNG")))
    assert result.output == "seen"


def test_transcribe_and_synthesize_with_client():
    class _Response:
        def __init__(self, text=None, content=None):  # noqa: ANN001
            self.text = text
            self.content = content

    class _Transcriptions:
        @staticmethod
        def create(**kwargs):  # noqa: ANN003
            return _Response(text="hello")

    class _Speech:
        @staticmethod
        def create(**kwargs):  # noqa: ANN003
            return _Response(content=b"audio-bytes")

    class _Audio:
        transcriptions = _Transcriptions()
        speech = _Speech()

    class FakeClient:
        audio = _Audio()

    assert transcribe(b"data", client=FakeClient()) == "hello"
    assert synthesize("hi", client=FakeClient()) == b"audio-bytes"
