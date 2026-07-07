"""Tests for the admin AI-safety console — GET/PATCH /admin/ai-sessions.

Covers:
  - RBAC: patient/doctor → 403, unauthenticated → 401
  - Empty DB → 200 with {total: 0, flagged_count: 0, items: []} (frontend
    renders the empty state, not the error state)
  - Safety classification from MetoAuditLog signals (safe/caution/urgent)
  - Filters: safety_level=urgent, reviewed, pagination limit/offset
  - PATCH review: persists reviewer + timestamp, idempotent, 404 for unknown id
  - MFA: these routes carry the same require_mfa gate as every other /admin
    route — no route-specific exception. That gate (and the enrollment
    middleware) is a global no-op while Settings.mfa_enforcement_enabled is
    False (default — temporary relaxed policy for the build/test phase);
    the `mfa_enforced` fixture flips it on to prove the mandatory-MFA
    behavior still exists and applies identically to ai-sessions.
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


@pytest.fixture
def doctor_user(db):
    user = User(
        email=f"ai-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. Test",
    )
    db.add(user)
    db.commit()
    return user


def _second_admin(db) -> User:
    user = User(
        email=f"ai-admin2-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.SUPER_ADMIN,
        full_name="Second Admin",
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


def test_doctor_gets_403(client, doctor_user):
    token = create_access_token(subject=doctor_user.id, role="doctor", mfa=True)
    r = client.get(BASE, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# MFA is NOT required for these two routes (finding 1)
# ---------------------------------------------------------------------------


def test_admin_without_mfa_can_list_sessions(client, db):
    """GET must succeed for an admin whose session was never MFA-verified."""
    user = User(
        email=f"ai-nomfa-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.SUPER_ADMIN,
        full_name="No MFA Admin",
    )
    db.add(user)
    db.commit()
    token = create_access_token(
        subject=user.id, role="super_admin", mfa=False, mfa_enrollment_required=False
    )
    r = client.get(BASE, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_admin_without_mfa_can_patch_review(client, db, patient_user):
    user = User(
        email=f"ai-nomfa2-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.INTERNAL_ADMIN,
        full_name="No MFA Admin 2",
    )
    db.add(user)
    db.commit()
    conv = _seed_conversation(db, patient_user, flagged=True)
    token = create_access_token(
        subject=user.id, role="internal_admin", mfa=False, mfa_enrollment_required=False
    )
    r = client.patch(f"{BASE}/{conv.id}/review", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["reviewed_at"] is not None


def test_ai_sessions_not_blocked_by_enrollment_claim_by_default(client, db):
    """MFA enforcement is OFF by default (temporary relaxed policy for the
    build/test phase — Settings.mfa_enforcement_enabled). While off, the
    MfaEnrollmentMiddleware passes every path through unconditionally, even
    a token that (incorrectly, e.g. minted before the flag was disabled)
    still carries mfa_enrollment_required=True. ai-sessions behaves exactly
    like every other admin route here — no route-specific exception."""
    user = User(
        email=f"ai-unenrolled-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.SUPER_ADMIN,
        full_name="Unenrolled Admin",
    )
    db.add(user)
    db.commit()
    token = create_access_token(
        subject=user.id, role="super_admin", mfa=False, mfa_enrollment_required=True
    )
    r = client.get(BASE, headers={"Authorization": f"Bearer {token}"})
    other_admin_route = client.get(
        "/api/v1/admin/stats", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    assert other_admin_route.status_code == 200


def test_ai_sessions_blocked_same_as_other_admin_routes_when_enforced(
    client, db, mfa_enforced
):
    """With MCP_MFA_ENFORCEMENT_ENABLED=true, an admin who owes MFA
    enrollment is blocked on /admin/ai-sessions exactly like any other admin
    route — proving there is still no route-specific exception, just the
    global flag."""
    user = User(
        email=f"ai-unenrolled2-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.SUPER_ADMIN,
        full_name="Unenrolled Admin 2",
    )
    db.add(user)
    db.commit()
    token = create_access_token(
        subject=user.id, role="super_admin", mfa=False, mfa_enrollment_required=True
    )
    r = client.get(BASE, headers={"Authorization": f"Bearer {token}"})
    other_admin_route = client.get(
        "/api/v1/admin/stats", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 403
    assert r.json().get("code") == "mfa_enrollment_required"
    assert other_admin_route.status_code == 403
    assert other_admin_route.json().get("code") == "mfa_enrollment_required"


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


def test_filter_and_pagination_combined(client, db, admin_headers, patient_user):
    """safety_level filter AND limit/offset must compose: total reflects the
    filtered count, and the page is sliced from the filtered set — not the
    unfiltered one."""
    _seed_conversation(db, patient_user)  # safe — excluded by the filter
    urgents = [_seed_conversation(db, patient_user, escalated=True) for _ in range(3)]

    r = client.get(f"{BASE}?safety_level=urgent&limit=2&offset=1", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3  # filtered count, not 4
    assert len(body["items"]) == 2  # items[1:3] of the 3-item filtered set
    assert all(item["safety_level"] == "urgent" for item in body["items"])
    urgent_ids = {c.id for c in urgents}
    assert all(item["id"] in urgent_ids for item in body["items"])


def test_severity_precedence_urgent_beats_caution_across_events(
    client, db, admin_headers, patient_user
):
    """A single conversation can have multiple audit events. If ANY event
    escalated, the conversation is urgent overall — even if an earlier event
    was merely flagged (caution)."""
    conv = MetoConversation(user_id=patient_user.id, screen_id="dashboard", title="c")
    db.add(conv)
    db.flush()
    db.add(
        MetoAuditLog(
            user_id=patient_user.id,
            conversation_id=conv.id,
            action="chat_message",
            safety_flags_detected=True,
            escalation_triggered=False,
        )
    )
    db.add(
        MetoAuditLog(
            user_id=patient_user.id,
            conversation_id=conv.id,
            action="chat_message",
            safety_flags_detected=False,
            escalation_triggered=True,
        )
    )
    db.commit()

    r = client.get(BASE, headers=admin_headers)
    assert r.status_code == 200
    item = next(i for i in r.json()["items"] if i["id"] == conv.id)
    assert item["safety_level"] == "urgent"
    assert item["flag"] == "urgent_response"


# ---------------------------------------------------------------------------
# PHI leakage (finding 2) — conversation title/content must never appear
# ---------------------------------------------------------------------------


def test_explanation_type_never_leaks_conversation_title(client, db, admin_headers, patient_user):
    """Regression: conv.title is auto-generated from the user's first message
    and can itself be PHI (e.g. a symptom description). It must never be
    returned as explanation_type or anywhere else in the list response."""
    sensitive_text = "Bệnh nhân bị đau ngực dữ dội, khó thở, tiền sử tăng huyết áp"
    conv = _seed_conversation(db, patient_user, escalated=True, title=sensitive_text)

    r = client.get(BASE, headers=admin_headers)
    assert r.status_code == 200
    assert sensitive_text not in r.text

    item = next(i for i in r.json()["items"] if i["id"] == conv.id)
    assert item["explanation_type"] in {"none", "safety_flag", "urgent_response"}
    assert sensitive_text not in item["explanation_type"]


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


def test_concurrent_review_does_not_overwrite_reviewer_or_duplicate_audit(
    client, db, admin_headers, patient_user
):
    """Two admins racing for the same session: only the winner's identity is
    recorded, the loser's request is a no-op (not an overwrite), and exactly
    one audit record is created — never two.

    This exercises the same atomic-UPDATE guard that protects true
    concurrent requests: the second call finds reviewed_at already set
    (rowcount=0) and must not touch the row or write an audit entry.
    """
    from app.models.governance import AuditLog

    second_admin = _second_admin(db)
    second_token = create_access_token(subject=second_admin.id, role="super_admin", mfa=True)
    second_headers = {"Authorization": f"Bearer {second_token}"}

    conv = _seed_conversation(db, patient_user, flagged=True)

    r1 = client.patch(f"{BASE}/{conv.id}/review", headers=admin_headers)
    r2 = client.patch(f"{BASE}/{conv.id}/review", headers=second_headers)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["reviewed_by"] == "Safety Admin"
    # NOT overwritten to "Second Admin" — the first reviewer's identity wins.
    assert r2.json()["reviewed_by"] == "Safety Admin"
    assert r1.json()["reviewed_at"] == r2.json()["reviewed_at"]

    reviews = (
        db.query(AuditLog)
        .filter(AuditLog.resource_id == conv.id, AuditLog.action == "ai_session.review")
        .all()
    )
    assert len(reviews) == 1
    assert reviews[0].actor_id != second_admin.id

    db.refresh(conv)
    assert conv.reviewed_by_user_id != second_admin.id
