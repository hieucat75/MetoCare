"""J3 action-first dashboard tests (BRD §I)."""

from __future__ import annotations

import datetime as dt

from app.main import app
from app.models.medical_document import (
    DocumentExtraction,
    ExtractionCandidate,
    MedicalDocument,
)
from app.services import medication as medication_svc
from app.services import medication_schedule as sched
from app.services import patient_dashboard
from fastapi.testclient import TestClient


def _seed_needs_review_candidate(db, patient_id: str):
    doc = MedicalDocument(
        patient_id=patient_id, quarantine_key="q", status="needs_review", object_state="accepted"
    )
    db.add(doc)
    db.flush()
    ext = DocumentExtraction(
        document_id=doc.id, schema_version="mdi-1", provider="mock", extraction_run_id="r1"
    )
    db.add(ext)
    db.flush()
    db.add(
        ExtractionCandidate(
            extraction_id=ext.id,
            document_id=doc.id,
            patient_id=patient_id,
            candidate_type="medication",
            fields_json={"name": "X"},
            dedupe_key="k1",
            status="needs_review",
        )
    )
    db.commit()


def test_dashboard_surfaces_doses_due_and_pending_reviews(db, patient):
    pid = patient["patient_id"]
    med = medication_svc.add_medication(db, patient_id=pid, data={"name": "Metformin"}, commit=True)
    s = sched.create_schedule(
        db,
        patient_id=pid,
        medication_id=med.id,
        schedule_type="fixed_daily",
        local_dose_times=["08:00"],
        patient_timezone="UTC",
        start_date=dt.date(2026, 6, 1),
        end_date=dt.date(2026, 6, 1),
    )
    db.commit()
    sched.materialize_due(db, s, now=dt.datetime(2026, 6, 1, 8, 1, tzinfo=dt.UTC))
    db.commit()
    _seed_needs_review_candidate(db, pid)

    result = patient_dashboard.build_dashboard(
        db, patient_id=pid, now=dt.datetime(2026, 6, 1, 8, 5, tzinfo=dt.UTC)
    )
    assert result["doses_due_count"] == 1
    assert result["pending_document_reviews"] == 1
    assert result["active_medications"] == 1
    assert result["empty_state"] is False
    action_types = {a["type"] for a in result["actions"]}
    assert {"medication_dose", "confirm_document"} <= action_types


def test_dashboard_empty_state(db, patient):
    result = patient_dashboard.build_dashboard(db, patient_id=patient["patient_id"])
    assert result["empty_state"] is True
    assert result["actions"][0]["type"] == "add_document"


def test_dashboard_api_and_bola(db, patient, token_for):
    from app.models.patient import PatientProfile
    from app.models.user import User, UserRole

    client = TestClient(app)
    r = client.get(
        f"/api/v1/patients/{patient['patient_id']}/dashboard", headers=patient["headers"]
    )
    assert r.status_code == 200, r.text
    assert "actions" in r.json()

    other = User(
        email="dash2@example.com", password_hash="x", role=UserRole.PATIENT, full_name="D2"
    )
    db.add(other)
    db.flush()
    db.add(PatientProfile(user_id=other.id, full_name="D2"))
    db.commit()
    r2 = client.get(
        f"/api/v1/patients/{patient['patient_id']}/dashboard",
        headers=token_for(other.id, role="patient"),
    )
    assert r2.status_code == 403


def test_stopped_medication_removed_from_dashboard_actions(db, patient):
    """CLIN PS-5: a discontinued drug must not appear as a "take your dose"
    action — the dashboard is the action feed the patient acts on."""
    pid = patient["patient_id"]
    med = medication_svc.add_medication(db, patient_id=pid, data={"name": "Enalapril"}, commit=True)
    s = sched.create_schedule(
        db,
        patient_id=pid,
        medication_id=med.id,
        schedule_type="fixed_daily",
        local_dose_times=["08:00"],
        patient_timezone="UTC",
        start_date=dt.date(2026, 6, 1),
        end_date=dt.date(2026, 6, 1),
    )
    db.commit()
    sched.materialize_due(db, s, now=dt.datetime(2026, 6, 1, 8, 1, tzinfo=dt.UTC))
    db.commit()
    medication_svc.update_medication(
        db,
        patient_id=pid,
        med_id=med.id,
        data={"lifecycle_status": "discontinued", "status_reason": "ngừng theo chỉ định"},
        actor_user_id=patient["user_id"],
        actor_role="patient",
    )

    result = patient_dashboard.build_dashboard(
        db, patient_id=pid, now=dt.datetime(2026, 6, 1, 8, 5, tzinfo=dt.UTC)
    )
    assert result["doses_due_count"] == 0
    assert "medication_dose" not in {a["type"] for a in result["actions"]}
    assert result["active_medications"] == 0
