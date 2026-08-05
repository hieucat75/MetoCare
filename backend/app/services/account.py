"""Patient self-service data export + account deletion (GDPR data-subject rights).

DIST-RC compliance slice. Two operations, both strictly self-scoped (the caller's
OWN data only — BOLA enforcement lives in the route, mirroring dashboard.py):

- ``build_export_bundle`` — assembles a decrypted JSON snapshot of everything the
  patient owns (profile, metrics, labs, meds, consents, conversation metadata,
  consultations, document metadata). Read-only.
- ``delete_account`` — soft-deletes clinical rows (never hard-delete), anonymizes
  PII on User + PatientProfile, disables login, and revokes refresh tokens +
  Meto consents. Idempotent: re-running touches only rows still live, so a second
  call returns cleanly instead of raising.

No PHI is written to the audit log — the route records action + patient_id only.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.clinical import (
    HealthMetric,
    LabDocument,
    LabResult,
    LabUploadBatch,
    Medication,
    MedicationStatement,
    SymptomLog,
)
from app.models.consultation import Consultation
from app.models.medical_document import DocumentPage, ExtractionCandidate, MedicalDocument
from app.models.medication_schedule import DoseOccurrence, MedicationSchedule
from app.models.meto import MetoConsent, MetoConversation, MetoMessage
from app.models.notification import Notification
from app.models.patient import PatientProfile
from app.models.user import User


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def build_export_bundle(
    db: Session,
    *,
    user_id: str,
    patient_id: str,
    generated_at: dt.datetime | None = None,
) -> dict:
    """Assemble the caller's own data as a serializable dict.

    All queries are self-scoped by ``patient_id`` / ``user_id``. Encrypted PHI
    columns decrypt transparently on read via the ORM type, which is correct here
    because the bundle is returned only to the data owner. Soft-deleted rows are
    excluded so the export reflects the patient's current record.
    """
    generated_at = generated_at or _now()

    user = db.get(User, user_id)
    profile = db.get(PatientProfile, patient_id)

    metrics = (
        db.execute(
            select(HealthMetric)
            .where(HealthMetric.patient_id == patient_id, HealthMetric.deleted_at.is_(None))
            .order_by(HealthMetric.measured_at)
        )
        .scalars()
        .all()
    )
    lab_results = (
        db.execute(
            select(LabResult)
            .where(LabResult.patient_id == patient_id, LabResult.deleted_at.is_(None))
            .order_by(LabResult.created_at)
        )
        .scalars()
        .all()
    )
    lab_batches = (
        db.execute(
            select(LabUploadBatch)
            .where(LabUploadBatch.patient_id == patient_id, LabUploadBatch.deleted_at.is_(None))
            .order_by(LabUploadBatch.created_at)
        )
        .scalars()
        .all()
    )
    medications = (
        db.execute(
            select(Medication)
            .where(Medication.patient_id == patient_id, Medication.deleted_at.is_(None))
            .order_by(Medication.created_at)
        )
        .scalars()
        .all()
    )
    consents = (
        db.execute(select(MetoConsent).where(MetoConsent.user_id == user_id)).scalars().all()
    )
    conversations = (
        db.execute(
            select(MetoConversation)
            .where(MetoConversation.user_id == user_id, MetoConversation.deleted_at.is_(None))
            .order_by(MetoConversation.created_at)
        )
        .scalars()
        .all()
    )
    consultations = (
        db.execute(
            select(Consultation)
            .where(Consultation.patient_id == patient_id, Consultation.deleted_at.is_(None))
            .order_by(Consultation.created_at)
        )
        .scalars()
        .all()
    )
    documents = (
        db.execute(
            select(MedicalDocument)
            .where(MedicalDocument.patient_id == patient_id, MedicalDocument.deleted_at.is_(None))
            .order_by(MedicalDocument.created_at)
        )
        .scalars()
        .all()
    )

    return {
        "generated_at": generated_at,
        "patient_id": patient_id,
        "profile": _profile_dict(user, profile),
        "health_metrics": [_metric_dict(m) for m in metrics],
        "lab_results": [_lab_result_dict(r) for r in lab_results],
        "lab_batches": [_lab_batch_dict(b) for b in lab_batches],
        "medications": [_medication_dict(m) for m in medications],
        "meto_consents": [_consent_dict(c) for c in consents],
        "meto_conversations": [_conversation_dict(c) for c in conversations],
        "consultations": [_consultation_dict(c) for c in consultations],
        "documents": [_document_dict(d) for d in documents],
    }


def delete_account(db: Session, *, user_id: str, patient_id: str) -> list[str]:
    """Soft-delete + anonymize the caller's account and clinical data.

    Idempotent by construction: soft-delete stamps only touch rows whose
    ``deleted_at`` / ``revoked_at`` is still NULL, and PII anonymization is a
    plain overwrite. The caller (route) owns the commit.

    Returns the list of object-storage keys backing the patient's medical
    documents / lab uploads / page images so the route can erase those blobs
    **after** the DB deletion commits (GDPR erasure completeness — the DB is
    authoritative; blobs are removed only once the soft-delete is durable).
    Keys are collected across *all* the patient's documents (not just newly
    stamped ones), so re-running deletion also cleans blobs an earlier run left
    behind. Storage ``delete`` is a no-op on missing keys, keeping this
    idempotent.
    """
    from app.models.auth_tokens import RefreshToken

    now = _now()
    orphaned_keys: list[str] = []

    # ---- Soft-delete clinical rows (never hard-delete) ----
    for model in (HealthMetric, LabResult, LabUploadBatch, Medication):
        rows = (
            db.execute(
                select(model).where(model.patient_id == patient_id, model.deleted_at.is_(None))
            )
            .scalars()
            .all()
        )
        for row in rows:
            row.deleted_at = now
            row.deleted_by = user_id

    for consult in (
        db.execute(
            select(Consultation).where(
                Consultation.patient_id == patient_id, Consultation.deleted_at.is_(None)
            )
        )
        .scalars()
        .all()
    ):
        consult.deleted_at = now
        consult.deleted_by = user_id

    # Medical documents: stamp the still-active rows AND collect every blob key
    # (quarantine + accepted) across all of the patient's documents for erasure.
    docs = (
        db.execute(select(MedicalDocument).where(MedicalDocument.patient_id == patient_id))
        .scalars()
        .all()
    )
    doc_ids = [doc.id for doc in docs]
    for doc in docs:
        if doc.quarantine_key:
            orphaned_keys.append(doc.quarantine_key)
        if doc.accepted_key:
            orphaned_keys.append(doc.accepted_key)
        if doc.deleted_at is None:
            doc.deleted_at = now
            doc.deleted_by = user_id

    # Per-page images (no soft-delete column; collect their blobs for erasure).
    # PRIV-F5: the page also carries the OCR text itself — stamping only the
    # parent MedicalDocument left that PHI readable in the DB forever. Blank the
    # content but keep the row skeleton so provenance/audit joins still resolve.
    if doc_ids:
        for page in (
            db.execute(select(DocumentPage).where(DocumentPage.document_id.in_(doc_ids)))
            .scalars()
            .all()
        ):
            if page.storage_key:
                orphaned_keys.append(page.storage_key)
            page.ocr_raw = None
            page.blocks_json = None

    # PRIV-F5: extracted candidates hold drug names, doses and diagnoses.
    # `fields_json` is NOT NULL, so it is emptied rather than nulled.
    for candidate in (
        db.execute(
            select(ExtractionCandidate).where(ExtractionCandidate.patient_id == patient_id)
        )
        .scalars()
        .all()
    ):
        candidate.fields_json = {}
        # `corrections_json` is the patient's own correction history (what they
        # retyped over the OCR); `field_confidence_json` is keyed by the same PHI
        # field names. Both go with it.
        candidate.corrections_json = None
        candidate.field_confidence_json = None

    # ── Integration-review P1: four PHI-bearing tables the sweep missed ──────
    #
    # Erasure is asserted complete in the DIST-RC compliance doc, but these four
    # still disclosed which drugs the patient took, at what dose, prescribed by
    # whom, and on what schedule. All are blanked in place (not hard-deleted) so
    # referential integrity and the PHI-free audit trail survive.

    # 1. medication_statements — the raw source assertion behind every medication,
    #    including the full OCR payload snapshot and the prescriber's name.
    for stmt in (
        db.execute(
            select(MedicationStatement).where(MedicationStatement.patient_id == patient_id)
        )
        .scalars()
        .all()
    ):
        stmt.raw_drug_name = ""  # NOT NULL
        stmt.normalized_name = None
        stmt.raw_dose = None
        stmt.raw_frequency = None
        stmt.raw_prescriber = None
        stmt.payload_snapshot = None
        stmt.source_ref = None

    # 2. medication_schedules / dose_occurrences — dosing times, and skip_reason is
    #    patient free text ("Tác dụng phụ — buồn nôn nhiều"). Schedules are stopped
    #    so nothing can keep reminding a deleted account.
    schedule_ids = [
        row[0]
        for row in db.execute(
            select(MedicationSchedule.id).where(MedicationSchedule.patient_id == patient_id)
        ).all()
    ]
    for schedule in (
        db.execute(
            select(MedicationSchedule).where(MedicationSchedule.patient_id == patient_id)
        )
        .scalars()
        .all()
    ):
        schedule.status = "stopped"
        schedule.local_dose_times = None
        schedule.recurrence = None
    if schedule_ids:
        for dose in (
            db.execute(
                select(DoseOccurrence).where(DoseOccurrence.patient_id == patient_id)
            )
            .scalars()
            .all()
        ):
            dose.skip_reason = None
            dose.local_render = None

    # 3. notifications — the reminder body carries the drug name in cleartext
    #    ("Đã đến giờ uống Metformin (500mg)").
    for note in (
        db.execute(select(Notification).where(Notification.user_id == user_id)).scalars().all()
    ):
        note.title = ""
        note.body = ""
        note.metadata_ = None

    # 4. symptom_logs — free-text symptom descriptions.
    for log in (
        db.execute(select(SymptomLog).where(SymptomLog.patient_id == patient_id))
        .scalars()
        .all()
    ):
        log.description = ""
        candidate.field_confidence_json = None
        candidate.corrections_json = None

    # Lab upload binaries (LabDocument holds the raw file object key).
    for lab_doc in (
        db.execute(select(LabDocument).where(LabDocument.patient_id == patient_id)).scalars().all()
    ):
        if lab_doc.storage_key:
            orphaned_keys.append(lab_doc.storage_key)

    # Meto conversations: stamp the still-active parents, then blank the message
    # bodies of *every* conversation the user owns (PRIV-F5). Message content is
    # free-text PHI — symptoms the patient typed, AI answers quoting their labs
    # and medications — and the export bundle deliberately omits it, so leaving
    # it here made it neither exportable nor erasable. Conversation ids are
    # collected across all conversations (not just newly stamped ones) so a
    # re-run also erases anything an earlier partial run left behind.
    conversations = (
        db.execute(select(MetoConversation).where(MetoConversation.user_id == user_id))
        .scalars()
        .all()
    )
    conversation_ids = [conv.id for conv in conversations]
    for conv in conversations:
        if conv.deleted_at is None:
            conv.deleted_at = now
            conv.status = "deleted"

    if conversation_ids:
        for msg in (
            db.execute(
                select(MetoMessage).where(MetoMessage.conversation_id.in_(conversation_ids))
            )
            .scalars()
            .all()
        ):
            msg.content = ""  # NOT NULL column — blank, never null
            msg.tool_calls = None
            msg.tool_results = None

    # ---- Revoke refresh tokens (block existing sessions) ----
    for tok in (
        db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
            )
        )
        .scalars()
        .all()
    ):
        tok.revoked_at = now

    # ---- Revoke Meto consents ----
    for consent in (
        db.execute(select(MetoConsent).where(MetoConsent.user_id == user_id)).scalars().all()
    ):
        consent.granted = False
        consent.revoked_at = now

    # ---- Anonymize PII + disable login (idempotent overwrite) ----
    profile = db.get(PatientProfile, patient_id)
    if profile is not None:
        profile.full_name = None
        profile.dob = None
        profile.phone = None
        profile.address = None
        profile.known_conditions = None
        profile.allergies = None
        profile.family_history = None
        profile.lifestyle_profile = None

    user = db.get(User, user_id)
    if user is not None:
        user.email = f"deleted-user-{user.id}@deleted.invalid"
        user.phone = None
        user.full_name = None
        user.is_active = False

    return sorted(set(orphaned_keys))


# ---------------------------------------------------------------------------
# Serialization helpers — plain dicts (jsonable_encoder handles date/datetime).
# ---------------------------------------------------------------------------


def _profile_dict(user: User | None, profile: PatientProfile | None) -> dict:
    return {
        "full_name": profile.full_name if profile else None,
        "dob": profile.dob if profile else None,
        "phone": (profile.phone if profile else None) or (user.phone if user else None),
        "email": user.email if user else None,
        "gender": profile.gender if profile else None,
        "height_cm": profile.height_cm if profile else None,
        "weight_kg": profile.weight_kg if profile else None,
        "waist_cm": profile.waist_cm if profile else None,
        "address": profile.address if profile else None,
        "known_conditions": profile.known_conditions if profile else None,
        "allergies": profile.allergies if profile else None,
        "family_history": profile.family_history if profile else None,
        "risk_segment": profile.risk_segment if profile else None,
    }


def _metric_dict(m: HealthMetric) -> dict:
    return {
        "id": m.id,
        "metric_type": m.metric_type,
        "value": m.original_value if m.original_value is not None else m.value,
        "unit": m.original_unit or m.unit,
        "measured_at": m.measured_at,
        "source": m.source,
        "status": m.status,
    }


def _lab_result_dict(r: LabResult) -> dict:
    return {
        "id": r.id,
        "batch_id": r.batch_id,
        "test_name": r.original_test_name or r.test_name,
        "value": r.original_value if r.original_value is not None else r.value,
        "unit": r.original_unit or r.unit,
        "reference_range": r.original_reference_range or r.reference_range,
        "status": r.status,
        "test_date": r.test_date,
    }


def _lab_batch_dict(b: LabUploadBatch) -> dict:
    return {
        "id": b.id,
        "lab_name": b.lab_name,
        "test_date": b.test_date,
        "created_at": b.created_at,
    }


def _medication_dict(m: Medication) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "dose": m.dose,
        "frequency": m.frequency,
        "note": m.note,
        "lifecycle_status": m.lifecycle_status,
        "created_at": m.created_at,
    }


def _consent_dict(c: MetoConsent) -> dict:
    return {
        "context_type": c.context_type,
        "granted": c.granted,
        "granted_at": c.granted_at,
        "revoked_at": c.revoked_at,
    }


def _conversation_dict(c: MetoConversation) -> dict:
    # Metadata only — message content is intentionally excluded.
    return {
        "id": c.id,
        "title": c.title,
        "status": c.status,
        "message_count": c.message_count,
        "created_at": c.created_at,
        "last_active_at": c.last_active_at,
    }


def _consultation_dict(c: Consultation) -> dict:
    return {
        "id": c.id,
        "doctor_id": c.doctor_id,
        "consultation_type": c.consultation_type,
        "status": c.status,
        "consultation_price": c.consultation_price,
        "chief_complaint": c.chief_complaint,
        "created_at": c.created_at,
        "completed_at": c.completed_at,
    }


def _document_dict(d: MedicalDocument) -> dict:
    # Metadata only — storage keys / binaries are internal, never exported.
    return {
        "id": d.id,
        "doc_type": d.doc_type,
        "status": d.status,
        "mime": d.mime,
        "size_bytes": d.size_bytes,
        "page_count": d.page_count,
        "created_at": d.created_at,
    }
