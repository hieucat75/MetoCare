"""Lab service — register a lab document, run (mock) OCR, interpret results.

OCR runs in mock mode by default (config MCP_OCR_MODE) so dev/test never call a
real provider. Interpretation delegates to the pure-python domain interpreter.
Access is consent-gated + audited.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import as_naive_utc, utcnow
from app.core.config import get_settings
from app.domain import lab_interpreter
from app.domain.lab_normalization import normalize_value_to_si
from app.models.clinical import HealthMetric, LabDocument, LabResult
from app.services import audit, consent, lab_batch
from app.services import ocr_case as ocr_case_svc
from app.services.health_metrics import classify_status

# Lab biomarkers that double as trackable health metrics. Promoting them into
# `health_metrics` (source='lab_result') makes the dashboard tiles + trend charts
# update the moment a patient confirms lab results — the canonical key is shared,
# so the mapping is identity (any recognised biomarker is promotable).
_PROMOTABLE = {spec.canonical for spec in lab_interpreter.BIOMARKERS}


def _measured_at_for(row: LabResult, test_date: dt.date | None) -> dt.datetime:
    """When the metric was 'measured' = the exam date (test_date), else the row's
    own test_date, else its insert time — NEVER 'now', so trends stay chronological."""
    d = test_date or row.test_date
    if d is not None:
        return as_naive_utc(dt.datetime.combine(d, dt.time()))
    return as_naive_utc(getattr(row, "created_at", None)) or utcnow()


def _promote_row(db: Session, row: LabResult, measured_at: dt.datetime) -> bool:
    """Promote a single lab row into a health_metric (idempotent per row). Returns
    True if a metric was written.

    Defence-in-depth: rows where verified_by_user is explicitly False are NEVER
    promoted, even if called directly. This guard is the last line of defence;
    the primary filter is in lab_pipeline.promote_gate (verified_rows list).
    """
    if row.verified_by_user is False:
        import logging as _logging
        _logging.getLogger("mcp.lab").warning(
            "_promote_row_blocked_unverified lab_result_id=%s canonical=%s — "
            "unverified OCR row must not reach patient metrics",
            row.id, row.canonical_name,
        )
        return False
    canonical = row.canonical_name or lab_interpreter.normalize_biomarker(row.test_name)
    if not canonical or canonical not in _PROMOTABLE or row.value is None:
        return False
    # Idempotent: drop any prior promotion of this exact lab row first (ORM-level
    # delete so a freshly-added-but-uncommitted metric is removed too).
    for prior in db.execute(
        select(HealthMetric).where(HealthMetric.source_ref == row.id)
    ).scalars():
        db.delete(prior)
    db.flush()
    spec = lab_interpreter._ALIAS_INDEX.get(canonical)
    nmin = spec.ref_low if spec else None
    nmax = spec.ref_high if spec else None
    db.add(
        HealthMetric(
            patient_id=row.patient_id,
            metric_type=canonical,
            value=row.value,
            unit=row.unit,
            measured_at=measured_at,
            source="lab_result",
            source_ref=row.id,
            normal_range_min=nmin,
            normal_range_max=nmax,
            status=classify_status(canonical, row.value, nmin, nmax),
        )
    )
    db.flush()  # session is autoflush=False — make the row visible to the next lookup
    return True


def promote_lab_rows_to_metrics(
    db: Session,
    *,
    patient_id: str,
    rows: list[LabResult],
    test_date: dt.date | None,
) -> int:
    """Promote confirmed lab rows into health_metrics so the dashboard + trends
    update. Idempotent per row; measured at the exam date. Returns count written."""
    return sum(_promote_row(db, row, _measured_at_for(row, test_date)) for row in rows)


def backfill_lab_metrics(db: Session, *, commit: bool = True) -> int:
    """One-time backfill: promote every lab_result that has no health_metric yet.

    Fixes labs created before lab→metric sync existed (and via the interpret/
    pipeline paths). Idempotent — rows already promoted (a health_metric points at
    them via source_ref) are skipped, so re-running is safe. Returns count written."""
    from sqlalchemy.orm import load_only as _load_only

    promoted_refs = select(HealthMetric.source_ref).where(HealthMetric.source_ref.is_not(None))
    # load_only avoids selecting columns added after this backfill migration ran
    # (e.g. original_value/unit/reference_range/test_name) so this function is safe
    # to call from the hmbk_backfill migration even on DBs that don't have them yet.
    orphans = db.execute(
        select(LabResult)
        .where(
            LabResult.deleted_at.is_(None),
            LabResult.value.is_not(None),
            LabResult.id.not_in(promoted_refs),
        )
        .options(_load_only(
            LabResult.id,
            LabResult.patient_id,
            LabResult.canonical_name,
            LabResult.test_name,
            LabResult.value,
            LabResult.unit,
            LabResult.test_date,
            LabResult.created_at,
        ))
    ).scalars().all()
    written = sum(_promote_row(db, row, _measured_at_for(row, None)) for row in orphans)
    if commit:
        db.commit()
    return written


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
    # Track whether extraction came from mock (deterministic, always trusted) or
    # real OCR (image scan, must pass confidence + verification gate).
    is_mock_path = getattr(doc, "storage_key", "").startswith("manual:") or (
        get_settings().ocr_mode == "mock"
    )
    interpretation = lab_interpreter.interpret_panel(raw_values)

    # Persist normalized results.
    new_rows: list[LabResult] = []
    for b in interpretation.biomarkers:
        # verified_by_user gate mirrors lab_pipeline: mock/manual rows are trusted;
        # real OCR rows require confidence >= 0.5 and no needs_verification flag.
        raw = next((v for v in raw_values if hasattr(v, "test_name") and v.test_name == b.raw_name), None)  # noqa: E501
        suspect = getattr(raw, "suspect_machine_id", False) if raw else False
        requires_review = getattr(raw, "requires_review", False) if raw else False
        auto_save_blocked = (
            not is_mock_path and (
                suspect
                or requires_review
                or b.ocr_confidence < 0.5
                or b.needs_verification
            )
        )
        lr = LabResult(
            patient_id=doc.patient_id,
            document_id=doc.id,
            test_name=b.raw_name,
            canonical_name=b.canonical,
            value=b.value,
            unit=b.unit,
            reference_range=b.reference_range,
            status=b.status.value,
            ocr_confidence=b.ocr_confidence,
            verified_by_user=not auto_save_blocked,
        )
        db.add(lr)
        new_rows.append(lr)
    doc.ocr_status = "done"
    db.flush()
    # Promote into health_metrics — only verified rows reach patient metrics.
    verified_rows = [r for r in new_rows if r.verified_by_user]
    promote_lab_rows_to_metrics(db, patient_id=doc.patient_id, rows=verified_rows, test_date=None)

    # Record OCR pipeline metrics (internal telemetry).
    from app.domain import hospital_profiles as _hp
    from app.services import ocr_metrics as _ocr_metrics

    _bm = interpretation.biomarkers
    _prof = _hp.detect_hospital(getattr(doc, "raw_text", "") or "")
    _ocr_metrics.get_metrics().record_upload(
        hospital_id=_prof.hospital_id if _prof else None,
        biomarkers_found=len(_bm),
        unknown_biomarkers=sum(1 for b in _bm if b.canonical == "unknown"),
        avg_confidence=sum(b.ocr_confidence for b in _bm) / max(len(_bm), 1),
        success=True,
    )

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
    force_mode: str | None = None,
    existing_batch_id: str | None = None,
    file_hash: str | None = None,
    ocr_case_id: str | None = None,
    review_time_seconds: float | None = None,
) -> tuple[LabDocument, list[LabResult]]:
    """Create a lab document + structured results from manual patient entry (PR-B).

    No OCR/file involved — the patient types the values. The document is marked
    ``status='manual'`` / ``ocr_status='done'`` and each result is flagged
    ``verified_by_user=True``. Consent-gated + audited, same as upload.

    force_mode="overwrite": soft-delete the existing_batch_id before saving.
    force_mode="new" or None: save alongside any existing batch.
    """
    consent.require_access(db, patient_id=patient_id, requester_id=requester_id, scope="lab")

    # Overwrite: cascade-delete the existing batch before creating the new one.
    if force_mode == "overwrite" and existing_batch_id:
        lab_batch.delete_batch(
            db,
            batch_id=existing_batch_id,
            deleted_by_user_id=requester_id,
            reason="overwritten by new upload",
            patient_id=patient_id,
        )

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

    # Create the batch that groups these results into one logical upload session.
    batch = lab_batch.create_batch(
        db,
        patient_id=patient_id,
        source_document_id=doc.id,
        lab_name=lab_name,
        test_date=test_date,
        file_hash=file_hash,
    )

    rows: list[LabResult] = []
    for item in results:
        # Resolve the canonical biomarker so the row is self-describing and can be
        # promoted into health_metrics (dashboard/trend sync).
        canonical = lab_interpreter.normalize_biomarker(item["test_name"])

        # P0 safety: normalize value to canonical unit (e.g. mmol/L → mg/dL for glucose)
        # before storing. Clinical rules always run in canonical units (mg/dL, etc.).
        # Keep original value/unit for display (already in original_value/original_unit).
        raw_value = item.get("value")
        raw_unit = item.get("unit") or ""
        if canonical and raw_value is not None:
            canonical_value, canonical_unit_str = normalize_value_to_si(
                raw_value, raw_unit, canonical
            )
        else:
            canonical_value = raw_value
            canonical_unit_str = raw_unit

        row = LabResult(
            patient_id=patient_id,
            document_id=doc.id,
            batch_id=batch.id,
            test_name=item["test_name"],
            canonical_name=canonical,
            value=canonical_value,
            unit=canonical_unit_str,
            reference_range=item.get("reference_range"),
            test_date=test_date,
            verified_by_user=True,
            original_value=item.get("original_value") if item.get("original_value") is not None else raw_value,  # noqa: E501
            original_unit=item.get("original_unit") if item.get("original_unit") is not None else raw_unit,  # noqa: E501
            original_reference_range=item.get("original_reference_range"),
            original_test_name=item.get("original_test_name"),
        )
        db.add(row)
        rows.append(row)
    db.flush()

    # Promote overlapping biomarkers into health_metrics so the dashboard + trend
    # charts reflect the new values immediately (measured at the exam date).
    promote_lab_rows_to_metrics(db, patient_id=patient_id, rows=rows, test_date=test_date)

    audit.record(
        db,
        actor_type="user",
        actor_id=requester_id,
        action="manual_lab_entry",
        resource_type="lab_document",
        resource_id=doc.id,
    )

    # Close the OCR feedback loop — non-blocking; must never abort the save transaction.
    if ocr_case_id:
        try:
            corrected_rows = [
                {
                    "test_name": r.get("test_name", ""),
                    "original_test_name": r.get("original_test_name") or r.get("test_name", ""),
                    "display_name_vi": r.get("display_name_vi") or "",
                    # Use the resolved canonical key so gap matching works correctly.
                    "mapped_metric_type": lab_interpreter.normalize_biomarker(
                        r.get("test_name", "")
                    ),
                    "value": r.get("value"),
                    "unit": r.get("unit") or "",
                }
                for r in results
            ]
            test_date_iso = (
                test_date.isoformat() if hasattr(test_date, "isoformat") else str(test_date)
            )
            ocr_case_svc.confirm_case(
                db,
                case_id=ocr_case_id,
                patient_id=patient_id,
                lab_batch_id=batch.id,
                corrected_rows=corrected_rows,
                test_date_iso=test_date_iso,
                user_review_time_seconds=review_time_seconds,
            )
        except Exception:
            import logging as _log
            _log.getLogger("mcp.lab").exception(
                "ocr_case_confirm_failed case=%s patient=%s — lab save NOT rolled back",
                ocr_case_id, patient_id,
            )

    db.commit()
    for row in rows:
        db.refresh(row)
    return doc, rows


def get_results_by_batch(
    db: Session,
    *,
    batch_id: str,
    patient_id: str,
) -> list[LabResult]:
    """Return all non-deleted LabResult rows belonging to *batch_id*.

    Ownership check is the caller's responsibility (pass the authenticated
    patient_id so the query implicitly enforces it — a batch owned by another
    patient will simply return []).
    """
    from sqlalchemy import select
    from app.models.clinical import LabUploadBatch

    # Verify the batch exists and belongs to the correct patient.
    batch = db.execute(
        select(LabUploadBatch).where(
            LabUploadBatch.id == batch_id,
            LabUploadBatch.patient_id == patient_id,
            LabUploadBatch.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if batch is None:
        return None  # sentinel: caller raises 404

    rows = list(
        db.execute(
            select(LabResult)
            .where(
                LabResult.batch_id == batch_id,
                LabResult.patient_id == patient_id,
                LabResult.deleted_at.is_(None),
            )
            .order_by(
                LabResult.test_date.is_(None),
                LabResult.test_date.desc(),
                LabResult.created_at.asc(),
            )
        ).scalars()
    )
    return rows


def list_lab_results(
    db: Session,
    *,
    patient_id: str,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[LabResult]]:
    """Return (total, items) of the patient's lab results, newest *exam date* first.

    Ordered by ``test_date`` DESC (the real exam date) so history/trends are
    chronological even when an old report is uploaded later. Rows without a
    test_date (legacy) sort last; ``created_at`` breaks ties."""
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
            # test_date IS NULL -> 1 (sorts after non-null 0); then newest date,
            # then newest insert. Portable across SQLite + Postgres.
            .order_by(
                LabResult.test_date.is_(None),
                LabResult.test_date.desc(),
                LabResult.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        ).scalars()
    )
    return total, rows
