"""Embedding providers for RAG.

`MockEmbedding` is a deterministic, hash-based bag-of-words embedding — no model,
no network, fully reproducible — so retrieval ranking is testable. Texts that
share words land closer in cosine space, which is enough to exercise the
pipeline. `OpenAIEmbedding` is a config-gated skeleton that never calls out.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

from app.core.config import get_settings

from .errors import RAGConfigError

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _WORD_RE.findall(text or "")]


class EmbeddingProvider(ABC):
    name: str = "base"
    dim: int = 256

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        ...

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class MockEmbedding(EmbeddingProvider):
    name = "mock"

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _bucket(self, token: str) -> int:
        h = hashlib.sha1(token.encode("utf-8")).digest()
        return int.from_bytes(h[:4], "big") % self.dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _tokens(text):
            vec[self._bucket(tok)] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


class OpenAIEmbedding(EmbeddingProvider):
    name = "openai"

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim
        self._api_key = get_settings().llm_api_key

    def embed(self, text: str) -> list[float]:
        raise RAGConfigError(
            "OpenAIEmbedding is a skeleton and makes no real call. "
            "Set MCP_EMBEDDING_PROVIDER=mock for dev/test."
        )


def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    name = settings.embedding_provider
    if name == "mock":
        return MockEmbedding(dim=settings.embedding_dim)
    if name == "openai":
        return OpenAIEmbedding()
    raise RAGConfigError(f"Unknown MCP_EMBEDDING_PROVIDER: {name!r}")
