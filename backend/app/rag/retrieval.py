"""Retrieval pipeline: query -> embed -> top-k -> rerank -> context window.

The reranker blends vector cosine similarity with lexical overlap so exact term
matches (e.g. a biomarker name) surface even when the embedding is coarse. The
assembled context is vetted once more for prompt-injection before it is returned
to the gateway, so a poisoned chunk can never reach the system prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import get_settings
from app.domain import guardrails

from .knowledge_base import KnowledgeBase, build_default_kb
from .vector_store import ScoredDocument

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _WORD_RE.findall(text or "")}


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    source: str
    score: float


class Retriever:
    def __init__(self, kb: KnowledgeBase) -> None:
        self._kb = kb

    def _rerank(self, query: str, candidates: list[ScoredDocument]) -> list[RetrievedChunk]:
        q_tokens = _tokens(query)
        reranked: list[RetrievedChunk] = []
        for cand in candidates:
            overlap = 0.0
            if q_tokens:
                doc_tokens = _tokens(cand.document.text)
                overlap = len(q_tokens & doc_tokens) / len(q_tokens)
            # Blend: vector similarity (primary) + lexical overlap (tie-breaker/boost).
            blended = 0.7 * cand.score + 0.3 * overlap
            reranked.append(
                RetrievedChunk(
                    text=cand.document.text,
                    source=cand.document.source,
                    score=blended,
                )
            )
        reranked.sort(key=lambda c: c.score, reverse=True)
        return reranked

    def retrieve(self, query: str, *, top_k: int | None = None) -> list[RetrievedChunk]:
        if not query or not query.strip() or len(self._kb) == 0:
            return []
        k = top_k if top_k is not None else get_settings().rag_top_k
        # Over-fetch a little so the reranker has room to reorder.
        candidates = self._kb.store.query(self._kb.embedder.embed(query), top_k=k * 2)
        ranked = self._rerank(query, candidates)
        # Drop zero-similarity noise; vet against injection one more time.
        safe = [c for c in ranked if c.score > 0 and not guardrails.is_injection(c.text)]
        return safe[:k]

    def build_context(self, query: str, *, top_k: int | None = None) -> str:
        """Return a context-window string to prepend to a system prompt (or '')."""
        chunks = self.retrieve(query, top_k=top_k)
        if not chunks:
            return ""
        lines = ["[NGỮ CẢNH THAM KHẢO ĐÃ DUYỆT — chỉ dùng để giải thích, không phải chẩn đoán]"]
        for c in chunks:
            lines.append(f"- ({c.source}) {c.text}")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Singleton (KB built once from seed). reset_retriever() for tests.
# --------------------------------------------------------------------------- #

_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever(build_default_kb())
    return _retriever


def reset_retriever() -> None:
    global _retriever
    _retriever = None
