"""Staged OCR / extraction pipeline (Master Plan §1.4).

Explicit stage interfaces so any provider swaps without touching the patient
domain:

    Preprocessor → OcrEngine → EntityExtractor → Normalizer → ConfidenceScorer
    → ReviewGate → (Promoter, applied later at confirm-time)

The pipeline turns document bytes into a ``PipelineResult`` — a classified doc
type plus a set of independently-reviewable ``CandidateDraft``s in ``needs_review``.
Everything is injectable; the deterministic ``MockOcrEngine`` + mock extractors are
the CI default so cloud credentials are never a blocker for core dev.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.services.ocr_engine import OcrTextResult, run_ocr

from .classifier import classify_document
from .extractors import CandidateDraft, get_extractor

# Bumped when the candidate schema or extraction contract changes materially.
SCHEMA_VERSION = "mdi-1"


@dataclass
class PageResult:
    page_no: int
    ocr_raw: str
    confidence: float
    blocks: dict | None = None


@dataclass
class PipelineResult:
    doc_type: str
    classification_confidence: float
    provider: str
    model: str | None
    pages: list[PageResult]
    candidates: list[CandidateDraft]
    warnings: list[str] = field(default_factory=list)


class OcrEngineProtocol(Protocol):
    name: str

    def run(self, image_bytes: bytes, mime: str) -> OcrTextResult: ...


def _default_ocr(image_bytes: bytes, mime: str) -> OcrTextResult:
    """Default engine call — delegates to the existing selection logic (§1.4)."""
    return run_ocr(image_bytes, mime)


def run_pipeline(
    *,
    page_bytes: list[bytes],
    mime: str,
    doc_type_hint: str | None = None,
    ocr_run=_default_ocr,
) -> PipelineResult:
    """Run the staged pipeline over one document's page images.

    ``ocr_run`` is injectable (tests pass a deterministic callable). ``page_bytes``
    is one entry per page; single-image documents pass a one-element list.
    """
    pages: list[PageResult] = []
    warnings: list[str] = []
    provider = "mock"

    combined_text_parts: list[str] = []
    for idx, raw in enumerate(page_bytes, start=1):
        result = ocr_run(raw, mime)
        provider = result.provider
        warnings.extend(result.warnings)
        pages.append(
            PageResult(page_no=idx, ocr_raw=result.text, confidence=result.confidence)
        )
        combined_text_parts.append(result.text)

    combined_text = "\n\n".join(combined_text_parts)
    avg_conf = (
        sum(p.confidence for p in pages) / len(pages) if pages else 0.0
    )

    doc_type, class_conf = classify_document(combined_text, hint=doc_type_hint)

    extractor = get_extractor(doc_type)
    candidates = extractor.extract(
        text=combined_text, doc_type=doc_type, ocr_confidence=avg_conf
    )

    return PipelineResult(
        doc_type=doc_type,
        classification_confidence=class_conf,
        provider=provider,
        model=None,
        pages=pages,
        candidates=candidates,
        warnings=warnings,
    )
