"""Multimodal input helpers.

Build content parts from files, bytes or URLs and hand them to the agent::

    from agentkit import App
    from agentkit.multimodal import content, image, text

    await app.run(content(text("What is in this photo?"), image("cat.png")))

``App.run`` / ``ChatRunner.send`` accept either a plain string or a sequence of
these parts. Generated images returned by the model are captured into
``deps.artifacts`` automatically (see :func:`collect_artifacts`).
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from pydantic_ai.messages import BinaryContent, ImageUrl, UserContent

__all__ = ["audio", "collect_artifacts", "content", "document", "image", "text"]


def _media_type(path: Path, fallback: str) -> str:
    guess, _ = mimetypes.guess_type(path.name)
    return guess or fallback


def text(value: str) -> str:
    """A text part (a plain string is already a valid content part)."""
    return value


def image(source: str | Path | bytes, *, media_type: str | None = None) -> UserContent:
    """An image part from a path, raw bytes, or a URL."""
    if isinstance(source, (str, Path)):
        value = str(source)
        if value.startswith(("http://", "https://")):
            return ImageUrl(value, media_type=media_type)
        path = Path(value)
        return BinaryContent(path.read_bytes(), media_type=media_type or _media_type(path, "image/png"))
    return BinaryContent(source, media_type=media_type or "image/png")


def audio(source: str | Path | bytes, *, media_type: str | None = None) -> UserContent:
    """An audio part from a path or raw bytes."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        return BinaryContent(
            path.read_bytes(), media_type=media_type or _media_type(path, "audio/wav")
        )
    return BinaryContent(source, media_type=media_type or "audio/wav")


def document(source: str | Path | bytes, *, media_type: str | None = None) -> UserContent:
    """A document part (e.g. a PDF) from a path or raw bytes."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        return BinaryContent(
            path.read_bytes(), media_type=media_type or _media_type(path, "application/pdf")
        )
    return BinaryContent(source, media_type=media_type or "application/pdf")


def content(*parts: UserContent) -> list[UserContent]:
    """Compose a multi-part user message."""
    return list(parts)


def collect_artifacts(messages: list[Any]) -> list[dict[str, Any]]:
    """Scan messages for generated binary media and describe them as artifacts."""
    artifacts: list[dict[str, Any]] = []
    for message in messages:
        for part in getattr(message, "parts", []):
            data = getattr(part, "data", None)
            media_type = getattr(part, "media_type", None)
            if isinstance(data, (bytes, bytearray)) and media_type:
                kind = str(media_type).split("/", 1)[0]
                if kind in {"image", "audio", "video"}:
                    artifacts.append(
                        {
                            "kind": kind,
                            "media_type": media_type,
                            "bytes": len(data),
                            "identifier": getattr(part, "identifier", None),
                        }
                    )
    return artifacts
