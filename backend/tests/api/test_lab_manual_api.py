"""PR-B API tests — manual lab-result entry + AI/OCR feature-flag gating.

Covers:
  POST /patients/{patient_id}/lab-results   — manual structured entry (no OCR)
  GET  /patients/{patient_id}/lab-results   — list results
  OCR feature flag OFF → 503 on /process + /interpret
  AI_ASSISTANT flag OFF → 503 on /ai/chat
"""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.patient import PatientProfile
from app.models.user import User, UserRole


@pytest.fixture
def patient_setup(db):
    p_user = User(
        email=f"manual-lab-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Manual Lab Patient",
    )
    db.add(p_user)
    db.flush()
    profile = PatientProfile(user_id=p_user.id, full_name="Manual Lab Patient")
    db.add(profile)
    db.commit()
    token = create_access_token(subject=p_user.id, role="patient")
    return {
        "user_id": p_user.id,
        "patient_id": profile.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def _results_url(pid: str) -> str:
    return f"/api/v1/patients/{pid}/lab-results"


def test_manual_lab_entry_creates_results(client, patient_setup):
    """PR-B: patient can enter structured results manually (no OCR)."""
    r = client.post(
        _results_url(patient_setup["patient_id"]),
        headers=patient_setup["headers"],
        json={
            "lab_name": "Xét nghiệm máu tổng quát",
            "test_date": "2026-06-15",
            "results": [
                {"test_name": "Glucose", "value": 95, "unit": "mg/dL", "reference_range": "70-100"},
                {"test_name": "HbA1c", "value": 5.4, "unit": "%"},
            ],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["total"] == 2
    names = {it["test_name"] for it in body["items"]}
    assert names == {"Glucose", "HbA1c"}
    assert all(it["verified_by_user"] for it in body["items"])


def test_manual_entry_requires_at_least_one_result(client, patient_setup):
    r = client.post(
        _results_url(patient_setup["patient_id"]),
        headers=patient_setup["headers"],
        json={"lab_name": "Empty", "results": []},
    )
    assert r.status_code == 422, r.text


def test_list_lab_results_returns_entered(client, patient_setup):
    client.post(
        _results_url(patient_setup["patient_id"]),
        headers=patient_setup["headers"],
        json={
            "test_date": "2026-06-10",
            "results": [{"test_name": "LDL", "value": 110, "unit": "mg/dL"}],
        },
    )
    r = client.get(_results_url(patient_setup["patient_id"]), headers=patient_setup["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1
    assert any(it["test_name"] == "LDL" for it in body["items"])


def test_patient_cannot_read_another_patients_results(client, patient_setup, db):
    other = User(
        email=f"other-{os.urandom(4).hex()}@example.com",
        password_hash="x", role=UserRole.PATIENT, full_name="Other",
    )
    db.add(other)
    db.flush()
    other_profile = PatientProfile(user_id=other.id, full_name="Other")
    db.add(other_profile)
    db.commit()
    r = client.get(_results_url(other_profile.id), headers=patient_setup["headers"])
    assert r.status_code == 403, r.text


# --- Feature-flag fail-closed (PR-B) ---


def test_ocr_disabled_returns_503_on_interpret(client, patient_setup, monkeypatch):
    """OCR flag OFF → /interpret 503 (manual entry still works above)."""
    monkeypatch.setenv("FEATURE_OCR", "false")
    monkeypatch.setenv("MCP_FEATURE_OCR", "false")
    # register a document to interpret
    doc = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/lab-documents",
        headers=patient_setup["headers"],
        json={"storage_key": "k", "file_type": "pdf", "lab_name": "L"},
    ).json()
    r = client.post(
        f"/api/v1/lab-documents/{doc['id']}/interpret",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 503, r.text


def test_ocr_disabled_returns_503_on_process(client, patient_setup, monkeypatch):
    monkeypatch.setenv("FEATURE_OCR", "false")
    doc = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/lab-documents",
        headers=patient_setup["headers"],
        json={"storage_key": "k", "file_type": "pdf", "lab_name": "L"},
    ).json()
    r = client.post(f"/api/v1/lab-documents/{doc['id']}/process", headers=patient_setup["headers"])
    assert r.status_code == 503, r.text


def test_ai_assistant_disabled_returns_503_on_chat(client, patient_setup, monkeypatch):
    monkeypatch.setenv("FEATURE_AI_ASSISTANT", "false")
    r = client.post(
        "/api/v1/ai/chat",
        headers=patient_setup["headers"],
        json={"message": "Xin chào", "intent": "general"},
    )
    assert r.status_code == 503, r.text


def test_manual_entry_unaffected_by_ocr_flag(client, patient_setup, monkeypatch):
    """Manual entry must work even with OCR disabled (it is the non-OCR path)."""
    monkeypatch.setenv("FEATURE_OCR", "false")
    r = client.post(
        _results_url(patient_setup["patient_id"]),
        headers=patient_setup["headers"],
        json={
            "test_date": "2026-06-10",
            "results": [{"test_name": "Glucose", "value": 90, "unit": "mg/dL"}],
        },
    )
    assert r.status_code == 201, r.text
