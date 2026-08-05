"""Lab service — register a lab document, run (mock) OCR, interpret results.

OCR runs in mock mode by default (config MCP_OCR_MODE) so dev/test never call a
real provider. Interpretation delegates to the pure-python domain interpreter.
Access is consent-gated + audited.
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.orm import Session

from app.core.clock import as_naive_utc, utcnow
from app.core.config import get_settings
from app.domain import lab_interpreter
from app.domain.lab_interpreter import classify_value
from app.domain.lab_normalization import normalize_value_to_si
from app.models.clinical import HealthMetric, LabDocument, LabResult, LabUploadBatch
from app.services import audit, consent, lab_batch
from app.services import ocr_case as ocr_case_svc
from app.services.biomarker_specs import check_plausibility
from app.services.health_metrics import classify_status

_log = logging.getLogger("mcp.lab")

# Lab biomarkers that double as trackable health metrics. Promoting them into
# `health_metrics` (source='lab_result') makes the dashboard tiles + trend charts
# update the moment a patient confirms lab results — the canonical key is shared,
# so the mapping is identity (any recognised biomarker is promotable).
_PROMOTABLE = {spec.canonical for spec in lab_interpreter.BIOMARKERS}


# ─── Canonical clinical messages (Vietnamese) ─────────────────────────────────
# Keyed by (canonical_name, status). Provides a single source of truth for
# patient-facing clinical messages — used in LabResultOut.clinical_message and
# as the banner text in the frontend (no hardcoded message maps allowed in UI).

_CLINICAL_MESSAGES: dict[tuple[str, str], str] = {
    # fasting_glucose (internal: mg/dL)
    ("fasting_glucose", "critical"): "Đường huyết ở mức nguy hiểm — cần bác sĩ đánh giá ngay",
    ("fasting_glucose", "low"): "Đường huyết thấp — cần theo dõi và trao đổi với bác sĩ",
    ("fasting_glucose", "normal"): "Đường huyết bình thường",
    ("fasting_glucose", "high"): "Đường huyết cao — nên tư vấn bác sĩ",
    # postprandial_glucose
    ("postprandial_glucose", "critical"): "Đường huyết sau ăn nguy hiểm — cần bác sĩ đánh giá ngay",
    ("postprandial_glucose", "low"): "Đường huyết sau ăn thấp — cần theo dõi",
    ("postprandial_glucose", "normal"): "Đường huyết sau ăn bình thường",
    ("postprandial_glucose", "high"): "Đường huyết sau ăn cao — nên tư vấn bác sĩ",
    # hba1c
    ("hba1c", "critical"): "HbA1c rất cao — cần bác sĩ xem xét sớm",
    ("hba1c", "low"): "HbA1c thấp",
    ("hba1c", "normal"): "HbA1c bình thường",
    ("hba1c", "high"): "HbA1c cao — nguy cơ tiểu đường, cần theo dõi",
}

_CLINICAL_MESSAGE_DEFAULT: dict[str, str] = {
    "critical": "Chỉ số ở mức nguy hiểm — cần bác sĩ đánh giá ngay",
    "low": "Chỉ số thấp hơn tham chiếu — nên trao đổi với bác sĩ",
    "normal": "Chỉ số trong khoảng bình thường",
    "high": "Chỉ số cao hơn tham chiếu — nên tư vấn bác sĩ",
}


def get_clinical_message(canonical_name: str | None, status: str | None) -> str | None:
    """Return the canonical Vietnamese clinical message for a given biomarker status.

    This is the SINGLE SOURCE OF TRUTH for all clinical messaging in the app.
    Frontend must NOT maintain its own status-to-message mapping.
    """
    if not canonical_name or not status:
        return None
    key = (canonical_name, status)
    if key in _CLINICAL_MESSAGES:
        return _CLINICAL_MESSAGES[key]
    # Fall back to generic status message.
    return _CLINICAL_MESSAGE_DEFAULT.get(status)


def normalize_and_classify(canonical_name: str | None, value, unit: str) -> dict:
    """Normalize a raw lab value + unit to canonical unit and classify it.

    Given a canonical biomarker name, a raw value, and a unit:
    1. Normalize to canonical unit (e.g. mmol/L -> mg/dL for glucose).
    2. Classify using lab_interpreter.classify_value().
    3. Return dict with: normalized_value_si, normalized_unit_si, status, clinical_message.

    Returns empty dict if canonical_name is None or value is None.
    Returns dict with status=None if biomarker is unsupported.
    """
    if not canonical_name or value is None:
        return {}

    # Normalize to canonical ("SI") unit.
    try:
        norm_value, norm_unit = normalize_value_to_si(float(value), unit or "", canonical_name)
    except (TypeError, ValueError):
        return {}

    # Classify.
    status_enum = classify_value(canonical_name, norm_value)
    if status_enum is None or status_enum.value == "unknown":
        # Unsupported biomarker -- return normalized fields but no status.
        return {
            "normalized_value_si": norm_value,
            "normalized_unit_si": norm_unit,
            "status": None,
            "clinical_message": None,
        }

    status = status_enum.value
    return {
        "normalized_value_si": norm_value,
        "normalized_unit_si": norm_unit,
        "status": status,
        "clinical_message": get_clinical_message(canonical_name, status),
    }


def validate_before_save(
    biomarker_name: str,
    original_value: float,
    original_unit: str,
    normalized_value_si: float | None,
    normalized_unit_si: str | None,
) -> dict:
    """Write-time integrity check. Called BEFORE DB save.

    Returns:
        {
          "valid":     bool,             # always True — we never silently reject
          "suspicious": bool,
          "reason":    str,
          "action":    "save" | "flag",  # "flag" means save + mark suspicious
        }

    Rules:
    - NEVER reject a record; only flag for human review.
    - Flag when original value/unit is physiologically implausible.
    - Flag when normalized value is physiologically implausible.
    - A biomarker with no spec entry is assumed plausible (unknown == not checked).
    """
    # 1. Plausibility check on original value/unit.
    plaus = check_plausibility(biomarker_name, original_value, original_unit)

    if not plaus["plausible"]:
        return {
            "valid": True,  # save regardless — never silently discard data
            "suspicious": True,
            "reason": plaus["reason"],
            "action": "flag",
        }

    # 2. Plausibility check on normalized value (if present).
    if normalized_value_si is not None and normalized_unit_si is not None:
        norm_plaus = check_plausibility(biomarker_name, normalized_value_si, normalized_unit_si)
        if not norm_plaus["plausible"]:
            return {
                "valid": True,
                "suspicious": True,
                "reason": f"Normalized value implausible: {norm_plaus['reason']}",
                "action": "flag",
            }

    return {"valid": True, "suspicious": False, "reason": "OK", "action": "save"}


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
            row.id,
            row.canonical_name,
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

    # P0 FIX: always promote in CANONICAL units (e.g. mg/dL for glucose), not SI/display.
    # row.value/unit may be the original as-printed unit (e.g. mmol/L from OCR path).
    # Prefer normalized_value_si/normalized_unit_si when available; else normalize now.
    # Use isinstance guard so MagicMock in tests doesn't bypass normalization.
    raw_norm_si = getattr(row, "normalized_value_si", None)
    raw_norm_unit = getattr(row, "normalized_unit_si", None)
    if isinstance(raw_norm_si, (int, float)) and isinstance(raw_norm_unit, str):
        promote_value = float(raw_norm_si)
        promote_unit = raw_norm_unit
    else:
        # Normalize on-the-fly (handles OCR rows without pre-normalized fields).
        promote_value, promote_unit = normalize_value_to_si(
            float(row.value), row.unit or "", canonical
        )

    db.add(
        HealthMetric(
            patient_id=row.patient_id,
            metric_type=canonical,
            value=promote_value,
            unit=promote_unit,
            # P0 clinical-integrity: preserve the ORIGINAL value+unit as printed on
            # the lab report (e.g. 88 µmol/L) for every user/AI-facing surface.
            # value/unit above stay CANONICAL for internal classification + trends.
            original_value=(
                row.original_value if row.original_value is not None else float(row.value)
            ),
            original_unit=row.original_unit or row.unit,
            measured_at=measured_at,
            source="lab_result",
            source_ref=row.id,
            normal_range_min=nmin,
            normal_range_max=nmax,
            # Use classify_value (knows critical_high/critical_low thresholds)
            # instead of classify_status (only uses RED_FLAG_VITAL_THRESHOLDS + ref range).
            # This ensures HealthMetric critical severity matches LabResult classification.
            status=(
                classify_value(canonical, promote_value).value
                if classify_value(canonical, promote_value) is not None
                else classify_status(canonical, promote_value, nmin, nmax)
            ),
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
    orphans = (
        db.execute(
            select(LabResult)
            .where(
                LabResult.deleted_at.is_(None),
                LabResult.value.is_not(None),
                LabResult.id.not_in(promoted_refs),
            )
            .options(
                _load_only(
                    LabResult.id,
                    LabResult.patient_id,
                    LabResult.canonical_name,
                    LabResult.test_name,
                    LabResult.value,
                    LabResult.unit,
                    LabResult.test_date,
                    LabResult.created_at,
                )
            )
        )
        .scalars()
        .all()
    )
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
        raw = next(
            (v for v in raw_values if hasattr(v, "test_name") and v.test_name == b.raw_name), None
        )  # noqa: E501
        suspect = getattr(raw, "suspect_machine_id", False) if raw else False
        requires_review = getattr(raw, "requires_review", False) if raw else False
        auto_save_blocked = not is_mock_path and (
            suspect or requires_review or b.ocr_confidence < 0.5 or b.needs_verification
        )
        # Auto-classify + normalize at creation time.
        _clf = normalize_and_classify(b.canonical, b.value, b.unit or "")
        _status = _clf.get("status") if _clf else None
        # Fallback to interpreter status only if canonical classification succeeds.
        if _status is None and b.status.value not in ("unknown",):
            _status = b.status.value

        lr = LabResult(
            patient_id=doc.patient_id,
            document_id=doc.id,
            test_name=b.raw_name,
            canonical_name=b.canonical,
            value=b.value,
            unit=b.unit,
            reference_range=b.reference_range,
            status=_status,
            ocr_confidence=b.ocr_confidence,
            verified_by_user=not auto_save_blocked,
            normalized_value_si=_clf.get("normalized_value_si") if _clf else None,
            normalized_unit_si=_clf.get("normalized_unit_si") if _clf else None,
        )
        # Write-time plausibility guardrail (Phase 2) — OCR path.
        if b.canonical and b.value is not None:
            _vld_ocr = validate_before_save(
                biomarker_name=b.canonical,
                original_value=float(b.value),
                original_unit=b.unit or "",
                normalized_value_si=_clf.get("normalized_value_si") if _clf else None,
                normalized_unit_si=_clf.get("normalized_unit_si") if _clf else None,
            )
            lr.data_quality_flag = _vld_ocr.get("action")
            lr.data_quality_note = _vld_ocr.get("reason") if _vld_ocr["suspicious"] else None
            if _vld_ocr["suspicious"]:
                _log.warning(
                    "validate_before_save (OCR) flagged suspicious: canonical=%s value=%s unit=%s reason=%s",  # noqa: E501
                    b.canonical,
                    b.value,
                    b.unit,
                    _vld_ocr["reason"],
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



def _hardened_canonical(test_name: str | None) -> str | None:
    """Resolve a printed lab label with the SAME matcher every other path uses.

    Deliberately not `lab_interpreter.normalize_biomarker`: its final step is a
    bare containment scan, which maps VLDL onto ldl and non-HDL onto hdl. Labels
    with no safe canonical resolve to None here and are stored uncanonicalised
    rather than filed under a neighbouring analyte.
    """
    if not test_name:
        return None
    from app.services.lab_parser import _match_biomarker, _strip_accents, build_alias_index

    matched = _match_biomarker(_strip_accents(test_name.lower()), build_alias_index())
    return matched[0].canonical if matched else None


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
    commit: bool = True,
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
        # Prefer an explicit canonical resolved by the CALLER with the hardened
        # matcher. `normalize_biomarker`'s step 4 is a bare containment scan
        # (`alias in key or key in alias`), so re-deriving here silently disagreed
        # with whatever the caller had already validated units against — the
        # promoter could accept a row as HDL while this stored it as total
        # cholesterol. The fallback is the hardened matcher too, so no path in
        # this function can reach the containment scan any more.
        canonical = item.get("canonical") or _hardened_canonical(item["test_name"])

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

        # Auto-classify at creation time: use the already-normalized canonical_value.
        classification = normalize_and_classify(canonical, canonical_value, canonical_unit_str)

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
            original_value=item.get("original_value")
            if item.get("original_value") is not None
            else raw_value,  # noqa: E501
            original_unit=item.get("original_unit")
            if item.get("original_unit") is not None
            else raw_unit,  # noqa: E501
            original_reference_range=item.get("original_reference_range"),
            original_test_name=item.get("original_test_name"),
            normalized_value_si=classification.get("normalized_value_si"),
            normalized_unit_si=classification.get("normalized_unit_si"),
            status=classification.get("status"),
        )
        # Write-time plausibility guardrail (Phase 2).
        _orig_val = (
            item.get("original_value") if item.get("original_value") is not None else raw_value
        )
        _orig_unit = (
            item.get("original_unit") if item.get("original_unit") is not None else raw_unit
        )
        if canonical and _orig_val is not None:
            _vld = validate_before_save(
                biomarker_name=canonical,
                original_value=float(_orig_val),
                original_unit=_orig_unit or "",
                normalized_value_si=classification.get("normalized_value_si"),
                normalized_unit_si=classification.get("normalized_unit_si"),
            )
            row.data_quality_flag = _vld.get("action")
            row.data_quality_note = _vld.get("reason") if _vld["suspicious"] else None
            if _vld["suspicious"]:
                _log.warning(
                    "validate_before_save flagged suspicious: canonical=%s value=%s unit=%s reason=%s",  # noqa: E501
                    canonical,
                    _orig_val,
                    _orig_unit,
                    _vld["reason"],
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
            _log.exception(
                "ocr_case_confirm_failed case=%s patient=%s — lab save NOT rolled back",
                ocr_case_id,
                patient_id,
            )

    # commit=False lets a transaction-owning caller (the MDI lab promoter) keep
    # the lab document/results/metrics + its candidate status + PromotionLink in
    # one atomic scope; it flushes instead so ids are available.
    if commit:
        db.commit()
        for row in rows:
            db.refresh(row)
    else:
        db.flush()
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

    # Phase 2 — classify-on-read fallback: if a row has a known canonical name
    # and a normalized value but still lacks a status (e.g. legacy/backfill gap),
    # compute it in-memory for display only — DO NOT commit to DB here.
    for result in rows:
        if (
            result.status is None
            and result.normalized_value_si is not None
            and result.canonical_name
        ):
            computed = classify_value(result.canonical_name, result.normalized_value_si)
            if computed is not None:
                result.status = computed.value

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
    total = db.execute(select(func.count()).select_from(LabResult).where(*base)).scalar_one()
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


def reclassify_lab_results(
    db: Session,
    *,
    batch_id: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Recompute status for existing LabResult records with null or missing status.

    Logic per record:
    1. Skip if canonical_name is null/missing (can't classify without known biomarker).
    2. Skip if both original_value and normalized_value_si are null (no value to classify).
    3. If normalized_value_si is null → compute from original_value + original_unit.
    4. Recompute status using classify_value(canonical_name, normalized_value_si).
    5. Update status, normalized fields in DB.
    6. NEVER overwrite: original_value, original_unit, raw OCR fields.
    7. If dry_run=True → return what WOULD change, no DB writes.

    Idempotent: records already correctly classified are counted as skipped.
    Returns: {"updated": N, "skipped": N, "errors": [str, ...]}
    """
    errors: list[str] = []
    updated = 0
    skipped = 0

    # Build query.
    conditions = [LabResult.deleted_at.is_(None)]
    if batch_id is not None:
        conditions.append(LabResult.batch_id == batch_id)

    rows = list(db.execute(select(LabResult).where(*conditions)).scalars())

    for row in rows:
        try:
            # Skip if no canonical name (can't classify).
            if not row.canonical_name:
                skipped += 1
                continue

            # Skip if no value available at all.
            if row.original_value is None and row.value is None and row.normalized_value_si is None:
                skipped += 1
                continue

            # Resolve the value to classify against. Use normalized_value_si if present;
            # otherwise derive from original_value + original_unit (or value + unit).
            norm_value = row.normalized_value_si
            norm_unit = row.normalized_unit_si

            if norm_value is None:
                # Try to normalize from original_value/original_unit first, then fallback to value/unit.  # noqa: E501
                raw_val = row.original_value if row.original_value is not None else row.value
                raw_unit = row.original_unit if row.original_unit is not None else row.unit

                if raw_val is None:
                    skipped += 1
                    continue

                if raw_unit:
                    norm_value, norm_unit = normalize_value_to_si(
                        raw_val, raw_unit, row.canonical_name
                    )
                else:
                    # No unit info — assume canonical unit and classify directly.
                    norm_value = raw_val
                    norm_unit = lab_interpreter._ALIAS_INDEX.get(row.canonical_name, None)
                    norm_unit = norm_unit.unit if norm_unit else None

            # Compute new status.
            new_status_enum = classify_value(row.canonical_name, norm_value)
            if new_status_enum is None:
                skipped += 1
                continue

            new_status = new_status_enum.value
            old_status = row.status

            # Check if already correctly classified (idempotent).
            if row.status == new_status and row.normalized_value_si == norm_value:
                skipped += 1
                continue

            _log.info(
                "reclassify %s (%s): %s → %s  (value=%.4f)",
                row.id,
                row.canonical_name,
                old_status,
                new_status,
                norm_value,
            )

            if not dry_run:
                row.status = new_status
                # Only update normalized fields if they were missing.
                if row.normalized_value_si is None:
                    row.normalized_value_si = norm_value
                if row.normalized_unit_si is None and norm_unit is not None:
                    row.normalized_unit_si = norm_unit

            updated += 1

        except Exception as exc:  # noqa: BLE001
            err_msg = (
                f"reclassify error row {row.id} ({getattr(row, 'canonical_name', '?')}): {exc}"
            )
            _log.warning(err_msg)
            errors.append(err_msg)

    if not dry_run and updated > 0:
        try:
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            errors.append(f"DB commit failed: {exc}")
            updated = 0

    return {"updated": updated, "skipped": skipped, "errors": errors}



def _sync_linked_health_metrics(
    db: Session,
    *,
    result_id: str,
    canonical_value: float | None,
    canonical_unit: str | None,
    new_status: str | None,
    requester_id: str,
) -> int:
    """Sync all live HealthMetric rows promoted from a LabResult after a correction.

    Updates value, unit, status for every live metric with source_ref == result_id.
    No-op when no linked metric exists. Returns count of rows updated.
    """
    if canonical_value is None:
        return 0
    metrics = db.execute(
        select(HealthMetric).where(
            HealthMetric.source_ref == result_id,
            HealthMetric.deleted_at.is_(None),
        )
    ).scalars().all()
    for m in metrics:
        m.value = canonical_value
        if canonical_unit is not None:
            m.unit = canonical_unit
        if new_status is not None:
            m.status = new_status
        spec = lab_interpreter._ALIAS_INDEX.get(m.metric_type)
        if spec is not None:
            m.normal_range_min = spec.ref_low
            m.normal_range_max = spec.ref_high
    db.flush()
    return len(metrics)

def correct_lab_result(
    db: Session,
    *,
    result_id: str,
    patient_id: str,
    requester_id: str,
    new_value: float,
    new_unit: str,
) -> LabResult:
    """User-corrects value/unit of an existing LabResult and triggers reclassification.

    - Appends old value to correction_history_json (provenance).
    - Updates original_value, original_unit to corrected values.
    - Re-runs normalize_and_classify() to update normalized_value_si, normalized_unit_si, status.
    - NEVER loses the original measurement: correction_history_json stores the trail.
    """
    import json

    consent.require_access(db, patient_id=patient_id, requester_id=requester_id, scope="lab")

    row = db.execute(
        select(LabResult).where(
            LabResult.id == result_id,
            LabResult.patient_id == patient_id,
            LabResult.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    if row is None:
        raise ValueError(f"LabResult {result_id!r} not found for patient {patient_id!r}")

    # Append provenance record before overwriting.
    history = json.loads(row.correction_history_json) if row.correction_history_json else []
    history.append(
        {
            "timestamp": utcnow().isoformat(),
            "old_value": row.original_value,
            "old_unit": row.original_unit,
            "corrected_by": "user",
        }
    )
    row.correction_history_json = json.dumps(history)

    # Update to corrected values.
    row.original_value = new_value
    row.original_unit = new_unit

    # Re-classify.
    classification = normalize_and_classify(row.canonical_name, new_value, new_unit)
    row.normalized_value_si = classification.get("normalized_value_si")
    row.normalized_unit_si = classification.get("normalized_unit_si")
    row.status = classification.get("status")

    # Also update the canonical value/unit fields.
    # IMPORTANT: row.value/unit must use the CANONICAL (primary) unit, not SI.
    # For glucose: canonical = mg/dL, SI/display = mmol/L.
    # normalized_value_si is already in canonical unit (despite the name);
    # normalized_unit_si is the canonical unit string (e.g. 'mg/dL' for glucose).
    # Using normalized_unit_si here is correct — it IS the canonical unit.
    canonical_value = classification.get("normalized_value_si")
    canonical_unit = classification.get("normalized_unit_si")
    row.value = canonical_value if canonical_value is not None else new_value
    row.unit = canonical_unit if canonical_unit is not None else new_unit

    # Sync linked HealthMetric rows so dashboard/charts reflect the correction.
    _sync_linked_health_metrics(
        db,
        result_id=row.id,
        canonical_value=canonical_value if canonical_value is not None else new_value,
        canonical_unit=canonical_unit if canonical_unit is not None else new_unit,
        new_status=classification.get("status"),
        requester_id=requester_id,
    )

    audit.record(
        db,
        actor_type="user",
        actor_id=requester_id,
        action="correct_lab_result",
        resource_type="lab_result",
        resource_id=row.id,
    )

    db.commit()
    db.refresh(row)
    return row


def edit_lab_result(
    db: Session,
    *,
    result_id: str,
    patient_id: str,
    requester_id: str,
    value: float | None = None,
    unit: str | None = None,
    test_name: str | None = None,
    reference_range: str | None = None,
    test_date=None,
    source_type: str | None = None,
) -> LabResult:
    """Extended partial-update for a LabResult.

    Applies any provided fields.  When value or unit changes, re-runs
    normalize_and_classify() just like correct_lab_result().
    """
    import json as _json

    consent.require_access(db, patient_id=patient_id, requester_id=requester_id, scope="lab")

    row = db.execute(
        select(LabResult).where(
            LabResult.id == result_id,
            LabResult.patient_id == patient_id,
            LabResult.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    if row is None:
        raise ValueError(f"LabResult {result_id!r} not found for patient {patient_id!r}")

    # Metadata fields
    if test_name is not None:
        row.test_name = test_name
    if reference_range is not None:
        row.reference_range = reference_range
    if test_date is not None:
        row.test_date = test_date

    # Value / unit change → re-classify (mirrors correct_lab_result logic)
    if value is not None or unit is not None:
        new_value = value if value is not None else row.original_value
        new_unit = unit if unit is not None else (row.original_unit or "")

        # Store provenance
        history = _json.loads(row.correction_history_json) if row.correction_history_json else []
        history.append(
            {
                "timestamp": utcnow().isoformat(),
                "old_value": row.original_value,
                "old_unit": row.original_unit,
                "corrected_by": "user",
            }
        )
        row.correction_history_json = _json.dumps(history)

        row.original_value = new_value
        row.original_unit = new_unit

        classification = normalize_and_classify(row.canonical_name, new_value, new_unit)
        row.normalized_value_si = classification.get("normalized_value_si")
        row.normalized_unit_si = classification.get("normalized_unit_si")
        row.status = classification.get("status")

        canonical_value = classification.get("normalized_value_si")
        canonical_unit = classification.get("normalized_unit_si")
        row.value = canonical_value if canonical_value is not None else new_value
        row.unit = canonical_unit if canonical_unit is not None else new_unit

        # Sync linked HealthMetric rows so dashboard/charts reflect the edit.
        _sync_linked_health_metrics(
            db,
            result_id=row.id,
            canonical_value=canonical_value if canonical_value is not None else new_value,
            canonical_unit=canonical_unit if canonical_unit is not None else new_unit,
            new_status=classification.get("status"),
            requester_id=requester_id,
        )

    audit.record(
        db,
        actor_type="user",
        actor_id=requester_id,
        action="edit_lab_result",
        resource_type="lab_result",
        resource_id=row.id,
    )

    db.commit()
    db.refresh(row)
    return row


def delete_lab_result(
    db: Session,
    *,
    result_id: str,
    patient_id: str,
    requester_id: str,
) -> None:
    """Soft-delete a single LabResult (sets deleted_at / deleted_by)."""
    consent.require_access(db, patient_id=patient_id, requester_id=requester_id, scope="lab")

    row = db.execute(
        select(LabResult).where(
            LabResult.id == result_id,
            LabResult.patient_id == patient_id,
            LabResult.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    if row is None:
        raise ValueError(f"LabResult {result_id!r} not found for patient {patient_id!r}")

    row.deleted_at = utcnow()
    row.deleted_by = requester_id

    audit.record(
        db,
        actor_type="user",
        actor_id=requester_id,
        action="delete",
        resource_type="lab_result",
        resource_id=result_id,
    )

    # Cascade soft-delete to any HealthMetric rows promoted from this lab result
    db.execute(
        sql_update(HealthMetric)
        .where(HealthMetric.source_ref == result_id)
        .where(HealthMetric.deleted_at.is_(None))
        .values(deleted_at=utcnow(), deleted_by=requester_id)
    )

    db.commit()
