"""Medication adherence endpoints — Phase 2.

Tests use the existing ``client`` and ``patient`` fixtures from conftest.
All DB ops run against an in-memory SQLite test database.
"""

from __future__ import annotations


def _add_medication(client, patient, name: str = "Metformin 500mg") -> str:
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/medications",
        json={"name": name, "dose": "500mg", "frequency": "2 lần/ngày"},
        headers=patient["headers"],
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_log_taken_dose(client, patient):
    med_id = _add_medication(client, patient)
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med_id}/adherence",
        json={"taken_at": "2026-06-24T08:00:00Z", "skipped": False},
        headers=patient["headers"],
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["medication_id"] == med_id
    assert body["patient_id"] == patient["patient_id"]
    assert body["skipped"] is False
    assert "2026-06-24" in body["taken_at"]


def test_log_skipped_dose(client, patient):
    med_id = _add_medication(client, patient, name="Atorvastatin 10mg")
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med_id}/adherence",
        json={"skipped": True, "note": "Quên uống buổi sáng"},
        headers=patient["headers"],
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["skipped"] is True
    assert body["note"] == "Quên uống buổi sáng"
    assert body["taken_at"] is None


def test_log_adherence_bare_post(client, patient):
    med_id = _add_medication(client, patient, name="Vitamin D 1000IU")
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med_id}/adherence",
        json={},
        headers=patient["headers"],
    )
    assert r.status_code == 201, r.text


def test_log_adherence_404_for_unknown_medication(client, patient):
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/medications/nonexistent-id/adherence",
        json={"taken_at": "2026-06-24T08:00:00Z"},
        headers=patient["headers"],
    )
    assert r.status_code == 404


def test_log_adherence_requires_auth(client, patient):
    med_id = _add_medication(client, patient)
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med_id}/adherence",
        json={"taken_at": "2026-06-24T08:00:00Z"},
    )
    assert r.status_code == 401


def test_get_adherence_history(client, patient):
    med_id = _add_medication(client, patient, name="Losartan 50mg")
    for i in range(3):
        client.post(
            f"/api/v1/patients/{patient['patient_id']}/medications/{med_id}/adherence",
            json={"taken_at": f"2026-06-2{i + 1}T08:00:00Z"},
            headers=patient["headers"],
        )
    r = client.get(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med_id}/adherence",
        headers=patient["headers"],
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 3
    assert items[0]["medication_id"] == med_id


def test_get_adherence_history_empty(client, patient):
    med_id = _add_medication(client, patient, name="Aspirin 100mg")
    r = client.get(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med_id}/adherence",
        headers=patient["headers"],
    )
    assert r.status_code == 200
    assert r.json() == []


def test_get_adherence_history_limit(client, patient):
    med_id = _add_medication(client, patient, name="Omeprazole 20mg")
    for i in range(5):
        client.post(
            f"/api/v1/patients/{patient['patient_id']}/medications/{med_id}/adherence",
            json={"taken_at": f"2026-06-2{i + 1}T08:00:00Z"},
            headers=patient["headers"],
        )
    r = client.get(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med_id}/adherence?limit=2",
        headers=patient["headers"],
    )
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_adherence_summary_empty(client, patient):
    r = client.get(
        f"/api/v1/patients/{patient['patient_id']}/medications/adherence-summary",
        headers=patient["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_doses_logged"] == 0
    assert body["taken"] == 0
    assert body["skipped"] == 0
    assert body["adherence_rate"] == 0.0


def test_adherence_summary_counts(client, patient):
    med_id = _add_medication(client, patient, name="Januvia 100mg")
    client.post(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med_id}/adherence",
        json={"taken_at": "2026-06-23T08:00:00Z"},
        headers=patient["headers"],
    )
    client.post(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med_id}/adherence",
        json={"skipped": True},
        headers=patient["headers"],
    )
    r = client.get(
        f"/api/v1/patients/{patient['patient_id']}/medications/adherence-summary",
        headers=patient["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["taken"] >= 1
    assert body["skipped"] >= 1
    assert 0.0 <= body["adherence_rate"] <= 1.0
    assert any(m["medication_id"] == med_id for m in body["today_medications"])


def test_adherence_summary_today_medication_fields(client, patient):
    med_id = _add_medication(client, patient, name="Empagliflozin 10mg")
    r = client.get(
        f"/api/v1/patients/{patient['patient_id']}/medications/adherence-summary",
        headers=patient["headers"],
    )
    assert r.status_code == 200
    meds = r.json()["today_medications"]
    med = next((m for m in meds if m["medication_id"] == med_id), None)
    assert med is not None
    assert "name" in med
    assert "taken_today" in med
    assert "skipped_today" in med
