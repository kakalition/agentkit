"""Speech: transcribe audio and synthesize speech (OpenAI audio models).

    from agentkit.audio import synthesize, transcribe

    text = transcribe("note.m4a")                    # speech -> text
    data = synthesize("Reminder: call mom.")         # text -> mp3 bytes
    Path("nudge.mp3").write_bytes(data)

Uses the ``openai`` client already required by the model layer. Pass ``client``
for a custom/async-compatible client, or ``api_key``. Realtime (streaming voice)
sessions are not provided here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentkit.errors import ConfigurationError

__all__ = ["DEFAULT_STT_MODEL", "DEFAULT_TTS_MODEL", "synthesize", "transcribe"]

DEFAULT_STT_MODEL = "whisper-1"
DEFAULT_TTS_MODEL = "tts-1"


def _client(client: Any = None, api_key: str | None = None) -> Any:
    if client is not None:
        return client
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - openai is a core dependency
        raise ConfigurationError("the 'openai' package is required for audio") from exc
    try:
        return OpenAI(api_key=api_key) if api_key else OpenAI()
    except Exception as exc:
        raise ConfigurationError(
            "no OpenAI credentials for audio (set OPENAI_API_KEY or pass api_key/client)"
        ) from exc


def transcribe(
    source: str | Path | bytes,
    *,
    model: str | None = None,
    language: str | None = None,
    prompt: str | None = None,
    client: Any = None,
    api_key: str | None = None,
    filename: str = "audio.wav",
) -> str:
    """Transcribe an audio file or raw bytes to text."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        file: Any = path.open("rb")
        filename = path.name
    else:
        file = source
    try:
        response = _client(client, api_key).audio.transcriptions.create(
            model=model or DEFAULT_STT_MODEL,
            file=(filename, file) if isinstance(source, bytes) else file,
            language=language,
            prompt=prompt,
        )
    finally:
        if isinstance(source, (str, Path)):
            file.close()
    return getattr(response, "text", str(response))


def synthesize(
    text: str,
    *,
    model: str | None = None,
    voice: str = "alloy",
    response_format: str = "mp3",
    client: Any = None,
    api_key: str | None = None,
) -> bytes:
    """Synthesize ``text`` to audio bytes (mp3 by default)."""
    response = _client(client, api_key).audio.speech.create(
        model=model or DEFAULT_TTS_MODEL,
        voice=voice,
        input=text,
        response_format=response_format,
    )
    content = getattr(response, "content", None)
    if content is None and hasattr(response, "read"):
        content = response.read()
    if content is None:  # pragma: no cover - defensive
        raise ConfigurationError("speech synthesis returned no audio")
    return bytes(content)
