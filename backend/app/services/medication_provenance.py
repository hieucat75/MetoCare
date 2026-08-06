"""Reverse provenance read: a canonical Medication → the source document(s) it was
promoted from (Master Plan §1.5 ``PromotionLink``).

The MDI pipeline only walks FORWARD (document → extraction → candidates → promotion).
The patient-facing medication surface needs the reverse edge so a patient can answer
"where did this medication come from?" from the medication itself, without first
having to find the document. Nothing outside the promote path reads ``PromotionLink``
today, so this module adds the missing read.

Read-only, no HTTP concerns: the route layer owns BOLA, the documents-consent gate
and status mapping.

PHI discipline — ``ExtractionCandidate.fields_json`` holds raw OCR output that was
never reviewed field-by-field, so it is NEVER returned wholesale. Only the explicit
allowlists below leave this module. ``diagnosis`` is deliberately excluded: §1.9
forbids a diagnosis becoming canonical without clinician confirmation, and echoing an
unconfirmed OCR'd diagnosis onto a medication page would do exactly that by the back
door.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.medical_document import (
    DocumentExtraction,
    ExtractionCandidate,
    MedicalDocument,
    PromotionLink,
)

# ``PromotionOutcome.canonical_type`` emitted by MedicationPromoter
# (services/mdi/promoters.py) for both created and merged_into outcomes.
CANONICAL_TYPE_MEDICATION = "medication"

# Prescription line fields safe to echo back: they describe THIS medication and are
# exactly what the patient already saw and confirmed during candidate review.
PRESCRIPTION_FIELDS = (
    "strength",
    "form",
    "quantity",
    "frequency",
    "route",
    "duration",
    "instructions",
)

# Prescription header context. ``diagnosis`` is intentionally absent — see module docstring.
PRESCRIPTION_CONTEXT_FIELDS = ("facility", "prescriber", "prescribed_date")


def _as_utc(value: dt.datetime | None) -> dt.datetime | None:
    """SQLite returns naive datetimes; stamp them UTC so the API always emits an offset."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=dt.UTC)


def _pick(source: Any, keys: tuple[str, ...]) -> dict[str, str]:
    """Allowlist-copy scalar values out of an untrusted JSON blob.

    Anything non-scalar or blank is dropped rather than coerced, so a malformed
    extraction can never inject a structure the API contract does not describe.
    """
    if not isinstance(source, dict):
        return {}
    out: dict[str, str] = {}
    for key in keys:
        value = source.get(key)
        if isinstance(value, str | int | float) and not isinstance(value, bool):
            text = str(value).strip()
            if text:
                out[key] = text
    return out


def source_documents_for_medication(
    db: Session, *, patient_id: str, medication_id: str
) -> list[dict]:
    """Every source document this medication was promoted from, newest promotion first.

    Returns ``[]`` when the medication was entered manually (no PromotionLink) — the
    common case. Callers must render that as "manually entered", never as an error.

    The ``patient_id`` filter is defence-in-depth: the route already proved
    self-ownership, but scoping the joins means a mis-shaped ``medication_id`` can
    never surface another patient's document.
    """
    rows = db.execute(
        select(PromotionLink, ExtractionCandidate, MedicalDocument, DocumentExtraction)
        .join(ExtractionCandidate, PromotionLink.candidate_id == ExtractionCandidate.id)
        .join(MedicalDocument, ExtractionCandidate.document_id == MedicalDocument.id)
        .outerjoin(
            DocumentExtraction, ExtractionCandidate.extraction_id == DocumentExtraction.id
        )
        .where(
            PromotionLink.canonical_type == CANONICAL_TYPE_MEDICATION,
            PromotionLink.canonical_id == medication_id,
            ExtractionCandidate.patient_id == patient_id,
            MedicalDocument.patient_id == patient_id,
            MedicalDocument.deleted_at.is_(None),
        )
        .order_by(PromotionLink.created_at.desc())
    ).all()

    return [
        {
            "document_id": doc.id,
            "doc_type": doc.doc_type,
            "document_status": doc.status,
            "document_source": doc.source,
            "page_count": doc.page_count,
            "uploaded_at": _as_utc(doc.created_at),
            "promotion_action": link.action,
            "promoted_at": _as_utc(link.created_at),
            "candidate_id": cand.id,
            "candidate_status": cand.status,
            "candidate_reviewed_at": _as_utc(cand.reviewed_at),
            "prescription_fields": _pick(cand.fields_json, PRESCRIPTION_FIELDS),
            "prescription_context": _pick(
                (cand.fields_json or {}).get("prescription_context")
                if isinstance(cand.fields_json, dict)
                else None,
                PRESCRIPTION_CONTEXT_FIELDS,
            ),
            # OCR provenance — which engine produced the text this record came from.
            "ocr_provider": extraction.provider if extraction else None,
            "ocr_model": extraction.model if extraction else None,
            "ocr_prompt_version": extraction.prompt_version if extraction else None,
            "ocr_schema_version": extraction.schema_version if extraction else None,
            "extraction_review_state": extraction.review_state if extraction else None,
        }
        for link, cand, doc, extraction in rows
    ]
