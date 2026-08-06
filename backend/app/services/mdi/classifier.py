"""Document-type classifier (Master Plan §1.3 — route to the correct extractor).

A lightweight Vietnamese-first keyword heuristic. An explicit ``hint`` from the
upload (the patient chose "Take prescription photo") always wins over the heuristic
— the patient knows what they photographed. Cloud/ML classification can replace
``classify_document`` later without touching callers.
"""

from __future__ import annotations

DOC_PRESCRIPTION = "prescription"
DOC_LAB_REPORT = "lab_report"
DOC_GENERAL = "general"
DOC_UNKNOWN = "unknown"

_VALID_HINTS = frozenset({DOC_PRESCRIPTION, DOC_LAB_REPORT, DOC_GENERAL})

# Lowercased VN + EN keyword signals per document type.
_PRESCRIPTION_KEYWORDS = (
    "đơn thuốc", "don thuoc", "prescription", "rx", "cách dùng",
    "liều dùng", "kê đơn", "bác sĩ kê", "viên", "ngày uống",
)
_LAB_KEYWORDS = (
    "xét nghiệm", "xet nghiem", "kết quả", "ket qua", "chỉ số", "glucose",
    "hba1c", "cholesterol", "creatinin", "trị số", "đơn vị", "khoảng tham chiếu",
    "reference", "mmol/l", "mg/dl", "u/l",
)
_GENERAL_KEYWORDS = (
    "chẩn đoán", "xuất viện", "tóm tắt", "siêu âm", "x-quang", "ct scan", "mri",
    "giải phẫu bệnh", "phiếu khám", "tái khám", "discharge", "imaging", "pathology",
    "referral", "chuyển tuyến",
)


def _score(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for kw in keywords if kw in text)


def classify_document(text: str, *, hint: str | None = None) -> tuple[str, float]:
    """Return ``(doc_type, confidence)``.

    ``hint`` (patient's chosen capture type) is authoritative when valid.
    Otherwise a keyword vote picks the type; confidence reflects the margin.
    """
    if hint in _VALID_HINTS:
        return hint, 1.0

    lowered = (text or "").lower()
    scores = {
        DOC_PRESCRIPTION: _score(lowered, _PRESCRIPTION_KEYWORDS),
        DOC_LAB_REPORT: _score(lowered, _LAB_KEYWORDS),
        DOC_GENERAL: _score(lowered, _GENERAL_KEYWORDS),
    }
    best_type = max(scores, key=lambda k: scores[k])
    best = scores[best_type]
    if best == 0:
        return DOC_UNKNOWN, 0.0

    total = sum(scores.values()) or 1
    confidence = round(best / total, 3)
    return best_type, confidence
