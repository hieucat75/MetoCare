"""Lab → health_metrics promotion (dashboard/metrics sync).

Confirming lab results promotes overlapping biomarkers into `health_metrics`
(source='lab_result', measured at the exam date) so the dashboard tiles + trend
charts reflect the new values immediately.
"""

from __future__ import annotations

import datetime as dt

from app.models.clinical import HealthMetric, LabResult
from app.services import lab
from sqlalchemy import select


def _save_labs(client, patient, *, test_date="2025-05-20", results=None):
    return client.post(
        f"/api/v1/patients/{patient['patient_id']}/lab-results",
        json={"test_date": test_date, "results": results or []},
        headers=patient["headers"],
    )


def _metrics(db, patient, metric_type=None):
    stmt = select(HealthMetric).where(HealthMetric.patient_id == patient["patient_id"])
    if metric_type:
        stmt = stmt.where(HealthMetric.metric_type == metric_type)
    return list(db.execute(stmt).scalars())


# --------------------------------------------------------------------------- #
# Promotion on confirm-save
# --------------------------------------------------------------------------- #

def test_lab_save_promotes_overlapping_metrics(client, patient, db):
    r = _save_labs(client, patient, results=[
        {"test_name": "fasting_glucose", "value": 140, "unit": "mg/dL"},
        {"test_name": "hba1c", "value": 7.2, "unit": "%"},
        {"test_name": "Triglyceride", "value": 320, "unit": "mg/dL"},
    ])
    assert r.status_code == 201, r.text
    promoted = _metrics(db, patient)
    by_type = {m.metric_type: m for m in promoted}
    assert by_type["fasting_glucose"].value == 140
    assert by_type["hba1c"].value == 7.2
    assert by_type["triglyceride"].value == 320  # freeform name normalised
    assert all(m.source == "lab_result" and m.source_ref for m in promoted)


def test_promoted_metric_measured_at_is_test_date(client, patient, db):
    _save_labs(client, patient, test_date="2024-11-03",
               results=[{"test_name": "fasting_glucose", "value": 99}])
    m = _metrics(db, patient, "fasting_glucose")[0]
    assert m.measured_at.date() == dt.date(2024, 11, 3)  # exam date, NOT today


def test_non_biomarker_not_promoted_no_error(client, patient, db):
    r = _save_labs(client, patient, results=[
        {"test_name": "Chỉ số lạ không xác định", "value": 5},
        {"test_name": "fasting_glucose", "value": 110},
    ])
    assert r.status_code == 201, r.text
    promoted = _metrics(db, patient)
    types = {m.metric_type for m in promoted}
    assert "fasting_glucose" in types
    assert all(t != "Chỉ số lạ không xác định" for t in types)  # unmapped dropped


def test_lab_row_without_value_not_promoted(client, patient, db):
    _save_labs(client, patient, results=[{"test_name": "fasting_glucose", "value": None}])
    assert _metrics(db, patient, "fasting_glucose") == []


# --------------------------------------------------------------------------- #
# Idempotency
# --------------------------------------------------------------------------- #

def test_promotion_is_idempotent(db, patient):
    row = LabResult(
        patient_id=patient["patient_id"], test_name="fasting_glucose",
        canonical_name="fasting_glucose", value=126.0, unit="mg/dL",
        test_date=dt.date(2025, 1, 1), verified_by_user=True,
    )
    db.add(row)
    db.flush()
    pid, td = patient["patient_id"], dt.date(2025, 1, 1)
    lab.promote_lab_rows_to_metrics(db, patient_id=pid, rows=[row], test_date=td)
    lab.promote_lab_rows_to_metrics(db, patient_id=pid, rows=[row], test_date=td)
    db.commit()
    rows = _metrics(db, patient, "fasting_glucose")
    assert len(rows) == 1  # re-promoting the same lab row replaces, never duplicates


# --------------------------------------------------------------------------- #
# Surfaces through the metrics API (what the dashboard/trend read)
# --------------------------------------------------------------------------- #

def test_metrics_api_returns_promoted_lab_value(client, patient):
    _save_labs(client, patient, test_date="2025-05-20",
               results=[{"test_name": "fasting_glucose", "value": 145, "unit": "mg/dL"}])
    got = client.get(
        f"/api/v1/patients/{patient['patient_id']}/metrics?metric_type=fasting_glucose",
        headers=patient["headers"],
    )
    assert got.status_code == 200, got.text
    items = got.json()["items"] if isinstance(got.json(), dict) else got.json()
    assert any(abs(it["value"] - 145) < 1e-6 for it in items), items


def test_metrics_status_classified_on_promotion(client, patient, db):
    # 140 fasting glucose is above the 70-99 reference -> classified high.
    _save_labs(client, patient, results=[{"test_name": "fasting_glucose", "value": 140}])
    m = _metrics(db, patient, "fasting_glucose")[0]
    assert m.status in ("high", "critical")


# --------------------------------------------------------------------------- #
# Backfill — fixes orphan labs (pre-sync / interpret / pipeline paths)
# --------------------------------------------------------------------------- #

def _orphan_lab(db, patient, **kw):
    """Insert a lab_result directly with NO promotion (simulates a pre-sync lab)."""
    row = LabResult(
        patient_id=patient["patient_id"], verified_by_user=True,
        **{"test_name": "fasting_glucose", "canonical_name": "fasting_glucose",
           "value": 140.0, "unit": "mg/dL", "test_date": dt.date(2024, 10, 15), **kw},
    )
    db.add(row)
    db.commit()
    return row


def test_backfill_promotes_orphan_labs(db, patient):
    _orphan_lab(db, patient)
    assert _metrics(db, patient, "fasting_glucose") == []  # orphan: not promoted yet
    n = lab.backfill_lab_metrics(db)
    assert n == 1
    m = _metrics(db, patient, "fasting_glucose")
    assert len(m) == 1 and m[0].value == 140 and m[0].source == "lab_result"
    assert m[0].measured_at.date() == dt.date(2024, 10, 15)  # uses the exam date


def test_backfill_is_idempotent(db, patient):
    _orphan_lab(db, patient)
    assert lab.backfill_lab_metrics(db) == 1
    assert lab.backfill_lab_metrics(db) == 0  # nothing left to promote
    assert len(_metrics(db, patient, "fasting_glucose")) == 1  # no duplicate


def test_backfill_skips_already_synced(client, patient, db):
    # A normally-saved (already promoted) lab is not re-promoted by the backfill.
    _save_labs(client, patient, results=[{"test_name": "fasting_glucose", "value": 99}])
    before = len(_metrics(db, patient, "fasting_glucose"))
    assert lab.backfill_lab_metrics(db) == 0
    assert len(_metrics(db, patient, "fasting_glucose")) == before


def test_backfill_orphan_without_test_date_uses_created_at(db, patient):
    _orphan_lab(db, patient, test_date=None)
    lab.backfill_lab_metrics(db)
    m = _metrics(db, patient, "fasting_glucose")
    assert len(m) == 1  # promoted even without a test_date (measured_at = created_at)


def test_interpret_document_promotes_metrics(db, patient):
    # The synchronous interpret path (mock OCR) must also promote — was an orphan source.
    doc = lab.register_document(
        db, patient_id=patient["patient_id"], requester_id=patient["user_id"],
        storage_key="normal-panel", file_type="pdf",
    )
    lab.interpret_document(db, document_id=doc.id, requester_id=patient["user_id"])
    promoted = _metrics(db, patient)
    assert promoted and all(m.source == "lab_result" for m in promoted)
