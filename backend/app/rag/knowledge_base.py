"""Knowledge base — load curated Vietnamese medical markdown into a vector store.

Seed content lives in `data/rag_seed/*.md` (no PHI). Each `##` section becomes a
chunk. Chunks are vetted for prompt-injection at ingestion time (defense-in-depth
even though the corpus is curated) and skipped if they carry an injection.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import get_settings
from app.domain import guardrails

from .embedding import EmbeddingProvider, get_embedding_provider
from .vector_store import Document, VectorStore, make_vector_store

_HEADING_RE = re.compile(r"^##\s+(.*)$", re.MULTILINE)


def chunk_markdown(text: str, *, source: str) -> list[Document]:
    """Split markdown into chunks keyed by `##` headings.

    Content before the first `##` (e.g. the title + disclaimer) is dropped to
    keep chunks focused. Each chunk id is `source#index`.
    """
    docs: list[Document] = []
    matches = list(_HEADING_RE.finditer(text))
    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if not body:
            continue
        chunk = f"{heading}\n{body}"
        docs.append(
            Document(
                id=f"{source}#{i}",
                text=chunk,
                source=source,
                metadata={"heading": heading},
            )
        )
    return docs


class KnowledgeBase:
    def __init__(
        self,
        *,
        embedder: EmbeddingProvider | None = None,
        store: VectorStore | None = None,
    ) -> None:
        self._embedder = embedder or get_embedding_provider()
        self._store = store or make_vector_store()
        self.skipped_injection = 0

    @property
    def store(self) -> VectorStore:
        return self._store

    @property
    def embedder(self) -> EmbeddingProvider:
        return self._embedder

    def ingest_document(self, doc: Document) -> bool:
        """Index a single chunk. Returns False if rejected (injection)."""
        if guardrails.is_injection(doc.text):
            self.skipped_injection += 1
            return False
        self._store.add(doc, self._embedder.embed(doc.text))
        return True

    def ingest_markdown(self, text: str, *, source: str) -> int:
        count = 0
        for doc in chunk_markdown(text, source=source):
            if self.ingest_document(doc):
                count += 1
        return count

    def load_seed_dir(self, seed_dir: str | Path) -> int:
        path = Path(seed_dir)
        total = 0
        if not path.exists():
            return 0
        for md in sorted(path.glob("*.md")):
            total += self.ingest_markdown(md.read_text(encoding="utf-8"), source=md.name)
        return total

    def __len__(self) -> int:
        return len(self._store)


def build_default_kb() -> KnowledgeBase:
    """Build a KB from the configured seed directory."""
    kb = KnowledgeBase()
    kb.load_seed_dir(get_settings().rag_seed_dir)
    return kb
