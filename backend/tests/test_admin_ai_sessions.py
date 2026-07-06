"""Tests for the admin AI-safety console — GET/PATCH /admin/ai-sessions.

Covers:
  - RBAC: patient/doctor → 403, unauthenticated → 401
  - Empty DB → 200 with {total: 0, flagged_count: 0, items: []} (frontend
    renders the empty state, not the error state)
  - Safety classification from MetoAuditLog signals (safe/caution/urgent)
  - Filters: safety_level=urgent, reviewed, pagination limit/offset
  - PATCH review: persists reviewer + timestamp, idempotent, 404 for unknown id
"""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.meto import MetoAuditLog, MetoConversation
from app.models.user import User, UserRole

BASE = "/api/v1/admin/ai-sessions"


@pytest.fixture(autouse=True)
def _clean_meto_tables(db):
    """The shared test DB persists across tests; count assertions need a
    clean slate for Meto conversations/audit rows."""
    db.query(MetoAuditLog).delete()
    db.query(MetoConversation).delete()
    db.commit()
    yield


@pytest.fixture
def admin_headers(db):
    user = User(
        email=f"ai-admin-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.SUPER_ADMIN,
        full_name="Safety Admin",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="super_admin", mfa=True)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def patient_user(db):
    user = User(
        phone=f"+8490{os.urandom(3).hex()[:7]}",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Bệnh nhân Meto",
    )
    db.add(user)
    db.commit()
    return user


def _seed_conversation(
    db,
    user: User,
    *,
    escalated: bool = False,
    flagged: bool = False,
    title: str | None = "Hỏi về đường huyết",
) -> MetoConversation:
    conv = MetoConversation(user_id=user.id, screen_id="dashboard", title=title)
    db.add(conv)
    db.flush()
    db.add(
        MetoAuditLog(
            user_id=user.id,
            conversation_id=conv.id,
            action="chat_message",
            safety_flags_detected=flagged,
            escalation_triggered=escalated,
        )
    )
    db.commit()
    return conv


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


def test_unauthenticated_gets_401(client):
    assert client.get(BASE).status_code == 401


def test_patient_gets_403(client, patient_user):
    token = create_access_token(subject=patient_user.id, role="patient", mfa=True)
    r = client.get(BASE, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Listing + classification
# ---------------------------------------------------------------------------


def test_empty_db_returns_empty_list_not_error(client, admin_headers):
    r = client.get(BASE, headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body == {"total": 0, "flagged_count": 0, "items": []}


def test_sessions_classified_by_audit_signals(client, db, admin_headers, patient_user):
    safe = _seed_conversation(db, patient_user)
    caution = _seed_conversation(db, patient_user, flagged=True)
    urgent = _seed_conversation(db, patient_user, escalated=True, flagged=True)

    r = client.get(BASE, headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    by_id = {item["id"]: item for item in body["items"]}

    assert body["total"] == 3
    assert body["flagged_count"] == 2  # caution + urgent
    assert by_id[safe.id]["safety_level"] == "safe"
    assert by_id[safe.id]["flag"] == "none"
    assert by_id[caution.id]["safety_level"] == "caution"
    assert by_id[caution.id]["flag"] == "review_requested"
    assert by_id[urgent.id]["safety_level"] == "urgent"
    assert by_id[urgent.id]["flag"] == "urgent_response"
    assert by_id[urgent.id]["patient_name"] == "Bệnh nhân Meto"
    assert by_id[urgent.id]["reviewed_at"] is None


def test_filter_safety_level_urgent(client, db, admin_headers, patient_user):
    _seed_conversation(db, patient_user)
    urgent = _seed_conversation(db, patient_user, escalated=True)

    r = client.get(f"{BASE}?safety_level=urgent", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == urgent.id


def test_pagination_limit_offset(client, db, admin_headers, patient_user):
    for _ in range(3):
        _seed_conversation(db, patient_user)

    r = client.get(f"{BASE}?limit=2&offset=2", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------


def test_review_marks_session_reviewed(client, db, admin_headers, patient_user):
    conv = _seed_conversation(db, patient_user, flagged=True)

    r = client.patch(f"{BASE}/{conv.id}/review", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["reviewed_at"] is not None
    assert body["reviewed_by"] == "Safety Admin"

    # Reviewed filter now excludes/includes it correctly.
    unreviewed = client.get(f"{BASE}?reviewed=false", headers=admin_headers).json()
    assert conv.id not in [i["id"] for i in unreviewed["items"]]


def test_review_is_idempotent(client, db, admin_headers, patient_user):
    conv = _seed_conversation(db, patient_user)
    first = client.patch(f"{BASE}/{conv.id}/review", headers=admin_headers).json()
    second = client.patch(f"{BASE}/{conv.id}/review", headers=admin_headers).json()
    assert first["reviewed_at"] == second["reviewed_at"]


def test_review_unknown_id_404(client, admin_headers):
    r = client.patch(f"{BASE}/does-not-exist/review", headers=admin_headers)
    assert r.status_code == 404
