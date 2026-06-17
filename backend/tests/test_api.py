"""API smoke + behavior tests (FastAPI TestClient, throwaway SQLite)."""

from __future__ import annotations


def _auth(patient):
    return patient["headers"]  # Bearer JWT for the patient's owner user


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_info_endpoint_reports_mock_modes(client):
    r = client.get("/api/v1/info")
    assert r.status_code == 200
    body = r.json()
    assert body["ai_mode"] == "mock"
    assert body["ocr_mode"] == "mock"


def test_create_and_list_metric(client, patient):
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/metrics",
        headers=_auth(patient),
        json={"metric_type": "fasting_glucose", "value": 95, "unit": "mg/dL",
              "normal_range_min": 70, "normal_range_max": 99},
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "normal"

    r2 = client.get(
        f"/api/v1/patients/{patient['patient_id']}/metrics?metric_type=fasting_glucose",
        headers=_auth(patient),
    )
    assert r2.status_code == 200
    assert len(r2.json()) >= 1


def test_metric_access_denied_without_auth(client, patient):
    r = client.get(f"/api/v1/patients/{patient['patient_id']}/metrics")
    assert r.status_code == 401  # missing bearer token


def test_metric_access_denied_for_stranger(client, patient, token_for):
    r = client.get(
        f"/api/v1/patients/{patient['patient_id']}/metrics",
        headers=token_for("stranger-123"),
    )
    assert r.status_code == 403  # consent gate


def test_critical_metric_status(client, patient):
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/metrics",
        headers=_auth(patient),
        json={"metric_type": "blood_pressure_systolic", "value": 200},
    )
    assert r.status_code == 201
    assert r.json()["status"] == "critical"


def test_lab_upload_and_interpret(client, patient):
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/lab-documents",
        headers=_auth(patient),
        json={"storage_key": "mock://lab/doc-1.pdf", "file_type": "pdf"},
    )
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]

    r2 = client.post(
        f"/api/v1/lab-documents/{doc_id}/interpret",
        headers=_auth(patient),
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert "không thay thế tư vấn bác sĩ" in body["patient_explanation"]
    assert any(b["canonical"] == "fasting_glucose" for b in body["biomarkers"])


def test_ai_chat_is_guardrailed_and_has_disclaimer(client, patient):
    r = client.post(
        "/api/v1/ai/chat",
        headers=_auth(patient),
        json={"message": "Tôi nên ăn gì buổi tối?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "không thay thế tư vấn bác sĩ" in body["text"]
    assert body["blocked"] is False


def test_ai_chat_red_flag_escalates(client, patient):
    r = client.post(
        "/api/v1/ai/chat",
        headers=_auth(patient),
        json={"message": "Tôi bị đau ngực và khó thở."},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["escalated_to_doctor"] is True
    assert body["risk_level"] == "emergency"


def test_ai_chat_medication_query_redirects(client, patient):
    r = client.post(
        "/api/v1/ai/chat",
        headers=_auth(patient),
        json={"message": "Tôi có nên tăng liều thuốc tiểu đường không?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "bác sĩ" in body["text"]


def test_triage_endpoint_red_flag(client, patient):
    r = client.post(
        "/api/v1/ai/triage",
        headers=_auth(patient),
        json={"symptom_text": "đau ngực dữ dội"},
    )
    assert r.status_code == 200
    assert r.json()["risk_level"] == "emergency"


def test_metabolic_score_endpoint(client, patient):
    r = client.post(
        "/api/v1/ai/metabolic-score",
        headers=_auth(patient),
        json={"waist_cm": 110, "hba1c": 7.5, "triglyceride": 260, "hdl": 30, "systolic_bp": 150},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["band"] == "high_concern"
    assert body["factors"]


def test_consent_grant_and_revoke_via_api(client, patient, token_for):
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/consents",
        headers=_auth(patient),
        json={"granted_to": "doctor-z", "data_scope": "health_metric"},
    )
    assert r.status_code == 201, r.text
    consent_id = r.json()["id"]

    # doctor-z can now read
    r2 = client.get(
        f"/api/v1/patients/{patient['patient_id']}/metrics",
        headers=token_for("doctor-z", "doctor"),
    )
    assert r2.status_code == 200

    # revoke
    r3 = client.delete(
        f"/api/v1/patients/{patient['patient_id']}/consents/{consent_id}",
        headers=_auth(patient),
    )
    assert r3.status_code == 200

    r4 = client.get(
        f"/api/v1/patients/{patient['patient_id']}/metrics",
        headers=token_for("doctor-z", "doctor"),
    )
    assert r4.status_code == 403
