"""Doctor Portal P0 API tests.

Covers:
- GET  /doctor/stats             aggregate counts
- GET  /doctor/patients          search + risk filter + sort + pagination + consented flag
- GET  /doctor/patients/{id}/timeline   consent 403 + success mapping
- GET  /doctor/queue             lab+ai+care_plan aggregation, filters, pending_count
- PATCH /doctor/queue/{id}/review dispatch per item_type (happy + bad id 404)
- RBAC                           DOCTOR ok, MEDICAL_REVIEWER ok, PATIENT 403
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from app.core.security import create_access_token
from app.models.ai import (
    AIClinicalRecommendation,
    AISession,
)
from app.models.care import CarePlan, CarePlanStatus, Doctor, Encounter
from app.models.clinical import HealthMetric, LabResult
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from sqlalchemy.orm import Session

API = "/api/v1"


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def _doctor_headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user_id, role='doctor', mfa=True)}"}


def _reviewer_headers(user_id: str) -> dict:
    return {
        "Authorization": (
            f"Bearer {create_access_token(subject=user_id, role='medical_reviewer', mfa=True)}"
        )
    }


def _patient_headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user_id, role='patient', mfa=True)}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def doctor(db: Session):
    uid = os.urandom(4).hex()
    user = User(
        email=f"dr-{uid}@clinic.vn",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="BS Portal Test",
        is_active=True,
        mfa_enabled=True,
    )
    db.add(user)
    db.flush()
    doc = Doctor(user_id=user.id, full_name="BS Portal Test", specialty="Nội tiết", is_active=True)
    db.add(doc)
    db.commit()
    return {"user": user, "doctor": doc, "user_id": user.id, "doctor_id": doc.id}


def _make_patient(db: Session, *, risk: str | None = None, name: str = "Bệnh nhân", email=None):
    uid = os.urandom(4).hex()
    user = User(
        email=email or f"pt-{uid}@example.vn",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name=name,
        is_active=True,
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name=name, risk_segment=risk)
    db.add(profile)
    db.commit()
    return user, profile


def _grant_profile_consent(db: Session, patient_profile_id: str, doctor_user_id: str):
    c = Consent(
        patient_id=patient_profile_id,
        consent_type="doctor_access",
        data_scope="profile",
        granted_to=doctor_user_id,
    )
    db.add(c)
    db.commit()
    return c


def _grant_narrow_consent(db: Session, patient_profile_id: str, doctor_user_id: str):
    """A visibility-granting consent whose data_scope is NOT profile/'*'.

    Makes the patient VISIBLE (roster/queue) but NOT PHI-authorized, so name /
    email / risk must be masked.
    """
    c = Consent(
        patient_id=patient_profile_id,
        consent_type="ai_use",
        data_scope="ai_use",
        granted_to=doctor_user_id,
    )
    db.add(c)
    db.commit()
    return c


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


class TestRBAC:
    def test_no_token_401(self, client):
        assert client.get(f"{API}/doctor/stats").status_code == 401

    def test_patient_forbidden(self, client):
        assert (
            client.get(f"{API}/doctor/stats", headers=_patient_headers("pt-x")).status_code == 403
        )

    def test_doctor_ok(self, client, doctor):
        r = client.get(f"{API}/doctor/stats", headers=_doctor_headers(doctor["user_id"]))
        assert r.status_code == 200

    def test_medical_reviewer_ok(self, client, db):
        # A medical_reviewer without a Doctor row still gets a valid (zeroed) response.
        uid = os.urandom(4).hex()
        u = User(
            email=f"mr-{uid}@clinic.vn",
            password_hash="x",
            role=UserRole.MEDICAL_REVIEWER,
            full_name="Reviewer",
            is_active=True,
            mfa_enabled=True,
        )
        db.add(u)
        db.commit()
        r = client.get(f"{API}/doctor/stats", headers=_reviewer_headers(u.id))
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_zero_baseline(self, client, doctor):
        r = client.get(f"{API}/doctor/stats", headers=_doctor_headers(doctor["user_id"]))
        assert r.status_code == 200
        body = r.json()
        assert body["total_patients"] == 0
        assert body["pending_reviews"] == 0
        assert body["urgent_reviews"] == 0
        assert body["reviews_today"] == 0
        assert body["avg_review_time_min"] is None

    def test_counts_pending_and_patients(self, client, db, doctor):
        user, profile = _make_patient(db, risk="high")
        _grant_profile_consent(db, profile.id, doctor["user_id"])
        # a pending (unverified) lab -> pending_labs + queue lab item
        db.add(
            LabResult(
                patient_id=profile.id,
                test_name="Glucose",
                value=7.0,
                status="high",
                verified_by_doctor=False,
            )
        )
        db.commit()

        r = client.get(f"{API}/doctor/stats", headers=_doctor_headers(doctor["user_id"]))
        body = r.json()
        assert body["total_patients"] == 1
        assert body["pending_reviews"] >= 1
        # 'high' status lab -> priority high, not urgent
        assert body["urgent_reviews"] == 0


# ---------------------------------------------------------------------------
# Patient roster
# ---------------------------------------------------------------------------


class TestPatients:
    def test_scope_and_consented_flag(self, client, db, doctor):
        user, profile = _make_patient(db, risk="medium", name="An Nguyen")
        _grant_profile_consent(db, profile.id, doctor["user_id"])
        r = client.get(f"{API}/doctor/patients", headers=_doctor_headers(doctor["user_id"]))
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["id"] == profile.id  # PatientProfile.id (FE profile route key)
        assert item["consented"] is True
        assert item["risk_segment"] == "medium"

    def test_encounter_scope_without_consent_not_consented(self, client, db, doctor):
        user, profile = _make_patient(db, risk="low")
        db.add(
            Encounter(
                patient_id=profile.id,
                doctor_id=doctor["doctor_id"],
                encounter_type="consult",
                status="in_progress",
                encounter_date=dt.datetime.utcnow(),
            )
        )
        db.commit()
        r = client.get(f"{API}/doctor/patients", headers=_doctor_headers(doctor["user_id"]))
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["consented"] is False

    def test_search_filters_by_name(self, client, db, doctor):
        u1, p1 = _make_patient(db, name="Tran Binh")
        u2, p2 = _make_patient(db, name="Le Cuong")
        _grant_profile_consent(db, p1.id, doctor["user_id"])
        _grant_profile_consent(db, p2.id, doctor["user_id"])
        r = client.get(
            f"{API}/doctor/patients?search=binh", headers=_doctor_headers(doctor["user_id"])
        )
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == p1.id

    def test_risk_filter_high_includes_very_high(self, client, db, doctor):
        u1, p1 = _make_patient(db, risk="very_high")
        u2, p2 = _make_patient(db, risk="low")
        _grant_profile_consent(db, p1.id, doctor["user_id"])
        _grant_profile_consent(db, p2.id, doctor["user_id"])
        r = client.get(
            f"{API}/doctor/patients?risk=high", headers=_doctor_headers(doctor["user_id"])
        )
        body = r.json()
        ids = {i["id"] for i in body["items"]}
        assert p1.id in ids
        assert p2.id not in ids

    def test_pagination(self, client, db, doctor):
        for i in range(3):
            u, p = _make_patient(db, name=f"Pat{i}")
            _grant_profile_consent(db, p.id, doctor["user_id"])
        r = client.get(
            f"{API}/doctor/patients?limit=2&offset=0", headers=_doctor_headers(doctor["user_id"])
        )
        body = r.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2

    def test_sort_by_name(self, client, db, doctor):
        u1, p1 = _make_patient(db, name="Zeta")
        u2, p2 = _make_patient(db, name="Alpha")
        _grant_profile_consent(db, p1.id, doctor["user_id"])
        _grant_profile_consent(db, p2.id, doctor["user_id"])
        r = client.get(
            f"{API}/doctor/patients?sort=name", headers=_doctor_headers(doctor["user_id"])
        )
        body = r.json()
        assert body["items"][0]["full_name"] == "Alpha"


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


class TestTimeline:
    def test_no_consent_403(self, client, db, doctor):
        user, profile = _make_patient(db)
        r = client.get(
            f"{API}/doctor/patients/{profile.id}/timeline",
            headers=_doctor_headers(doctor["user_id"]),
        )
        assert r.status_code == 403

    def test_missing_patient_404(self, client, doctor):
        r = client.get(
            f"{API}/doctor/patients/does-not-exist/timeline",
            headers=_doctor_headers(doctor["user_id"]),
        )
        assert r.status_code == 404

    def test_success_maps_events(self, client, db, doctor):
        user, profile = _make_patient(db)
        _grant_profile_consent(db, profile.id, doctor["user_id"])
        db.add(
            HealthMetric(
                patient_id=profile.id,
                metric_type="weight_kg",
                value=80.0,
                measured_at=dt.datetime.utcnow(),
            )
        )
        db.add(
            HealthMetric(
                patient_id=profile.id,
                metric_type="weight_kg",
                value=78.0,
                measured_at=dt.datetime.utcnow() - dt.timedelta(days=30),
            )
        )
        db.commit()
        r = client.get(
            f"{API}/doctor/patients/{profile.id}/timeline",
            headers=_doctor_headers(doctor["user_id"]),
        )
        assert r.status_code == 200
        events = r.json()
        assert isinstance(events, list)
        # weight_change -> mapped to metric_logged
        assert all(
            e["event_type"]
            in {
                "lab_uploaded",
                "lab_approved",
                "metric_logged",
                "care_plan_created",
                "care_plan_approved",
                "ai_session",
                "consent_granted",
                "consent_revoked",
            }
            for e in events
        )


# ---------------------------------------------------------------------------
# Queue aggregation
# ---------------------------------------------------------------------------


def _seed_ai_rec(db, *, patient_id: str, doctor_user_id: str, doctor_id: str):
    """Seed a pending AI rec + consent(ai_use) so it enters the review queue."""
    session = AISession(patient_id=patient_id, session_type="lab_explanation")
    db.add(session)
    db.flush()
    rec = AIClinicalRecommendation.create_from_ai(
        session_id=session.id,
        patient_id=patient_id,
        recommendation_type="lab_interpretation",
    )
    db.add(rec)
    db.add(
        Consent(
            patient_id=patient_id,
            consent_type="ai_use",
            data_scope="*",
            granted_to=doctor_user_id,
        )
    )
    db.commit()
    return rec


class TestQueue:
    def test_aggregates_three_types(self, client, db, doctor):
        user, profile = _make_patient(db)
        _grant_profile_consent(db, profile.id, doctor["user_id"])
        # lab_result (pending)
        db.add(
            LabResult(
                patient_id=profile.id, test_name="HbA1c", value=8.0, status="high",
                verified_by_doctor=False,
            )
        )
        # care_plan (pending_review)
        db.add(CarePlan(patient_id=profile.id, title="Kế hoạch A", status=CarePlanStatus.PENDING_REVIEW))
        db.commit()
        # ai_session rec
        _seed_ai_rec(db, patient_id=profile.id, doctor_user_id=doctor["user_id"], doctor_id=doctor["doctor_id"])

        r = client.get(f"{API}/doctor/queue", headers=_doctor_headers(doctor["user_id"]))
        assert r.status_code == 200
        body = r.json()
        types = {i["item_type"] for i in body["items"]}
        assert types == {"lab_result", "ai_session", "care_plan"}
        assert body["pending_count"] == body["total"] == 3
        # composite ids
        for i in body["items"]:
            assert ":" in i["id"]
            assert i["id"].split(":", 1)[0] == i["item_type"]

    def test_filter_by_item_type(self, client, db, doctor):
        user, profile = _make_patient(db)
        _grant_profile_consent(db, profile.id, doctor["user_id"])
        db.add(
            LabResult(
                patient_id=profile.id, test_name="LDL", value=5.0, status="high",
                verified_by_doctor=False,
            )
        )
        db.add(CarePlan(patient_id=profile.id, title="Plan", status=CarePlanStatus.PENDING_REVIEW))
        db.commit()
        r = client.get(
            f"{API}/doctor/queue?item_type=care_plan", headers=_doctor_headers(doctor["user_id"])
        )
        body = r.json()
        assert {i["item_type"] for i in body["items"]} == {"care_plan"}
        # pending_count is over the whole queue, not the filtered slice
        assert body["pending_count"] == 2


# ---------------------------------------------------------------------------
# Review dispatch
# ---------------------------------------------------------------------------


class TestReview:
    def test_review_lab_approve(self, client, db, doctor):
        user, profile = _make_patient(db)
        _grant_profile_consent(db, profile.id, doctor["user_id"])
        lab = LabResult(
            patient_id=profile.id, test_name="TG", value=3.0, status="high", verified_by_doctor=False
        )
        db.add(lab)
        db.commit()
        r = client.patch(
            f"{API}/doctor/queue/lab_result:{lab.id}/review",
            headers=_doctor_headers(doctor["user_id"]),
            json={"decision": "approved", "comment": "Đã xem"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == f"lab_result:{lab.id}"
        assert body["status"] == "approved"

    def test_review_care_plan_reject(self, client, db, doctor):
        user, profile = _make_patient(db)
        _grant_profile_consent(db, profile.id, doctor["user_id"])
        plan = CarePlan(patient_id=profile.id, title="Plan", status=CarePlanStatus.PENDING_REVIEW)
        db.add(plan)
        db.commit()
        r = client.patch(
            f"{API}/doctor/queue/care_plan:{plan.id}/review",
            headers=_doctor_headers(doctor["user_id"]),
            json={"decision": "rejected", "comment": "Chưa phù hợp"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "rejected"

    def test_review_ai_approve(self, client, db, doctor):
        user, profile = _make_patient(db)
        _grant_profile_consent(db, profile.id, doctor["user_id"])
        rec = _seed_ai_rec(
            db, patient_id=profile.id, doctor_user_id=doctor["user_id"], doctor_id=doctor["doctor_id"]
        )
        r = client.patch(
            f"{API}/doctor/queue/ai_session:{rec.id}/review",
            headers=_doctor_headers(doctor["user_id"]),
            json={"decision": "approved", "comment": "OK"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"

    def test_bad_composite_id_404(self, client, doctor):
        r = client.patch(
            f"{API}/doctor/queue/lab_result:nonexistent/review",
            headers=_doctor_headers(doctor["user_id"]),
            json={"decision": "approved", "comment": "x"},
        )
        assert r.status_code == 404

    def test_malformed_id_404(self, client, doctor):
        r = client.patch(
            f"{API}/doctor/queue/garbage/review",
            headers=_doctor_headers(doctor["user_id"]),
            json={"decision": "approved", "comment": "x"},
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# FIX 1 — server-side scope gate on review dispatch (403 + no dispatch)
# ---------------------------------------------------------------------------


class TestReviewScopeGate:
    def test_lab_review_denied_for_unrelated_patient(self, client, db, doctor):
        # Patient with NO consent and NO encounter to this doctor.
        user, profile = _make_patient(db, name="Secret Patient")
        lab = LabResult(
            patient_id=profile.id,
            test_name="TG",
            value=3.0,
            status="high",
            verified_by_doctor=False,
        )
        db.add(lab)
        db.commit()
        lab_id = lab.id

        r = client.patch(
            f"{API}/doctor/queue/lab_result:{lab_id}/review",
            headers=_doctor_headers(doctor["user_id"]),
            json={"decision": "approved", "comment": "x"},
        )
        assert r.status_code == 403
        # No PHI (patient name) leaked in the error body.
        assert "Secret Patient" not in r.text
        # No dispatch happened: the lab is UNCHANGED.
        db.expire_all()
        assert db.get(LabResult, lab_id).verified_by_doctor is False

    def test_care_plan_review_denied_for_unrelated_patient(self, client, db, doctor):
        user, profile = _make_patient(db, name="Secret Patient")
        plan = CarePlan(
            patient_id=profile.id, title="Plan", status=CarePlanStatus.PENDING_REVIEW
        )
        db.add(plan)
        db.commit()
        plan_id = plan.id

        r = client.patch(
            f"{API}/doctor/queue/care_plan:{plan_id}/review",
            headers=_doctor_headers(doctor["user_id"]),
            json={"decision": "rejected", "comment": "x"},
        )
        assert r.status_code == 403
        assert "Secret Patient" not in r.text
        db.expire_all()
        assert db.get(CarePlan, plan_id).status == CarePlanStatus.PENDING_REVIEW

    def test_ai_review_denied_for_unrelated_patient(self, client, db, doctor):
        user, profile = _make_patient(db, name="Secret Patient")
        # Pending AI rec but NO consent/encounter granted to this doctor.
        session = AISession(patient_id=profile.id, session_type="lab_explanation")
        db.add(session)
        db.flush()
        rec = AIClinicalRecommendation.create_from_ai(
            session_id=session.id,
            patient_id=profile.id,
            recommendation_type="lab_interpretation",
        )
        db.add(rec)
        db.commit()
        rec_id = rec.id

        r = client.patch(
            f"{API}/doctor/queue/ai_session:{rec_id}/review",
            headers=_doctor_headers(doctor["user_id"]),
            json={"decision": "approved", "comment": "x"},
        )
        assert r.status_code == 403
        assert "Secret Patient" not in r.text
        db.expire_all()
        assert db.get(AIClinicalRecommendation, rec_id).status == "pending_review"


# ---------------------------------------------------------------------------
# FIX 2 — review comment + internal_note persisted (encrypted), round-trip
# ---------------------------------------------------------------------------


class TestReviewDecisionPersistence:
    def _decisions(self, db, *, item_id: str):
        from app.models.care import DoctorReviewDecision

        return (
            db.query(DoctorReviewDecision)
            .filter(DoctorReviewDecision.item_id == item_id)
            .all()
        )

    def test_lab_decision_persisted(self, client, db, doctor):
        user, profile = _make_patient(db)
        _grant_profile_consent(db, profile.id, doctor["user_id"])
        lab = LabResult(
            patient_id=profile.id, test_name="TG", value=3.0, status="high",
            verified_by_doctor=False,
        )
        db.add(lab)
        db.commit()
        lab_id = lab.id
        r = client.patch(
            f"{API}/doctor/queue/lab_result:{lab_id}/review",
            headers=_doctor_headers(doctor["user_id"]),
            json={"decision": "approved", "comment": "Đã xem", "internal_note": "nội bộ"},
        )
        assert r.status_code == 200, r.text
        db.expire_all()
        rows = self._decisions(db, item_id=lab_id)
        assert len(rows) == 1
        assert rows[0].decision == "approved"
        assert rows[0].comment == "Đã xem"
        assert rows[0].internal_note == "nội bộ"

    def test_care_plan_decision_persisted(self, client, db, doctor):
        user, profile = _make_patient(db)
        _grant_profile_consent(db, profile.id, doctor["user_id"])
        plan = CarePlan(
            patient_id=profile.id, title="Plan", status=CarePlanStatus.PENDING_REVIEW
        )
        db.add(plan)
        db.commit()
        plan_id = plan.id
        r = client.patch(
            f"{API}/doctor/queue/care_plan:{plan_id}/review",
            headers=_doctor_headers(doctor["user_id"]),
            json={"decision": "rejected", "comment": "Chưa phù hợp", "internal_note": "ghi chú"},
        )
        assert r.status_code == 200, r.text
        db.expire_all()
        rows = self._decisions(db, item_id=plan_id)
        assert len(rows) == 1
        assert rows[0].decision == "rejected"
        assert rows[0].comment == "Chưa phù hợp"
        assert rows[0].internal_note == "ghi chú"

    def test_ai_decision_persisted(self, client, db, doctor):
        user, profile = _make_patient(db)
        _grant_profile_consent(db, profile.id, doctor["user_id"])
        rec = _seed_ai_rec(
            db, patient_id=profile.id, doctor_user_id=doctor["user_id"],
            doctor_id=doctor["doctor_id"],
        )
        rec_id = rec.id
        r = client.patch(
            f"{API}/doctor/queue/ai_session:{rec_id}/review",
            headers=_doctor_headers(doctor["user_id"]),
            json={"decision": "approved", "comment": "OK", "internal_note": "riêng tư"},
        )
        assert r.status_code == 200, r.text
        db.expire_all()
        rows = self._decisions(db, item_id=rec_id)
        assert len(rows) == 1
        assert rows[0].decision == "approved"
        assert rows[0].comment == "OK"
        assert rows[0].internal_note == "riêng tư"


# ---------------------------------------------------------------------------
# FIX 3 — roster masks PHI for narrow/unrelated consent
# ---------------------------------------------------------------------------


class TestRosterPhiMasking:
    def test_narrow_consent_masks_phi_and_not_searchable(self, client, db, doctor):
        user, profile = _make_patient(
            db, risk="high", name="Hidden Name", email="hidden@example.vn"
        )
        _grant_narrow_consent(db, profile.id, doctor["user_id"])

        r = client.get(f"{API}/doctor/patients", headers=_doctor_headers(doctor["user_id"]))
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["id"] == profile.id
        assert item["full_name"] is None
        assert item["email"] == ""
        assert item["risk_segment"] is None
        assert item["consented"] is False

        # Searching by the real (masked) name must NOT surface the patient.
        r2 = client.get(
            f"{API}/doctor/patients?search=Hidden", headers=_doctor_headers(doctor["user_id"])
        )
        assert r2.json()["total"] == 0


# ---------------------------------------------------------------------------
# P1: queue must not leak patient_name under a narrow (non-care) consent —
# symmetric to the roster mask. A patient visible only via ai_use consent
# still appears in the queue (the doctor may act) but their name must be None.
# ---------------------------------------------------------------------------


class TestQueuePhiMasking:
    def test_queue_masks_patient_name_under_narrow_consent(self, client, db, doctor):
        user, profile = _make_patient(db, name="Hidden Queue Name")
        _grant_narrow_consent(db, profile.id, doctor["user_id"])  # ai_use only
        db.add(
            LabResult(
                patient_id=profile.id, test_name="HbA1c", value=8.0, status="high",
                verified_by_doctor=False,
            )
        )
        db.commit()

        r = client.get(f"{API}/doctor/queue", headers=_doctor_headers(doctor["user_id"]))
        assert r.status_code == 200
        body = r.json()
        # Item is visible (doctor may act) ...
        assert body["total"] == 1
        item = body["items"][0]
        assert item["item_type"] == "lab_result"
        # ... but the name is masked (PHI gate), never the real name.
        assert item["patient_name"] is None
        assert "Hidden Queue Name" not in r.text

    def test_review_response_masks_patient_name_under_narrow_consent(self, client, db, doctor):
        user, profile = _make_patient(db, name="Hidden Review Name")
        _grant_narrow_consent(db, profile.id, doctor["user_id"])  # ai_use only
        lab = LabResult(
            patient_id=profile.id, test_name="TG", value=3.0, status="high", verified_by_doctor=False
        )
        db.add(lab)
        db.commit()

        # Narrow consent grants visibility, so the scope gate allows the action,
        # but the review response must still mask the name.
        r = client.patch(
            f"{API}/doctor/queue/lab_result:{lab.id}/review",
            headers=_doctor_headers(doctor["user_id"]),
            json={"decision": "approved", "comment": "Đã xem"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "approved"
        assert body["patient_name"] is None
        assert "Hidden Review Name" not in r.text
