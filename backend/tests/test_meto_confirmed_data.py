"""J4/M8 — Meto AI must only ever see CONFIRMED clinical data (BRD §J / AI2).

Two guarantees are locked here:

1. `_build_recent_labs` never returns unverified OCR lab rows. Unverified rows
   (verified_by_user=False) persist in lab_results after an OCR upload but before
   the patient confirms them; they must not enter the AI context.
2. The generative chat endpoints are gated by the AI_ASSISTANT feature flag
   (progressive enablement, §1.10) and fail closed (503) when it is off.
"""

from __future__ import annotations

import datetime as dt

from app.ai.context.builder import ContextBuilder
from app.models.clinical import LabResult, LabUploadBatch


def _seed_labs(db, patient_id: str):
    """Seed one confirmed + one unverified lab row in a recent batch."""
    batch = LabUploadBatch(patient_id=patient_id, test_date=dt.date.today())
    db.add(batch)
    db.flush()
    db.add_all(
        [
            LabResult(
                patient_id=patient_id,
                batch_id=batch.id,
                test_name="HbA1c",
                value=7.2,
                unit="%",
                status="high",
                verified_by_user=True,
            ),
            LabResult(
                patient_id=patient_id,
                batch_id=batch.id,
                test_name="Glucose",
                value=9.9,
                unit="mmol/L",
                status="high",
                verified_by_user=False,  # unconfirmed OCR row — must be excluded
            ),
        ]
    )
    db.commit()


def test_build_recent_labs_excludes_unverified(db, patient):
    _seed_labs(db, patient["patient_id"])

    rows = ContextBuilder()._build_recent_labs(db, patient["user_id"])

    assert rows is not None
    names = {r["test_name"] for r in rows}
    assert "HbA1c" in names  # confirmed row present
    assert "Glucose" not in names  # unconfirmed OCR row excluded (AI2 fix)


def test_build_recent_labs_includes_doctor_verified(db, patient):
    """A doctor-verified lab (not re-ticked by the patient) is still CONFIRMED and
    must reach Meto — matching the platform-wide confirmed = user OR doctor rule."""
    batch = LabUploadBatch(patient_id=patient["patient_id"], test_date=dt.date.today())
    db.add(batch)
    db.flush()
    db.add(
        LabResult(
            patient_id=patient["patient_id"],
            batch_id=batch.id,
            test_name="Creatinine",
            value=1.1,
            unit="mg/dL",
            verified_by_user=False,
            verified_by_doctor=True,
        )
    )
    db.commit()

    rows = ContextBuilder()._build_recent_labs(db, patient["user_id"])
    assert rows is not None
    assert "Creatinine" in {r["test_name"] for r in rows}


def test_build_recent_labs_none_when_only_unverified(db, patient):
    """A patient with only unconfirmed OCR labs yields no AI lab context at all."""
    batch = LabUploadBatch(patient_id=patient["patient_id"], test_date=dt.date.today())
    db.add(batch)
    db.flush()
    db.add(
        LabResult(
            patient_id=patient["patient_id"],
            batch_id=batch.id,
            test_name="LDL",
            value=4.1,
            unit="mmol/L",
            verified_by_user=False,
        )
    )
    db.commit()

    assert ContextBuilder()._build_recent_labs(db, patient["user_id"]) is None


def test_build_recent_metrics_excludes_untrusted_source(db, patient):
    """Defense-in-depth: a metric from an untrusted (e.g. future OCR) source is
    excluded from the AI context; trusted patient/lab sources are included."""
    from app.models.clinical import HealthMetric

    now = dt.datetime.utcnow()  # naive UTC, as the app stores measured_at
    db.add_all(
        [
            HealthMetric(
                patient_id=patient["patient_id"],
                metric_type="glucose_fasting",
                value=5.5,
                unit="mmol/L",
                original_value=5.5,
                original_unit="mmol/L",
                measured_at=now,
                source="manual",
                status="normal",
            ),
            HealthMetric(
                patient_id=patient["patient_id"],
                metric_type="body_weight",
                value=70.0,
                unit="kg",
                original_value=70.0,
                original_unit="kg",
                measured_at=now,
                source="ocr_candidate",  # untrusted / unverified future source
                status="normal",
            ),
        ]
    )
    db.commit()

    rows = ContextBuilder()._build_recent_metrics(db, patient["user_id"])
    assert rows is not None
    types = {r["metric_type"] for r in rows}
    assert "glucose_fasting" in types  # trusted source included
    assert "body_weight" not in types  # untrusted source excluded


def test_meto_chat_blocked_when_flag_off(patient, client, monkeypatch):
    # FEATURE_ is consulted before MCP_FEATURE_ in is_enabled, so this alone gates.
    monkeypatch.setenv("FEATURE_AI_ASSISTANT", "false")
    r = client.post(
        "/api/v1/meto/chat",
        headers=patient["headers"],
        json={"message": "xin chào", "screen_id": "dashboard"},
    )
    assert r.status_code == 503, r.text


def test_meto_chat_stream_blocked_when_flag_off(patient, client, monkeypatch):
    monkeypatch.setenv("FEATURE_AI_ASSISTANT", "false")
    r = client.post(
        "/api/v1/meto/chat/stream",
        headers=patient["headers"],
        json={"message": "xin chào", "screen_id": "dashboard"},
    )
    assert r.status_code == 503, r.text
