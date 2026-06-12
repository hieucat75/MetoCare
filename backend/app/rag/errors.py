"""RAG error types."""

from __future__ import annotations


class RAGError(Exception):
    """Base class for RAG errors."""


class RAGConfigError(RAGError):
    """A RAG component is selected but cannot run (skeleton provider / store)."""
