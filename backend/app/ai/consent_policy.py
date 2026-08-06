"""Meto per-category consent policy (BRD §J).

Explicit, purpose-specific, versioned consent gates AI use of each PHI category.
Enforcement is fail-closed: a category is usable only when the patient has an
active grant recorded against the CURRENT policy version. Revocation or a policy
bump immediately blocks future use of that category.

No PHI ever appears here or in consent audit records — only category keys.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.meto import MetoConsent

# Bump when the consent purpose text / scope changes. Grants recorded against an
# older version are treated as NOT granted until the patient re-consents.
CONSENT_POLICY_VERSION = "1.0"

# Canonical category keys (the 5 owner-approved purposes).
CATEGORY_HEALTH_RECORDS = "health_records"        # health records + metrics
CATEGORY_MEDICATIONS = "medications"              # medications + adherence
CATEGORY_DOCUMENTS = "documents"                  # medical documents / OCR
CATEGORY_DOCTOR_CONSULTATION = "doctor_consultation"  # doctor-consultation data
CATEGORY_AI_PROCESSING = "ai_processing"          # master: AI may process at all

# Ordered for stable API/UI presentation.
CONSENT_CATEGORIES: tuple[str, ...] = (
    CATEGORY_AI_PROCESSING,
    CATEGORY_HEALTH_RECORDS,
    CATEGORY_MEDICATIONS,
    CATEGORY_DOCUMENTS,
    CATEGORY_DOCTOR_CONSULTATION,
)

# Purpose-specific description shown to the patient (Vietnamese, patient-facing).
CATEGORY_PURPOSE: dict[str, str] = {
    CATEGORY_AI_PROCESSING: (
        "Cho phép Meto xử lý dữ liệu của bạn bằng AI để trả lời câu hỏi. "
        "Không bật mục này thì Meto sẽ không hoạt động."
    ),
    CATEGORY_HEALTH_RECORDS: (
        "Cho phép Meto dùng hồ sơ sức khỏe và chỉ số (bệnh nền, dị ứng, xét "
        "nghiệm, chỉ số) đã xác nhận để giải thích và nhắc nhở."
    ),
    CATEGORY_MEDICATIONS: (
        "Cho phép Meto dùng thông tin thuốc và mức độ tuân thủ của bạn."
    ),
    CATEGORY_DOCUMENTS: (
        "Cho phép Meto dùng dữ liệu trích xuất từ tài liệu y tế (OCR) bạn đã xác nhận."
    ),
    CATEGORY_DOCTOR_CONSULTATION: (
        "Cho phép Meto dùng dữ liệu buổi tư vấn với bác sĩ."
    ),
}

# Maps each AI-context block to the consent category that governs it. Blocks not
# listed (user_profile, screen_context) carry no clinical PHI and are ungated.
# safety_flags are derived solely from labs/metrics, so they ride health_records.
BLOCK_CONSENT_CATEGORY: dict[str, str] = {
    "health_summary": CATEGORY_HEALTH_RECORDS,
    "care_plan": CATEGORY_HEALTH_RECORDS,
    "recent_labs": CATEGORY_HEALTH_RECORDS,
    "recent_metrics": CATEGORY_HEALTH_RECORDS,
    "medications": CATEGORY_MEDICATIONS,
    "today_context": CATEGORY_DOCTOR_CONSULTATION,
}


def load_granted_categories(db: Session, user_id: str) -> set[str]:
    """Categories the user has actively granted at the CURRENT policy version.

    Fail-closed: a grant that is revoked, or recorded against a stale policy
    version, is excluded — so a policy bump forces re-consent.
    """
    rows = (
        db.query(MetoConsent)
        .filter(
            MetoConsent.user_id == user_id,
            MetoConsent.granted.is_(True),
            MetoConsent.revoked_at.is_(None),
            MetoConsent.policy_version == CONSENT_POLICY_VERSION,
        )
        .all()
    )
    return {r.context_type for r in rows}


def is_granted(db: Session, user_id: str, category: str) -> bool:
    """True iff the given category is actively granted at the current version."""
    return category in load_granted_categories(db, user_id)
