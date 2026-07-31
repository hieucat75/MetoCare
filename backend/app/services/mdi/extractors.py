"""Entity extractors (Master Plan §1.4 EntityExtractor stage) + a registry.

An extractor turns OCR text for one document into a set of independently-
confirmable ``CandidateDraft``s. Real per-doc-type extractors (prescription in M3,
lab in M4, general report in M7) register themselves here; until then the
deterministic ``MockExtractor`` produces candidates so the candidate lifecycle is
exercisable end-to-end in CI without cloud OCR.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Protocol

from app.models.medical_document import (
    CANDIDATE_FINDING,
    CANDIDATE_LAB_RESULT,
    CANDIDATE_MEDICATION,
)

# doc_type → the candidate_type the mock extractor emits.
_MOCK_TYPE_BY_DOC = {
    "prescription": CANDIDATE_MEDICATION,
    "lab_report": CANDIDATE_LAB_RESULT,
    "general": CANDIDATE_FINDING,
    "unknown": CANDIDATE_FINDING,
}

_MAX_MOCK_CANDIDATES = 5


@dataclass
class CandidateDraft:
    """A single extracted item before it is persisted as an ExtractionCandidate."""

    candidate_type: str
    ordinal: int
    fields: dict
    dedupe_key: str
    field_confidence: dict = field(default_factory=dict)


def make_dedupe_key(candidate_type: str, *parts: str) -> str:
    """Stable dedupe key: sha256 of the candidate type + normalized parts.

    Re-extraction of the same document yields the same key for the same logical
    item, so ``uq_extraction_dedupe_key`` collapses duplicates (§1.5). Internal
    whitespace is collapsed so OCR whitespace jitter across runs (a real
    Tesseract nondeterminism source) does not change the key.
    """
    norm = "|".join(
        re.sub(r"\s+", " ", p).strip().lower() for p in parts if p and p.strip()
    )
    digest = sha256(f"{candidate_type}::{norm}".encode()).hexdigest()
    return digest[:32]


class EntityExtractor(Protocol):
    def extract(
        self, *, text: str, doc_type: str, ocr_confidence: float
    ) -> list[CandidateDraft]: ...


class MockExtractor:
    """Deterministic extractor for CI + M2. Emits one candidate per meaningful line."""

    def extract(
        self, *, text: str, doc_type: str, ocr_confidence: float
    ) -> list[CandidateDraft]:
        candidate_type = _MOCK_TYPE_BY_DOC.get(doc_type, CANDIDATE_FINDING)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        # Keep only content-bearing lines (skip obvious headers with no ':' or digit).
        content = [ln for ln in lines if (":" in ln or any(c.isdigit() for c in ln))]
        drafts: list[CandidateDraft] = []
        for ordinal, line in enumerate(content[:_MAX_MOCK_CANDIDATES]):
            drafts.append(
                CandidateDraft(
                    candidate_type=candidate_type,
                    ordinal=ordinal,
                    fields={"raw_line": line, "source": "mock"},
                    dedupe_key=make_dedupe_key(candidate_type, line),
                    field_confidence={"raw_line": round(ocr_confidence, 3)},
                )
            )
        return drafts


_REGISTRY: dict[str, EntityExtractor] = {}
_FALLBACK: EntityExtractor = MockExtractor()


def register_extractor(doc_type: str, extractor: EntityExtractor) -> None:
    """Register a real per-doc-type extractor (M3 prescription, M4 lab, M7 report)."""
    _REGISTRY[doc_type] = extractor


def get_extractor(doc_type: str) -> EntityExtractor:
    """Return the extractor for ``doc_type``, falling back to the mock extractor."""
    return _REGISTRY.get(doc_type, _FALLBACK)


def reset_extractors() -> None:
    """Clear registered extractors (test isolation)."""
    _REGISTRY.clear()
