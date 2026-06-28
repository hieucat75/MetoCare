"""Lab upload batch service.

Handles batch creation, duplicate detection, and cascading soft-delete:
  batch -> lab_results -> health_metrics (via source_ref).

Rules enforced here:
- Never hard-delete medical data.
- Patients may only delete their own batches (caller must verify patient_id).
- delete_batch() is idempotent: already-deleted batches return silently.
- Duplicate detection: same test_date + overlapping canonicals >=50%, or
  same test_date + same lab_name, or exact file_hash match.
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.clinical import HealthMetric, LabResult, LabUploadBatch
from app.services import audit

_logger = logging.getLogger("mcp.lab_batch")

_OVERLAP_THRESHOLD = 0.5  # >=50% shared canonicals = duplicate


# -- Batch creation ----------------------------------------------------------


def create_batch(
    db: Session,
    *,
    patient_id: str,
    source_document_id: str | None,
    lab_name: str | None,
    test_date: dt.date | None,
    file_hash: str | None = None,
) -> LabUploadBatch:
    """Create and flush a new LabUploadBatch. Caller must commit."""
    batch = LabUploadBatch(
        patient_id=patient_id,
        source_document_id=source_document_id,
        lab_name=lab_name,
        test_date=test_date,
        file_hash=file_hash,
    )
    db.add(batch)
    db.flush()
    _logger.debug(
        "lab_batch_created batch_id=%s patient=%s date=%s", batch.id, patient_id, test_date
    )
    return batch


# -- Duplicate detection -----------------------------------------------------


def check_duplicate(
    db: Session,
    *,
    patient_id: str,
    test_date: dt.date,
    lab_name: str | None = None,
    biomarker_names: list[str] | None = None,
    file_hash: str | None = None,
) -> tuple[bool, str | None, str | None]:
    """Return (is_duplicate, existing_batch_id, reason).

    Priority order:
    1. Exact file_hash match (if provided).
    2. Same test_date + same lab_name (case-insensitive containment).
    3. Same test_date + >=50% overlapping canonical biomarker names.
    """
    base_filter = (
        LabUploadBatch.patient_id == patient_id,
        LabUploadBatch.deleted_at.is_(None),
        LabUploadBatch.test_date == test_date,
    )

    # 1. Exact hash
    if file_hash:
        row = (
            db.execute(
                select(LabUploadBatch).where(
                    *base_filter,
                    LabUploadBatch.file_hash == file_hash,
                )
            )
            .scalars()
            .first()
        )
        if row:
            _logger.info("lab_batch_duplicate_hash batch=%s patient=%s", row.id, patient_id)
            return True, row.id, "exact_hash"

    # 2. Same test_date + lab_name
    if lab_name:
        ln = lab_name.strip().lower()
        candidates = db.execute(select(LabUploadBatch).where(*base_filter)).scalars().all()
        for c in candidates:
            if c.lab_name and ln in c.lab_name.lower():
                _logger.info("lab_batch_duplicate_name batch=%s patient=%s", c.id, patient_id)
                return True, c.id, "same_date_lab"

    # 3. Overlapping biomarkers
    if biomarker_names:
        incoming = {n.strip().lower() for n in biomarker_names if n}
        if incoming:
            candidates = db.execute(select(LabUploadBatch).where(*base_filter)).scalars().all()
            for c in candidates:
                existing_canonicals = set(
                    db.execute(
                        select(LabResult.canonical_name).where(
                            LabResult.batch_id == c.id,
                            LabResult.deleted_at.is_(None),
                            LabResult.canonical_name.is_not(None),
                        )
                    )
                    .scalars()
                    .all()
                )
                if not existing_canonicals:
                    continue
                overlap = incoming & {n.lower() for n in existing_canonicals}
                ratio = len(overlap) / max(len(incoming), len(existing_canonicals))
                if ratio >= _OVERLAP_THRESHOLD:
                    _logger.info(
                        "lab_batch_duplicate_overlap batch=%s ratio=%.2f patient=%s",
                        c.id,
                        ratio,
                        patient_id,
                    )
                    return True, c.id, "overlapping_biomarkers"

    return False, None, None


# -- Batch delete (cascade soft-delete) -------------------------------------


def delete_batch(
    db: Session,
    *,
    batch_id: str,
    deleted_by_user_id: str,
    reason: str | None = None,
    patient_id: str,
) -> None:
    """Soft-delete a batch, its lab_results, and their promoted health_metrics.

    Idempotent: if the batch is already deleted, returns immediately.
    Raises ValueError if batch does not exist.
    Raises PermissionError if batch does not belong to patient_id.
    Audit-logs the deletion.
    """
    batch = db.get(LabUploadBatch, batch_id)
    if batch is None:
        raise ValueError(f"Batch {batch_id} not found.")
    if batch.patient_id != patient_id:
        raise PermissionError(f"Batch {batch_id} does not belong to patient {patient_id}.")
    if batch.deleted_at is not None:
        _logger.debug("lab_batch_delete_idempotent batch_id=%s", batch_id)
        return  # already deleted -- idempotent

    now = dt.datetime.utcnow()

    # Collect live lab_results in this batch.
    live_results = (
        db.execute(
            select(LabResult).where(
                LabResult.batch_id == batch_id,
                LabResult.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )

    result_ids = [r.id for r in live_results]

    # Soft-delete health_metrics promoted from these results (via source_ref).
    if result_ids:
        metrics = (
            db.execute(
                select(HealthMetric).where(
                    HealthMetric.source_ref.in_(result_ids),
                    HealthMetric.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        for m in metrics:
            m.deleted_at = now
            m.deleted_by = deleted_by_user_id
        _logger.info("lab_batch_delete_metrics count=%d batch_id=%s", len(metrics), batch_id)

    # Soft-delete lab_results.
    for r in live_results:
        r.deleted_at = now
        r.deleted_by = deleted_by_user_id
    _logger.info("lab_batch_delete_results count=%d batch_id=%s", len(live_results), batch_id)

    # Soft-delete the batch itself.
    batch.deleted_at = now
    batch.deleted_by = deleted_by_user_id
    batch.delete_reason = reason

    audit.record(
        db,
        actor_type="user",
        actor_id=deleted_by_user_id,
        action="delete_lab_batch",
        resource_type="lab_upload_batch",
        resource_id=batch_id,
    )
    db.commit()
    _logger.info("lab_batch_deleted batch_id=%s by=%s", batch_id, deleted_by_user_id)


# -- Batch list --------------------------------------------------------------


def list_batches(
    db: Session,
    *,
    patient_id: str,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[dict]]:
    """Return (total, items) of non-deleted batches, newest test_date first.

    Each item dict includes a result_count of live lab_results in the batch.
    """
    limit = min(limit, 100)
    base = (
        LabUploadBatch.patient_id == patient_id,
        LabUploadBatch.deleted_at.is_(None),
    )
    total = db.execute(select(func.count()).select_from(LabUploadBatch).where(*base)).scalar_one()

    batches = (
        db.execute(
            select(LabUploadBatch)
            .where(*base)
            .order_by(
                LabUploadBatch.test_date.is_(None),
                LabUploadBatch.test_date.desc(),
                LabUploadBatch.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    items = []
    for b in batches:
        count = db.execute(
            select(func.count())
            .select_from(LabResult)
            .where(
                LabResult.batch_id == b.id,
                LabResult.deleted_at.is_(None),
            )
        ).scalar_one()
        items.append(
            {
                "id": b.id,
                "patient_id": b.patient_id,
                "lab_name": b.lab_name,
                "test_date": b.test_date,
                "result_count": count,
                "created_at": b.created_at,
            }
        )
    return total, items
