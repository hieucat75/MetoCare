"""T23 API tests — Notification Scaffold (10 tests).

Endpoints tested:
  POST   /api/v1/notifications              (admin creates)
  GET    /api/v1/notifications              (own list)
  PATCH  /api/v1/notifications/{id}/read   (mark single read)
  POST   /api/v1/notifications/read-all    (mark all read)

Test cases:
  1.  test_admin_creates_notification_for_patient         → 201
  2.  test_patient_lists_own_notifications                → 200
  3.  test_patient_lists_unread_only                      → filtered
  4.  test_patient_marks_notification_as_read             → 200, is_read=True
  5.  test_patient_cannot_mark_another_users_notification → 403
  6.  test_patient_marks_all_as_read                      → 200, count returned
  7.  test_doctor_lists_own_notifications                 → 200
  8.  test_non_admin_cannot_create_notification           → 403
  9.  test_ai_service_blocked_on_all_endpoints            → 403
  10. test_unauthenticated_returns_401                    → 401
"""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.notification import Notification
from app.models.user import User, UserRole
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

_BASE = "/api/v1/notifications"


def _notif_url() -> str:
    return _BASE


def _read_url(notif_id: str) -> str:
    return f"{_BASE}/{notif_id}/read"


def _read_all_url() -> str:
    return f"{_BASE}/read-all"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_ctx():
    """INTERNAL_ADMIN JWT headers + user_id."""
    admin_id = f"t23-admin-{os.urandom(4).hex()}"
    token = create_access_token(subject=admin_id, role="internal_admin", mfa=True)
    return {
        "user_id": admin_id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def patient_ctx(db):
    """PATIENT user + JWT."""
    user = User(
        email=f"t23-patient-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="T23 Patient",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="patient")
    return {
        "user_id": user.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def another_patient_ctx(db):
    """A second, unrelated PATIENT user + JWT."""
    user = User(
        email=f"t23-patient2-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="T23 Patient 2",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="patient")
    return {
        "user_id": user.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def doctor_ctx(db):
    """DOCTOR user + JWT (MFA verified)."""
    user = User(
        email=f"t23-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="T23 Doctor",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="doctor", mfa=True)
    return {
        "user_id": user.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def _seed_notification(
    db,
    *,
    user_id: str,
    is_read: bool = False,
    title: str = "Test Notification",
    body: str = "This is a test notification.",
    type: str = "system",
) -> Notification:
    """Directly seed a Notification row (bypasses service layer)."""
    notif = Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        is_read=is_read,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


# ---------------------------------------------------------------------------
# 1. Admin creates notification for patient → 201
# ---------------------------------------------------------------------------


def test_admin_creates_notification_for_patient(
    client: TestClient, admin_ctx, patient_ctx
):
    """INTERNAL_ADMIN POSTs to /notifications → 201 with correct payload."""
    payload = {
        "user_id": patient_ctx["user_id"],
        "type": "appointment_reminder",
        "title": "Upcoming Appointment",
        "body": "You have an appointment tomorrow at 10:00.",
        "metadata": {"appointment_id": "appt-001"},
    }
    r = client.post(_notif_url(), json=payload, headers=admin_ctx["headers"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user_id"] == patient_ctx["user_id"]
    assert body["type"] == "appointment_reminder"
    assert body["title"] == "Upcoming Appointment"
    assert body["is_read"] is False
    assert "id" in body
    assert "created_at" in body


# ---------------------------------------------------------------------------
# 2. Patient lists own notifications → 200
# ---------------------------------------------------------------------------


def test_patient_lists_own_notifications(client: TestClient, db, patient_ctx):
    """PATIENT GETs /notifications → 200 with their own notifications only."""
    _seed_notification(db, user_id=patient_ctx["user_id"], title="Notif 1")
    _seed_notification(db, user_id=patient_ctx["user_id"], title="Notif 2")

    r = client.get(_notif_url(), headers=patient_ctx["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    # At least the 2 we just seeded
    assert len(body) >= 2
    for item in body:
        assert item["user_id"] == patient_ctx["user_id"]


# ---------------------------------------------------------------------------
# 3. Patient lists unread only (?unread_only=true) → filtered
# ---------------------------------------------------------------------------


def test_patient_lists_unread_only(client: TestClient, db, patient_ctx):
    """?unread_only=true returns only unread notifications."""
    _seed_notification(db, user_id=patient_ctx["user_id"], is_read=False, title="Unread")
    _seed_notification(db, user_id=patient_ctx["user_id"], is_read=True, title="Read")

    r = client.get(
        _notif_url(),
        params={"unread_only": "true"},
        headers=patient_ctx["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    # All returned items must be unread
    for item in body:
        assert item["is_read"] is False


# ---------------------------------------------------------------------------
# 4. Patient marks notification as read → 200, is_read=True
# ---------------------------------------------------------------------------


def test_patient_marks_notification_as_read(client: TestClient, db, patient_ctx):
    """PATCH /notifications/{id}/read → 200 with is_read=True, read_at set."""
    notif = _seed_notification(
        db, user_id=patient_ctx["user_id"], is_read=False, title="Mark Me Read"
    )

    r = client.patch(_read_url(notif.id), headers=patient_ctx["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == notif.id
    assert body["is_read"] is True
    assert body["read_at"] is not None


# ---------------------------------------------------------------------------
# 5. Patient cannot mark another user's notification → 403
# ---------------------------------------------------------------------------


def test_patient_cannot_mark_another_users_notification(
    client: TestClient, db, patient_ctx, another_patient_ctx
):
    """PATCH notification owned by another user → 403 (ownership enforced)."""
    # Seed a notification for *another* patient
    notif = _seed_notification(
        db,
        user_id=another_patient_ctx["user_id"],
        title="Not Yours",
    )

    r = client.patch(_read_url(notif.id), headers=patient_ctx["headers"])
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 6. Patient marks all as read → 200, count returned
# ---------------------------------------------------------------------------


def test_patient_marks_all_as_read(client: TestClient, db, patient_ctx):
    """POST /notifications/read-all → 200, {"count": N} where N > 0."""
    _seed_notification(db, user_id=patient_ctx["user_id"], is_read=False, title="Unread A")
    _seed_notification(db, user_id=patient_ctx["user_id"], is_read=False, title="Unread B")

    r = client.post(_read_all_url(), headers=patient_ctx["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert "count" in body
    assert body["count"] >= 2  # at minimum the 2 we just seeded


# ---------------------------------------------------------------------------
# 7. Doctor lists own notifications → 200
# ---------------------------------------------------------------------------


def test_doctor_lists_own_notifications(client: TestClient, db, doctor_ctx):
    """DOCTOR GETs /notifications → 200 (their own only)."""
    _seed_notification(db, user_id=doctor_ctx["user_id"], title="Doctor Notif")

    r = client.get(_notif_url(), headers=doctor_ctx["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    for item in body:
        assert item["user_id"] == doctor_ctx["user_id"]


# ---------------------------------------------------------------------------
# 8. Non-admin cannot create notification → 403
# ---------------------------------------------------------------------------


def test_non_admin_cannot_create_notification(
    client: TestClient, patient_ctx, another_patient_ctx
):
    """PATIENT POSTs to /notifications → 403 (admin-only operation)."""
    payload = {
        "user_id": another_patient_ctx["user_id"],
        "type": "system",
        "title": "Unauthorized Create",
        "body": "This should not be created.",
    }
    r = client.post(_notif_url(), json=payload, headers=patient_ctx["headers"])
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 9. AI_SERVICE → 403 on all notification endpoints
# ---------------------------------------------------------------------------


def test_ai_service_blocked_on_all_endpoints(client: TestClient, db, patient_ctx):
    """AI_SERVICE role receives 403 on every notification endpoint."""
    ai_id = f"t23-ai-{os.urandom(4).hex()}"
    ai_token = create_access_token(subject=ai_id, role="ai_service")
    ai_headers = {"Authorization": f"Bearer {ai_token}"}

    # Seed a notification owned by an existing patient so the ID is valid
    notif = _seed_notification(db, user_id=patient_ctx["user_id"])

    # GET /notifications
    r = client.get(_notif_url(), headers=ai_headers)
    assert r.status_code == 403, f"GET expected 403, got {r.status_code}"

    # PATCH /notifications/{id}/read
    r = client.patch(_read_url(notif.id), headers=ai_headers)
    assert r.status_code == 403, f"PATCH read expected 403, got {r.status_code}"

    # POST /notifications/read-all
    r = client.post(_read_all_url(), headers=ai_headers)
    assert r.status_code == 403, f"POST read-all expected 403, got {r.status_code}"

    # POST /notifications (create)
    r = client.post(
        _notif_url(),
        json={
            "user_id": patient_ctx["user_id"],
            "type": "system",
            "title": "AI Attempt",
            "body": "Should be blocked.",
        },
        headers=ai_headers,
    )
    assert r.status_code == 403, f"POST create expected 403, got {r.status_code}"


# ---------------------------------------------------------------------------
# 10. Unauthenticated → 401
# ---------------------------------------------------------------------------


def test_unauthenticated_returns_401(client: TestClient):
    """Requests without a bearer token → 401 on all notification endpoints."""
    r = client.get(_notif_url())
    assert r.status_code == 401, r.text

    r = client.post(_read_all_url())
    assert r.status_code == 401, r.text

    r = client.post(
        _notif_url(),
        json={
            "user_id": "x",
            "type": "system",
            "title": "x",
            "body": "x",
        },
    )
    assert r.status_code == 401, r.text
