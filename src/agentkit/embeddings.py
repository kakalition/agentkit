"""CPU-only text embeddings for semantic memory recall.

A thin, pluggable embedder interface with three backends:

* ``sentence-transformers`` (default) — loads any HF sentence-transformer on CPU,
  default ``sentence-transformers/all-MiniLM-L6-v2`` (~90MB). Lazy: the model is
  only built on the first ``embed`` call.
* ``fastembed`` — lighter ONNX models (e.g. ``BAAI/bge-small-en-v1.5``), no Torch.
* ``hash`` — deterministic offline bag-of-words hashing, used by tests and as a
  no-download fallback.

Instruction-aware models (Qwen3, e5, bge) can be given a query/document prefix
via ``memory_embedding_query_prompt`` / ``memory_embedding_document_prompt``.

Vectors are stored as base64 float32 text (libSQL has no BLOB bind) and ranked
by cosine similarity, so no vector database is required.
"""

from __future__ import annotations

import base64
import hashlib
import math
from array import array
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

DEFAULT_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EMBED_BACKEND = "sentence-transformers"
DEFAULT_EMBED_DEVICE = "cpu"
HASH_DIM = 256


@runtime_checkable
class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for char in text.lower():
        if char.isalnum():
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


class HashingEmbedder:
    """Deterministic bag-of-words hashing embedder — offline, no model download."""

    def __init__(self, dim: int = HASH_DIM) -> None:
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in _tokens(text):
            digest = hashlib.md5(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[index] += sign
        norm = math.sqrt(sum(value * value for value in vec))
        return [value / norm for value in vec] if norm else vec

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]


class SentenceTransformerEmbedder:
    """Any HF sentence-transformer on CPU. Lazy-loading.

    ``query_prompt`` / ``document_prompt`` are prepended before encoding, which
    instruction-aware models (Qwen3, e5, bge) expect; leave empty for MiniLM.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_EMBED_MODEL,
        device: str = DEFAULT_EMBED_DEVICE,
        *,
        query_prompt: str = "",
        document_prompt: str = "",
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.query_prompt = query_prompt
        self.document_prompt = document_prompt
        self._model: Any = None

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name, device=self.device)
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        return [list(map(float, vector)) for vector in vectors]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not self.document_prompt:
            return self._encode(texts)
        return self._encode([f"{self.document_prompt}{text}" for text in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._encode([f"{self.query_prompt}{text}"])[0]


class FastEmbedEmbedder:
    """fastembed ONNX models (CPU, no Torch). Lazy-loading."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: Any = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name)
        return [list(map(float, vector)) for vector in self._model.embed(list(texts))]


def build_embedder(settings: Any = None) -> Embedder | None:
    """Build the configured embedder, or ``None`` to disable semantic recall.

    The returned embedder is lazy, so constructing it never imports Torch or
    downloads a model — that only happens on the first ``embed`` call.
    """
    backend = (
        str(getattr(settings, "memory_embedding_backend", DEFAULT_EMBED_BACKEND) or "none")
        .strip()
        .lower()
    )
    model = getattr(settings, "memory_embedding_model", DEFAULT_EMBED_MODEL) or DEFAULT_EMBED_MODEL
    device = (
        getattr(settings, "memory_embedding_device", DEFAULT_EMBED_DEVICE) or DEFAULT_EMBED_DEVICE
    )
    query_prompt = getattr(settings, "memory_embedding_query_prompt", "") or ""
    document_prompt = getattr(settings, "memory_embedding_document_prompt", "") or ""

    if backend in {"none", "off", "keyword", ""}:
        return None
    if backend == "hash":
        return HashingEmbedder()
    if backend in {"sentence-transformers", "sentence_transformers", "st", "torch"}:
        return SentenceTransformerEmbedder(
            model, device, query_prompt=query_prompt, document_prompt=document_prompt
        )
    if backend == "fastembed":
        return FastEmbedEmbedder(model)
    return None


def embed_documents(embedder: Embedder, texts: list[str]) -> list[list[float]]:
    """Embed stored documents, using ``embed_documents`` when the backend has it."""
    method = getattr(embedder, "embed_documents", None)
    return method(texts) if method is not None else embedder.embed(texts)


def embed_query(embedder: Embedder, text: str) -> list[float]:
    """Embed a search query, using ``embed_query`` when the backend has it."""
    method = getattr(embedder, "embed_query", None)
    if method is not None:
        return method(text)
    return embedder.embed([text])[0]


_default_embedder: Embedder | None = None


def configure(embedder: Embedder | None) -> None:
    """Set the process-wide default embedder used by :class:`MemoryRepo`."""
    global _default_embedder
    _default_embedder = embedder


def get_default_embedder() -> Embedder | None:
    return _default_embedder


def pack_vector(vector: Sequence[float]) -> str:
    return base64.b64encode(array("f", (float(value) for value in vector)).tobytes()).decode(
        "ascii"
    )


def unpack_vector(blob: str) -> list[float]:
    values = array("f")
    values.frombytes(base64.b64decode(blob))
    return list(values)


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


__all__ = [
    "DEFAULT_EMBED_BACKEND",
    "DEFAULT_EMBED_DEVICE",
    "DEFAULT_EMBED_MODEL",
    "Embedder",
    "FastEmbedEmbedder",
    "HashingEmbedder",
    "SentenceTransformerEmbedder",
    "build_embedder",
    "configure",
    "cosine_similarity",
    "embed_documents",
    "embed_query",
    "get_default_embedder",
    "pack_vector",
    "unpack_vector",
]
