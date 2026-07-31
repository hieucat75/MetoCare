"""VN prescription entity extractor (BRD §D, Master Plan §1.4 EntityExtractor).

Deterministic, Vietnamese-first parser over OCR text of a *printed* prescription.
One prescription yields MANY independent medication candidates (finding 1); each
carries per-field confidence and a stable dedupe_key so re-upload never double-
promotes (§1.5). Handwriting → whatever OCR yields, low confidence, mandatory
review (every candidate enters needs_review regardless). No network, no LLM.
"""

from __future__ import annotations

import re

from app.models.medical_document import CANDIDATE_MEDICATION

from .extractors import CandidateDraft, make_dedupe_key

# ── field patterns ───────────────────────────────────────────────────────────
_ENUM_RE = re.compile(r"^\s*(\d{1,2})\s*[).\-/]\s*(.+)$")
_STRENGTH_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(mg|mcg|g|ml|iu|ui|đvqt)\b", re.IGNORECASE
)
_FORMS = (
    "viên", "ống", "gói", "chai", "tuýp", "lọ", "vỉ", "túi", "gam",
    "tablet", "capsule", "cap", "tab",
)
_FORM_RE = re.compile(r"\b(" + "|".join(map(re.escape, _FORMS)) + r")\b", re.IGNORECASE)
_QTY_RE = re.compile(
    r"(?:sl|số\s*lượng)\s*[:.]?\s*(\d+)|x\s*(\d+)\b|(\d+)\s*(?:viên|ống|gói|chai|lọ|vỉ)",
    re.IGNORECASE,
)
_FREQ_RE = re.compile(
    r"ngày\s*(?:uống\s*)?\d+\s*lần|\d+\s*lần\s*/?\s*ngày|"
    r"(?:sáng|trưa|chiều|tối)(?:\s*[,\-/]\s*(?:sáng|trưa|chiều|tối))*",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(r"trong\s*(\d+)\s*(ngày|tuần|tháng)", re.IGNORECASE)
_DATE_RE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")

_ROUTE_BY_KW = {
    "uống": "uống", "ngậm": "ngậm", "tiêm": "tiêm", "bôi": "bôi",
    "nhỏ mắt": "nhỏ mắt", "nhỏ": "nhỏ", "xịt": "xịt", "đặt": "đặt",
}

_HEADER_INSTRUCTION_KW = ("cách dùng", "uống", "ngày", "sáng", "trưa", "chiều", "tối", "liều")


def _extract_header(lines: list[str]) -> dict:
    ctx: dict[str, str] = {}
    for ln in lines:
        low = ln.lower()
        if "facility" not in ctx and any(
            k in low for k in ("bệnh viện", "phòng khám", "phòng mạch", "clinic")
        ):
            ctx["facility"] = ln.strip()
        if "prescriber" not in ctx and any(k in low for k in ("bác sĩ", "bác sỹ", "bs.", "bs ")):
            ctx["prescriber"] = ln.strip()
        if "prescribed_date" not in ctx:
            m = _DATE_RE.search(ln)
            if m:
                ctx["prescribed_date"] = m.group(0)
        if "diagnosis" not in ctx and ("chẩn đoán" in low or "chan doan" in low):
            after = re.split(r"chẩn đoán|chan doan", ln, flags=re.IGNORECASE)[-1]
            ctx["diagnosis"] = after.lstrip(" :-").strip() or ln.strip()
    return ctx


def _route_of(text: str) -> str | None:
    low = text.lower()
    for kw, route in _ROUTE_BY_KW.items():
        if kw in low:
            return route
    return None


def _parse_medicine(line: str, instruction: str | None) -> dict:
    combined = line if not instruction else f"{line} {instruction}"
    strength_m = _STRENGTH_RE.search(line)
    strength = f"{strength_m.group(1)}{strength_m.group(2).lower()}" if strength_m else None
    # Name = the text before the strength token (or the whole line, trimmed).
    name_part = line[: strength_m.start()] if strength_m else line
    name = re.sub(r"^\s*\d{1,2}\s*[).\-/]\s*", "", name_part).strip(" .:-")
    form_m = _FORM_RE.search(combined)
    qty_m = _QTY_RE.search(combined)
    quantity = next((g for g in (qty_m.groups() if qty_m else []) if g), None)
    freq_m = _FREQ_RE.search(combined)
    dur_m = _DURATION_RE.search(combined)
    return {
        "name": name,
        "strength": strength,
        "form": form_m.group(1).lower() if form_m else None,
        "quantity": quantity,
        "frequency": freq_m.group(0).strip() if freq_m else None,
        "route": _route_of(combined),
        "duration": f"{dur_m.group(1)} {dur_m.group(2)}" if dur_m else None,
        "instructions": instruction.strip() if instruction else None,
    }


def _is_instruction_line(line: str) -> bool:
    low = line.lower()
    return not _ENUM_RE.match(line) and any(k in low for k in _HEADER_INSTRUCTION_KW)


class PrescriptionExtractor:
    """Parse a printed VN prescription into per-medicine candidates."""

    def extract(
        self, *, text: str, doc_type: str, ocr_confidence: float
    ) -> list[CandidateDraft]:
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        context = _extract_header(lines)

        # Locate enumerated medicine lines; otherwise fall back to any line that
        # carries a strength token (a strong medicine signal).
        indexed = list(enumerate(lines))
        med_indices = [i for i, ln in indexed if _ENUM_RE.match(ln)]
        if not med_indices:
            med_indices = [i for i, ln in indexed if _STRENGTH_RE.search(ln)]

        drafts: list[CandidateDraft] = []
        ordinal = 0
        for idx in med_indices:
            line = lines[idx]
            instruction = None
            if idx + 1 < len(lines) and _is_instruction_line(lines[idx + 1]):
                instruction = lines[idx + 1]
            fields = _parse_medicine(line, instruction)
            if not fields["name"]:
                continue
            fields["prescription_context"] = context
            # High-risk fields always require confirmation regardless of confidence
            # (§1.6) — surface which fields are low-confidence for the review UI.
            conf = round(float(ocr_confidence), 3)
            field_conf = {
                "name": conf,
                "strength": conf if fields["strength"] else 0.0,
                "frequency": conf if fields["frequency"] else 0.0,
            }
            drafts.append(
                CandidateDraft(
                    candidate_type=CANDIDATE_MEDICATION,
                    ordinal=ordinal,
                    fields=fields,
                    # Include frequency + instructions so two legitimately
                    # distinct lines for the same drug+strength+form (e.g. a
                    # morning vs. evening regimen) remain SEPARATE candidates
                    # rather than one being silently deduped away (§1.5 finding).
                    dedupe_key=make_dedupe_key(
                        CANDIDATE_MEDICATION,
                        fields["name"],
                        fields.get("strength") or "",
                        fields.get("form") or "",
                        fields.get("frequency") or "",
                        fields.get("instructions") or "",
                    ),
                    field_confidence=field_conf,
                )
            )
            ordinal += 1
        return drafts
