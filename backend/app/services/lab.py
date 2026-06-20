"""Lab service — register a lab document, run (mock) OCR, interpret results.

OCR runs in mock mode by default (config MCP_OCR_MODE) so dev/test never call a
real provider. Interpretation delegates to the pure-python domain interpreter.
Access is consent-gated + audited.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain import lab_interpreter
from app.models.clinical import LabDocument, LabResult
from app.services import audit, consent


def register_document(
    db: Session,
    *,
    patient_id: str,
    requester_id: str,
    storage_key: str,
    file_type: str | None = None,
    lab_name: str | None = None,
) -> LabDocument:
    consent.require_access(db, patient_id=patient_id, requester_id=requester_id, scope="lab")
    doc = LabDocument(
        patient_id=patient_id,
        storage_key=storage_key,
        file_type=file_type,
        lab_name=lab_name,
        ocr_status="pending",
    )
    db.add(doc)
    db.flush()
    audit.record(
        db,
        actor_type="user",
        actor_id=requester_id,
        action="upload",
        resource_type="lab_document",
        resource_id=doc.id,
    )
    db.commit()
    return doc


def _extract(document: LabDocument) -> list[lab_interpreter.RawLabValue]:
    settings = get_settings()
    if settings.ocr_mode == "mock":
        return lab_interpreter.mock_ocr_extract(document.storage_key)
    # Real provider integration is a P1 worker job; never called in dev/test.
    raise NotImplementedError(
        "Real OCR provider not configured. Set MCP_OCR_MODE=mock for dev/test."
    )


def interpret_document(
    db: Session,
    *,
    document_id: str,
    requester_id: str,
) -> lab_interpreter.LabInterpretation:
    doc = db.get(LabDocument, document_id)
    if doc is None:
        raise ValueError("lab document not found")
    consent.require_access(db, patient_id=doc.patient_id, requester_id=requester_id, scope="lab")

    raw_values = _extract(doc)
    interpretation = lab_interpreter.interpret_panel(raw_values)

    # Persist normalized results.
    for b in interpretation.biomarkers:
        db.add(
            LabResult(
                patient_id=doc.patient_id,
                document_id=doc.id,
                test_name=b.raw_name,
                canonical_name=b.canonical,
                value=b.value,
                unit=b.unit,
                reference_range=b.reference_range,
                status=b.status.value,
                ocr_confidence=b.ocr_confidence,
            )
        )
    doc.ocr_status = "done"
    db.flush()
    audit.record(
        db,
        actor_type="user",
        actor_id=requester_id,
        action="interpret",
        resource_type="lab_document",
        resource_id=doc.id,
    )
    db.commit()
    return interpretation


def create_manual_entry(
    db: Session,
    *,
    patient_id: str,
    requester_id: str,
    lab_name: str | None,
    test_date,
    results: list[dict],
) -> tuple[LabDocument, list[LabResult]]:
    """Create a lab document + structured results from manual patient entry (PR-B).

    No OCR/file involved — the patient types the values. The document is marked
    ``status='manual'`` / ``ocr_status='done'`` and each result is flagged
    ``verified_by_user=True``. Consent-gated + audited, same as upload.
    """
    consent.require_access(db, patient_id=patient_id, requester_id=requester_id, scope="lab")

    doc = LabDocument(
        patient_id=patient_id,
        storage_key=f"manual:{patient_id}",
        file_type="manual",
        lab_name=lab_name,
        ocr_status="done",
        status="manual",
    )
    db.add(doc)
    db.flush()

    rows: list[LabResult] = []
    for item in results:
        row = LabResult(
            patient_id=patient_id,
            document_id=doc.id,
            test_name=item["test_name"],
            value=item.get("value"),
            unit=item.get("unit"),
            reference_range=item.get("reference_range"),
            test_date=test_date,
            verified_by_user=True,
        )
        db.add(row)
        rows.append(row)
    db.flush()

    audit.record(
        db,
        actor_type="user",
        actor_id=requester_id,
        action="manual_lab_entry",
        resource_type="lab_document",
        resource_id=doc.id,
    )
    db.commit()
    for row in rows:
        db.refresh(row)
    return doc, rows


def list_lab_results(
    db: Session,
    *,
    patient_id: str,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[LabResult]]:
    """Return (total, items) of the patient's lab results (newest first)."""
    from sqlalchemy import func, select

    limit = min(limit, 100)
    base = (
        LabResult.patient_id == patient_id,
        LabResult.deleted_at.is_(None),
    )
    total = db.execute(
        select(func.count()).select_from(LabResult).where(*base)
    ).scalar_one()
    rows = list(
        db.execute(
            select(LabResult)
            .where(*base)
            .order_by(LabResult.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )
    return total, rows
