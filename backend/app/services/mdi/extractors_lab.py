"""VN lab-report entity extractor (BRD §E, Master Plan §1.4).

Deterministic parser over OCR text of a printed VN lab report. One report yields
MANY independent lab-result candidates (finding 1); each carries the ORIGINAL
value/unit/label (never a silently-normalized value — §E) plus a stable
dedupe_key. Reuses ``lab_interpreter.normalize_biomarker`` to recognize which
lines are real biomarkers, so free-text/header lines are ignored. No LLM/network.
"""

from __future__ import annotations

import re

from app.domain import lab_interpreter
from app.models.medical_document import CANDIDATE_LAB_RESULT

from .extractors import CandidateDraft, make_dedupe_key

# analyte name (may contain digits, e.g. HbA1c) … a SEPARATOR (colon/space) …
# value … unit … optional (low - high) reference range. The separator before the
# value is required so an analyte's embedded digit (HbA1c) is never read as the value.
_VALUE_RE = re.compile(
    r"^(?P<name>.*?[A-Za-zÀ-ỹ%)])[:=\s]\s*"
    r"(?P<value>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>%|[A-Za-zµμ]+(?:/[A-Za-zµμ.]+)?)?"
    r"(?:\s*\(?\s*(?P<low>\d+(?:[.,]\d+)?)\s*[-–—]\s*(?P<high>\d+(?:[.,]\d+)?)\s*\)?)?"
)
_DATE_RE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")


def _num(raw: str) -> float:
    return float(raw.replace(",", "."))


def _report_date(lines: list[str]) -> str | None:
    for ln in lines:
        low = ln.lower()
        if any(k in low for k in ("ngày", "date", "thu mẫu", "lấy mẫu", "kết quả")):
            m = _DATE_RE.search(ln)
            if m:
                return m.group(0)
    for ln in lines:  # fall back to any date on the report
        m = _DATE_RE.search(ln)
        if m:
            return m.group(0)
    return None


class LabExtractor:
    """Parse a printed VN lab report into per-analyte candidates."""

    def extract(
        self, *, text: str, doc_type: str, ocr_confidence: float
    ) -> list[CandidateDraft]:
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        report_date = _report_date(lines)

        drafts: list[CandidateDraft] = []
        ordinal = 0
        for ln in lines:
            m = _VALUE_RE.search(ln)
            if not m:
                continue
            raw_name = m.group("name").strip(" :=.-")
            if not raw_name:
                continue
            canonical = lab_interpreter.normalize_biomarker(raw_name)
            if canonical is None:
                continue  # not a recognized biomarker → skip (headers, notes, ids)

            value = _num(m.group("value"))
            unit = (m.group("unit") or "").strip() or None
            ref_range = None
            if m.group("low") and m.group("high"):
                ref_range = f"{m.group('low')}-{m.group('high')}"

            fields = {
                "test_name": raw_name,
                "original_test_name": raw_name,
                "canonical": canonical,
                # ORIGINAL value/unit are preserved verbatim; normalization to SI
                # happens only at promotion, keeping the original for display (§E).
                "value": value,
                "unit": unit,
                "reference_range": ref_range,
                "specimen_date": report_date,
            }
            conf = round(float(ocr_confidence), 3)
            drafts.append(
                CandidateDraft(
                    candidate_type=CANDIDATE_LAB_RESULT,
                    ordinal=ordinal,
                    fields=fields,
                    dedupe_key=make_dedupe_key(
                        CANDIDATE_LAB_RESULT,
                        canonical,
                        report_date or "",
                        # canonical numeric form so "5.6"/"5.60"/"5,60" → one key
                        f"{round(value, 4):g}",
                        unit or "",
                    ),
                    field_confidence={"value": conf, "unit": conf if unit else 0.0},
                )
            )
            ordinal += 1
        return drafts
