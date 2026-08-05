"""VN lab-report entity extractor (BRD §E, Master Plan §1.4).

Deterministic parser over OCR text of a printed VN lab report. One report yields
MANY independent lab-result candidates (finding 1); each carries the ORIGINAL
value/unit/label (never a silently-normalized value — §E) plus a stable
dedupe_key. No LLM/network.

Analyte recognition uses ``lab_parser._match_biomarker`` — the SAME hardened
matcher the /lab-uploads path uses — not ``lab_interpreter.normalize_biomarker``.
That matters clinically: ``normalize_biomarker``'s step 4 is a bare containment
scan (``alias in key or key in alias``), so it resolves "VLDL" to ``ldl`` and
"Non-HDL cholesterol" to ``hdl``. A patient confirming the VLDL line off their own
report would overwrite their LDL with a much lower number and see it classified
optimal — a false negative on cardiovascular risk, and invisible at review time
because the card shows the printed label, not the resolved canonical.
``_match_biomarker`` drops those labels outright (``_UNMAPPABLE_LABEL_RE``) and
applies longest-alias/shadowing rules, so a wrong analyte becomes a dropped row.
"""

from __future__ import annotations

import re

from app.models.medical_document import CANDIDATE_LAB_RESULT
from app.services.lab_parser import _match_biomarker, _strip_accents, build_alias_index

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
        # ONE shared alias index — the same one /lab-uploads uses. Calling
        # _match_biomarker with no index silently falls back to the bare
        # _ALIAS_INDEX, under which "HDL Cholesterol" resolves to
        # total_cholesterol. See lab_parser.build_alias_index.
        alias_index = build_alias_index()
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
            # Match against the accent-stripped, lower-cased label, the form
            # `_match_biomarker` and `_UNMAPPABLE_LABEL_RE` are written against.
            matched = _match_biomarker(_strip_accents(raw_name.lower()), alias_index)
            if matched is None:
                # Not a recognized biomarker (headers, notes, ids) OR a label with
                # no safe canonical (non-HDL, VLDL, lipid ratios). Dropping the row
                # is deliberate: a wrong analyte is worse than a missing one.
                continue
            canonical = matched[0].canonical

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
