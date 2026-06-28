"""Clinical Knowledge Platform (CKP) v1.

Single authoritative medical knowledge source for MetoCare AI explanations.
"""
from .registry import KnowledgeRegistry, get_registry, reset_registry
from .schema import KnowledgeCard, KnowledgeSections

__all__ = [
    "KnowledgeRegistry",
    "KnowledgeCard",
    "KnowledgeSections",
    "get_registry",
    "reset_registry",
]
