"""Vector stores for RAG.

`InMemoryVectorStore` does exact cosine similarity over a small curated corpus —
no dependency (no faiss). `PgVectorStore` / `QdrantStore` are config-gated
skeletons so the interface and selection are fixed without pulling heavy infra.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.core.config import get_settings

from .errors import RAGConfigError


@dataclass(frozen=True)
class Document:
    id: str
    text: str
    source: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoredDocument:
    document: Document
    score: float


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class VectorStore(ABC):
    name: str = "base"

    @abstractmethod
    def add(self, doc: Document, vector: list[float]) -> None:
        ...

    @abstractmethod
    def query(self, vector: list[float], *, top_k: int) -> list[ScoredDocument]:
        ...

    @abstractmethod
    def clear(self) -> None:
        ...

    @abstractmethod
    def __len__(self) -> int:
        ...


class InMemoryVectorStore(VectorStore):
    name = "memory"

    def __init__(self) -> None:
        self._items: list[tuple[Document, list[float]]] = []

    def add(self, doc: Document, vector: list[float]) -> None:
        self._items.append((doc, vector))

    def query(self, vector: list[float], *, top_k: int) -> list[ScoredDocument]:
        scored = [ScoredDocument(doc, cosine(vector, vec)) for doc, vec in self._items]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[: max(0, top_k)]

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


class PgVectorStore(VectorStore):
    name = "pgvector"

    def __init__(self) -> None:
        raise RAGConfigError(
            "PgVectorStore is a skeleton (needs pgvector). "
            "Set MCP_VECTOR_STORE=memory for dev/test."
        )

    def add(self, doc: Document, vector: list[float]) -> None:  # pragma: no cover
        raise RAGConfigError("PgVectorStore not implemented.")

    def query(self, vector: list[float], *, top_k: int) -> list[ScoredDocument]:  # pragma: no cover
        raise RAGConfigError("PgVectorStore not implemented.")

    def clear(self) -> None:  # pragma: no cover
        raise RAGConfigError("PgVectorStore not implemented.")

    def __len__(self) -> int:  # pragma: no cover
        return 0


class QdrantStore(VectorStore):
    name = "qdrant"

    def __init__(self) -> None:
        raise RAGConfigError(
            "QdrantStore is a skeleton (needs qdrant-client). "
            "Set MCP_VECTOR_STORE=memory for dev/test."
        )

    def add(self, doc: Document, vector: list[float]) -> None:  # pragma: no cover
        raise RAGConfigError("QdrantStore not implemented.")

    def query(self, vector: list[float], *, top_k: int) -> list[ScoredDocument]:  # pragma: no cover
        raise RAGConfigError("QdrantStore not implemented.")

    def clear(self) -> None:  # pragma: no cover
        raise RAGConfigError("QdrantStore not implemented.")

    def __len__(self) -> int:  # pragma: no cover
        return 0


def make_vector_store() -> VectorStore:
    name = get_settings().vector_store
    if name == "memory":
        return InMemoryVectorStore()
    if name == "pgvector":
        return PgVectorStore()
    if name == "qdrant":
        return QdrantStore()
    raise RAGConfigError(f"Unknown MCP_VECTOR_STORE: {name!r}")
