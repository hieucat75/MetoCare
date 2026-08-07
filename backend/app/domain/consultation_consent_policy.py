"""Consultation-specific doctor data-sharing consent policy.

Distinct from every other consent record in the system:

- ``consent.TermsConsent``  — one-time Terms/Privacy acceptance at registration.
- ``governance.Consent``    — long-lived patient→party data-sharing grant.
- ``meto.MetoConsent``      — per-category consent for AI (Meto) processing.
- **this**                  — one grant, scoped to ONE consultation with ONE
  doctor, captured at booking, revocable at any time.

Two independent version stamps are recorded on every grant:

``CONSENT_VERSION``
    The *semantics* of what is being shared (the category set and what each
    category covers). Enforcement is fail-closed on this stamp: a grant recorded
    against an older CONSENT_VERSION is treated as no consent at all, so
    widening the scope forces re-consent and can never silently apply to grants
    the patient made under narrower terms.

``POLICY_VERSION``
    The *copy* the patient actually read. Recorded for audit and to prove what
    was on screen. Deliberately NOT part of the access decision: a typo fix or
    a translation tweak must not tear down PHI access in the middle of a live
    consultation. Bump CONSENT_VERSION — not just this — whenever the meaning
    of the sharing changes.

No PHI ever appears in this module or in any consent/audit record built from
it — only category keys, version stamps, and identifiers.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------

CONSENT_VERSION = "1.0"
POLICY_VERSION = "1.0"

# The purpose this consent authorises. A grant is usable for nothing else.
PURPOSE_DOCTOR_CONSULTATION = "doctor_consultation"

# ---------------------------------------------------------------------------
# Data categories
# ---------------------------------------------------------------------------

CATEGORY_HEALTH_RECORDS = "health_records"
CATEGORY_MEDICATIONS = "medications_and_adherence"
CATEGORY_LAB_RESULTS = "lab_results"
CATEGORY_MEDICAL_DOCUMENTS = "medical_documents"
CATEGORY_PATIENT_PROFILE = "patient_profile"

# Ordered for stable API/UI presentation.
CATEGORIES: tuple[str, ...] = (
    CATEGORY_HEALTH_RECORDS,
    CATEGORY_MEDICATIONS,
    CATEGORY_LAB_RESULTS,
    CATEGORY_MEDICAL_DOCUMENTS,
    CATEGORY_PATIENT_PROFILE,
)

CATEGORY_SET = frozenset(CATEGORIES)

# ---------------------------------------------------------------------------
# Categories that DO NOT exist, on purpose
# ---------------------------------------------------------------------------
#
# The patient's private Meto (AI) conversations are not a grantable category.
# There is no key for them here, so there is no value a client could send that
# would authorise sharing them, and no branch downstream that could read them.
# Sharing AI chat history with a doctor would need its own approved category
# and its own screen — not a widening of this one.
#
NEVER_SHAREABLE: frozenset[str] = frozenset({"ai_chat_history", "meto_conversations"})


def normalize_categories(raw: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    """Return the recognised subset of *raw*, deduplicated and in canonical order.

    Unknown keys — including anything in ``NEVER_SHAREABLE`` — are dropped
    rather than rejected: a client that invents a category must not be able to
    widen the grant, and a client running an older build that omits a category
    must still be able to book with the categories it does know about.
    """
    if not raw:
        return ()
    requested = {c for c in raw if isinstance(c, str)}
    return tuple(c for c in CATEGORIES if c in requested)


# ---------------------------------------------------------------------------
# Patient-facing copy (Vietnamese-first, authored server-side)
# ---------------------------------------------------------------------------
#
# Served to web and mobile so both render the SAME words, and so the text that
# was on screen is versioned alongside the grant. Clients must not hardcode a
# second copy of this.
#
CONSENT_COPY: dict[str, str] = {
    "title": "Chia sẻ thông tin sức khỏe với bác sĩ?",
    "body": (
        "Để bác sĩ có đủ thông tin phục vụ buổi tư vấn, MetoCare có thể chia sẻ "
        "các thông tin sức khỏe liên quan của bạn, bao gồm hồ sơ sức khỏe, thuốc "
        "đang sử dụng, kết quả xét nghiệm và tài liệu y tế đã được bạn xác nhận.\n\n"
        "Thông tin chỉ được cung cấp cho bác sĩ thực hiện buổi tư vấn này và được "
        "sử dụng cho mục đích tư vấn, chăm sóc sức khỏe.\n\n"
        "Bạn có thể quản lý hoặc thu hồi quyền chia sẻ trong phần Quyền riêng tư."
    ),
    "accept_label": "Đồng ý và tiếp tục",
    "decline_label": "Không chia sẻ",
}

# Per-category labels — what each key means, in the patient's words.
CATEGORY_LABEL: dict[str, str] = {
    CATEGORY_HEALTH_RECORDS: "Hồ sơ sức khỏe và chỉ số",
    CATEGORY_MEDICATIONS: "Thuốc đang sử dụng và mức độ tuân thủ",
    CATEGORY_LAB_RESULTS: "Kết quả xét nghiệm",
    CATEGORY_MEDICAL_DOCUMENTS: "Tài liệu y tế đã xác nhận",
    CATEGORY_PATIENT_PROFILE: "Thông tin hồ sơ cá nhân liên quan",
}
