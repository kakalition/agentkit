from __future__ import annotations

import math

from agentkit.embeddings import (
    DEFAULT_EMBED_MODEL,
    HashingEmbedder,
    SentenceTransformerEmbedder,
    build_embedder,
    configure,
    cosine_similarity,
    embed_documents,
    embed_query,
    get_default_embedder,
    pack_vector,
    unpack_vector,
)


class _Settings:
    def __init__(
        self,
        backend: str = "hash",
        model: str = "BAAI/bge-m3",
        device: str = "cpu",
    ) -> None:
        self.memory_embedding_backend = backend
        self.memory_embedding_model = model
        self.memory_embedding_device = device


def test_hashing_embedder_is_deterministic_and_normalized():
    embedder = HashingEmbedder(dim=64)
    first = embedder.embed(["Hello, World!"])[0]
    second = embedder.embed(["hello world"])[0]
    assert first == second, "tokenization is case/punctuation insensitive"
    assert math.isclose(math.sqrt(sum(v * v for v in first)), 1.0, rel_tol=1e-6)


def test_pack_unpack_roundtrip():
    vector = [0.1, -0.25, 3.5, 0.0]
    restored = unpack_vector(pack_vector(vector))
    assert all(math.isclose(a, b, rel_tol=1e-6) for a, b in zip(restored, vector, strict=True))


def test_cosine_similarity():
    assert math.isclose(cosine_similarity([1, 0], [2, 0]), 1.0)
    assert cosine_similarity([1, 0], [0, 1]) == 0.0
    assert cosine_similarity([0, 0], [1, 0]) == 0.0
    assert cosine_similarity([1, 0, 0], [1, 0]) == 0.0  # dimension mismatch


def test_build_embedder_backends():
    assert build_embedder(_Settings(backend="none")) is None
    assert build_embedder(_Settings(backend="keyword")) is None
    assert build_embedder(_Settings(backend="unknown")) is None
    assert isinstance(build_embedder(_Settings(backend="hash")), HashingEmbedder)
    # The sentence-transformers backend is lazy: building it must not import torch.
    st = build_embedder(_Settings(backend="sentence-transformers"))
    assert isinstance(st, SentenceTransformerEmbedder)
    assert st.model_name == "BAAI/bge-m3" and st.device == "cpu"


def test_default_model_is_small_minilm():
    assert DEFAULT_EMBED_MODEL == "sentence-transformers/all-MiniLM-L6-v2"


class _DocQueryEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[9.0] for _ in texts]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [2.0]


class _BasicEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[3.0] for _ in texts]


def test_embed_helpers_prefer_specific_methods():
    embedder = _DocQueryEmbedder()
    assert embed_documents(embedder, ["a", "b"]) == [[1.0], [1.0]]
    assert embed_query(embedder, "a") == [2.0]


def test_embed_helpers_fallback_to_embed():
    embedder = _BasicEmbedder()
    assert embed_documents(embedder, ["a", "b"]) == [[3.0], [3.0]]
    assert embed_query(embedder, "a") == [3.0]


def test_configure_sets_default():
    configure(None)
    assert get_default_embedder() is None
    marker = HashingEmbedder()
    configure(marker)
    assert get_default_embedder() is marker
    configure(None)
