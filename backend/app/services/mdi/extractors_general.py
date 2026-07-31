"""General medical-report entity extractor (BRD §F, Master Plan §1.9).

Deterministic, Vietnamese-first parser over OCR text of a discharge / imaging /
pathology / referral / exam report. Produces TYPED candidates only — never
canonical clinical facts (§1.9): diagnosis / procedure / finding / recommendation
/ follow_up. Confirmation is per-candidate; a diagnosis is display-only until
confirmed; a follow_up becomes a task/reminder only after confirmation (Journey 3
schedules it). No LLM/network.
"""

from __future__ import annotations

import re

from app.models.medical_document import (
    CANDIDATE_DIAGNOSIS,
    CANDIDATE_FINDING,
    CANDIDATE_FOLLOW_UP,
    CANDIDATE_MEDICATION,
    CANDIDATE_PROCEDURE,
    CANDIDATE_RECOMMENDATION,
)

from .extractors import CandidateDraft, make_dedupe_key

# A dose/strength signal → the line is a medication order, not a procedure/finding.
# Such candidates are re-typed to `medication` so they route through the
# MedicationPromoter (statement-first reconciliation), never RecordOnlyPromoter (§1.9).
_MED_RE = re.compile(r"\d+\s?(mg|mcg|g|ml|viên|vien|iu|ui)\b", re.IGNORECASE)

# Section-label → candidate type. First matching label on a line wins; the text
# AFTER the label (or the following lines) is the candidate content.
_LABELS: list[tuple[str, str]] = [
    ("chẩn đoán", CANDIDATE_DIAGNOSIS),
    ("chan doan", CANDIDATE_DIAGNOSIS),
    ("diagnosis", CANDIDATE_DIAGNOSIS),
    ("thủ thuật", CANDIDATE_PROCEDURE),
    ("phẫu thuật", CANDIDATE_PROCEDURE),
    ("chỉ định", CANDIDATE_PROCEDURE),
    ("procedure", CANDIDATE_PROCEDURE),
    ("kết luận", CANDIDATE_FINDING),
    ("mô tả", CANDIDATE_FINDING),
    ("finding", CANDIDATE_FINDING),
    ("tái khám", CANDIDATE_FOLLOW_UP),
    ("hẹn khám", CANDIDATE_FOLLOW_UP),
    ("follow-up", CANDIDATE_FOLLOW_UP),
    ("follow up", CANDIDATE_FOLLOW_UP),
    ("lời dặn", CANDIDATE_RECOMMENDATION),
    ("khuyến nghị", CANDIDATE_RECOMMENDATION),
    ("dặn dò", CANDIDATE_RECOMMENDATION),
    ("recommendation", CANDIDATE_RECOMMENDATION),
]

_DATE_RE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")


def _segments(line: str) -> list[tuple[str, str]]:
    """Split one line into (candidate_type, content) segments — one per section
    label present, in left-to-right order. This prevents same-line label bleed
    (a follow_up sharing a line with a diagnosis becomes its own candidate)."""
    low = line.lower()
    hits: list[tuple[int, str, str]] = []
    for label, ctype in _LABELS:
        pos = low.find(label)
        if pos != -1:
            hits.append((pos, label, ctype))
    if not hits:
        return []
    hits.sort(key=lambda h: h[0])
    segs: list[tuple[str, str]] = []
    for i, (pos, label, ctype) in enumerate(hits):
        start = pos + len(label)
        end = hits[i + 1][0] if i + 1 < len(hits) else len(line)
        content = line[start:end].lstrip(" :：-–").strip()
        segs.append((ctype, content))
    return segs


def _summary(lines: list[str]) -> str:
    """A short structured summary — the first few content lines, capped."""
    body = " · ".join(lines[:6])
    return body[:500]


class GeneralReportExtractor:
    """Parse a general medical report into typed candidates (§1.9)."""

    def extract(
        self, *, text: str, doc_type: str, ocr_confidence: float
    ) -> list[CandidateDraft]:
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        report_date = None
        for ln in lines:
            m = _DATE_RE.search(ln)
            if m:
                report_date = m.group(0)
                break
        summary = _summary(lines)

        drafts: list[CandidateDraft] = []
        ordinal = 0
        conf = round(float(ocr_confidence), 3)
        for i, ln in enumerate(lines):
            for ctype, content in _segments(ln):
                # Label on its own line → look one line ahead for the content
                # (common discharge layout: header line, indented content below).
                if not content and i + 1 < len(lines) and not _segments(lines[i + 1]):
                    content = lines[i + 1]
                if not content:
                    continue
                # A dose/strength signal means this is a medication order — re-type
                # so it routes through MedicationPromoter's reconciliation, never
                # the record-only path (§1.9).
                if _MED_RE.search(content):
                    ctype = CANDIDATE_MEDICATION
                fields: dict = {
                    "text": content,
                    "report_date": report_date,
                    "summary": summary,
                }
                if ctype == CANDIDATE_MEDICATION:
                    fields["name"] = content  # MedicationPromoter reads fields["name"]
                drafts.append(
                    CandidateDraft(
                        candidate_type=ctype,
                        ordinal=ordinal,
                        fields=fields,
                        dedupe_key=make_dedupe_key(ctype, content, report_date or ""),
                        field_confidence={"text": conf},
                    )
                )
                ordinal += 1
        return drafts
