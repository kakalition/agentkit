"""The speech contracts — transcribe audio, synthesize speech."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

__all__ = ["Speech", "Synthesizer", "Transcriber"]


@runtime_checkable
class Transcriber(Protocol):
    """Speech to text."""

    def transcribe(self, source: str | Path | bytes, **options: Any) -> str: ...


@runtime_checkable
class Synthesizer(Protocol):
    """Text to audio bytes."""

    def synthesize(self, text: str, **options: Any) -> bytes: ...


@runtime_checkable
class Speech(Transcriber, Synthesizer, Protocol):
    """A speech driver that both transcribes and synthesizes."""
