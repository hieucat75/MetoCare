"""RAG retrieval (P2 #2).

Curated Vietnamese medical knowledge base + deterministic mock embeddings +
in-memory cosine vector store + retrieval pipeline. Skeleton adapters
(OpenAIEmbedding / PgVectorStore / QdrantStore) never call out. Retrieved context
is vetted for prompt-injection before it can reach an LLM system prompt.
"""

from __future__ import annotations

from .embedding import EmbeddingProvider, MockEmbedding, get_embedding_provider
from .errors import RAGConfigError
from .knowledge_base import KnowledgeBase, build_default_kb, chunk_markdown
from .retrieval import RetrievedChunk, Retriever, get_retriever, reset_retriever
from .vector_store import Document, InMemoryVectorStore, ScoredDocument, make_vector_store

__all__ = [
    "EmbeddingProvider",
    "MockEmbedding",
    "get_embedding_provider",
    "RAGConfigError",
    "KnowledgeBase",
    "build_default_kb",
    "chunk_markdown",
    "RetrievedChunk",
    "Retriever",
    "get_retriever",
    "reset_retriever",
    "Document",
    "InMemoryVectorStore",
    "ScoredDocument",
    "make_vector_store",
]
