"""Bundled synthetic QA fixtures (dev/staging automation only).

These ship a tiny, fully synthetic medical document (a valid placeholder image
plus its known "OCR" text) so Journey A (document OCR) can be ingested through
the REAL pipeline without a native camera. The content is entirely fabricated —
NO real PHI. Reachable only via ``POST /documents/qa-fixture`` when
``settings.qa_fixture_enabled`` is on (never in production; the startup guard in
``config.validate_required_env_vars`` refuses to boot prod with it enabled).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_QA_PRESCRIPTION_PNG = _DIR / "qa_prescription.png"
_QA_PRESCRIPTION_TXT = _DIR / "qa_prescription.txt"


@dataclass(frozen=True)
class QaFixture:
    """A bundled synthetic document + the deterministic text it "OCRs" to."""

    image_bytes: bytes
    mime: str
    doc_type_hint: str
    ocr_text: str
    ocr_confidence: float


def load_qa_prescription_fixture() -> QaFixture:
    """Load the synthetic prescription fixture (image bytes + known OCR text).

    The image is a valid placeholder PNG that passes magic-byte validation; the
    text is a fabricated VN prescription that the real ``PrescriptionExtractor``
    turns into deterministic ``needs_review`` medication candidates.
    """
    return QaFixture(
        image_bytes=_QA_PRESCRIPTION_PNG.read_bytes(),
        mime="image/png",
        doc_type_hint="prescription",
        ocr_text=_QA_PRESCRIPTION_TXT.read_text(encoding="utf-8"),
        ocr_confidence=0.95,
    )


__all__ = ["QaFixture", "load_qa_prescription_fixture"]
