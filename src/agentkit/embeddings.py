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
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

import numpy as np

from agentkit.support import drivers
from agentkit.support.kinds import DriverKind, EmbeddingsDriver
from agentkit.support.manager import Manager

DEFAULT_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EMBED_BACKEND: EmbeddingsDriver = EmbeddingsDriver.SENTENCE_TRANSFORMERS
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


class _BackendShim:
    """Fallback settings proxy that overrides only the embedding backend."""

    def __init__(self, settings: Any, backend: str) -> None:
        self._settings = settings
        self.memory_embedding_backend = backend

    def __getattr__(self, name: str) -> Any:
        return getattr(self._settings, name)


def _override_backend(settings: Any, backend: str) -> Any:
    copy = getattr(settings, "model_copy", None)
    if callable(copy):
        try:
            return copy(update={"memory_embedding_backend": backend})
        except Exception:  # pragma: no cover - non-pydantic settings
            pass
    return _BackendShim(settings, backend)


def build_embedder_for_backend(app: Any, backend: str | EmbeddingsDriver) -> Embedder | None:
    """Build the embedder for a named ``backend`` using the app's settings."""
    settings = getattr(app, "settings", None)
    if settings is None:
        from agentkit.config import get_settings

        settings = get_settings()
    try:
        resolved: EmbeddingsDriver | str = EmbeddingsDriver(backend)
    except ValueError:
        resolved = backend
    return build_embedder(_override_backend(settings, resolved))


class EmbedderManager(Manager):
    """Resolves the configured embedder (``memory_embedding_backend``).

    The backend setting doubles as the driver name, so existing configuration
    keeps working: ``sentence-transformers`` (default), ``fastembed``, ``hash``
    or ``none``. Register new embedders with
    ``app.extend("embeddings", "my-model", factory)``.
    """

    kind = DriverKind.EMBEDDINGS
    default_driver = DEFAULT_EMBED_BACKEND

    @property
    def setting_name(self) -> str:
        return "memory_embedding_backend"

    def create(self, name: str) -> Embedder | None:
        override = self._overrides.get(name)
        if override is not None:
            return override(self.app)
        factory = drivers.resolve(self.kind, name)
        if factory is not None:
            return factory(self.app)
        return build_embedder_for_backend(self.app, name)

    def available(self) -> list[str]:
        names = set(super().available())
        names.update(str(driver) for driver in EmbeddingsDriver)
        return sorted(names)


def pack_vector(vector: Sequence[float]) -> str:
    """Base64-encode a float32 vector (the storage format; libSQL has no BLOB bind)."""
    data = np.asarray(vector, dtype=np.float32).tobytes()
    return base64.b64encode(data).decode("ascii")


def unpack_vector(blob: str) -> list[float]:
    data = base64.b64decode(blob)
    return np.frombuffer(data, dtype=np.float32).tolist()


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        return 0.0
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    norm_a = float(np.linalg.norm(va))
    norm_b = float(np.linalg.norm(vb))
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))


def similarity_scores(
    query: Sequence[float], vectors: Sequence[Sequence[float]]
) -> list[float]:
    """Cosine similarity of ``query`` against many same-dimension vectors.

    Vectorized with numpy — the fast fallback used when the optional
    ``sqlite-vec`` extension is unavailable. All ``vectors`` must share the
    query's dimension; callers filter mismatches first.
    """
    if not vectors:
        return []
    q = np.asarray(query, dtype=np.float32)
    matrix = np.asarray(vectors, dtype=np.float32)
    query_norm = float(np.linalg.norm(q))
    if query_norm <= 0.0:
        return [0.0] * len(vectors)
    norms = np.linalg.norm(matrix, axis=1)
    denom = norms * query_norm
    dots = matrix @ q
    with np.errstate(divide="ignore", invalid="ignore"):
        scores = np.where(denom > 0.0, dots / denom, 0.0)
    return [float(score) for score in scores]


def sqlite_vec_available() -> bool:
    """Whether the optional ``sqlite-vec`` accelerator can be imported/loaded.

    When unavailable, semantic search falls back to the numpy-vectorized cosine
    scan in :func:`similarity_scores`.
    """
    try:  # pragma: no cover - depends on the optional extra
        import sqlite_vec  # noqa: F401
    except Exception:
        return False
    return True


__all__ = [
    "DEFAULT_EMBED_BACKEND",
    "DEFAULT_EMBED_DEVICE",
    "DEFAULT_EMBED_MODEL",
    "Embedder",
    "EmbedderManager",
    "FastEmbedEmbedder",
    "HashingEmbedder",
    "SentenceTransformerEmbedder",
    "build_embedder",
    "build_embedder_for_backend",
    "configure",
    "cosine_similarity",
    "embed_documents",
    "embed_query",
    "get_default_embedder",
    "pack_vector",
    "similarity_scores",
    "sqlite_vec_available",
    "unpack_vector",
]
