"""Per-category Meto consent (BRD §J) — versioned, revocable, fail-closed, audited.

Exercises the REAL consent gate (opts out of the default grant-all fixture via the
module-level real_consent marker).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from app.ai.consent_policy import (
    CATEGORY_AI_PROCESSING,
    CATEGORY_HEALTH_RECORDS,
    CONSENT_CATEGORIES,
    CONSENT_POLICY_VERSION,
    is_granted,
)
from app.ai.context.schemas import ScreenContext
from app.main import app
from app.models.meto import MetoAuditLog, MetoConsent
from app.services.meto_chat import MetoChatService
from fastapi.testclient import TestClient

pytestmark = pytest.mark.real_consent


def _svc() -> MetoChatService:
    return MetoChatService(MagicMock())


def test_get_consent_lists_all_categories_default_false(db, patient):
    statuses = _svc().get_consent(db, patient["user_id"])
    assert {s.context_type for s in statuses} == set(CONSENT_CATEGORIES)
    assert all(not s.granted for s in statuses)  # nothing granted yet
    assert all(s.purpose for s in statuses)  # purpose-specific text present
    assert all(s.policy_version == CONSENT_POLICY_VERSION for s in statuses)


def test_grant_then_revoke_updates_effective_status(db, patient):
    svc = _svc()
    uid = patient["user_id"]
    svc.update_consent(db, uid, CATEGORY_HEALTH_RECORDS, True)
    assert is_granted(db, uid, CATEGORY_HEALTH_RECORDS)
    svc.update_consent(db, uid, CATEGORY_HEALTH_RECORDS, False)
    assert not is_granted(db, uid, CATEGORY_HEALTH_RECORDS)  # revocation blocks future use


def test_unknown_category_rejected(db, patient):
    with pytest.raises(ValueError):
        _svc().update_consent(db, patient["user_id"], "not_a_category", True)


def test_stale_policy_version_forces_reconsent(db, patient):
    svc = _svc()
    uid = patient["user_id"]
    svc.update_consent(db, uid, CATEGORY_HEALTH_RECORDS, True)
    row = (
        db.query(MetoConsent)
        .filter(MetoConsent.user_id == uid, MetoConsent.context_type == CATEGORY_HEALTH_RECORDS)
        .first()
    )
    row.policy_version = "0.9"  # simulate a policy bump — grant is now stale
    db.commit()
    assert not is_granted(db, uid, CATEGORY_HEALTH_RECORDS)


def test_audit_records_grant_without_phi(db, patient):
    uid = patient["user_id"]
    _svc().update_consent(db, uid, CATEGORY_AI_PROCESSING, True)
    logs = (
        db.query(MetoAuditLog)
        .filter(MetoAuditLog.user_id == uid, MetoAuditLog.action == "consent_granted")
        .all()
    )
    assert logs
    log = logs[-1]
    assert log.context_types == [CATEGORY_AI_PROCESSING]  # category key only
    assert log.details.get("policy_version") == CONSENT_POLICY_VERSION
    assert set(log.details.keys()) <= {"policy_version"}  # no PHI keys


def test_api_grant_revoke_and_unknown_category(db, patient):
    client = TestClient(app)
    headers = patient["headers"]

    r = client.get("/api/v1/meto/consent", headers=headers)
    assert r.status_code == 200
    assert {s["context_type"] for s in r.json()} == set(CONSENT_CATEGORIES)

    r = client.post(
        "/api/v1/meto/consent",
        headers=headers,
        json={"context_type": CATEGORY_AI_PROCESSING, "granted": True},
    )
    assert r.status_code == 200

    r = client.get("/api/v1/meto/consent", headers=headers)
    granted = {s["context_type"] for s in r.json() if s["granted"]}
    assert CATEGORY_AI_PROCESSING in granted

    r = client.post(
        "/api/v1/meto/consent",
        headers=headers,
        json={"context_type": "bogus", "granted": True},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_chat_master_gate_blocks_without_ai_processing_consent(db, patient):
    resp = await _svc().chat(
        db=db,
        user_id=patient["user_id"],
        conversation_id=None,
        message="Xin chào Meto",
        screen_context=ScreenContext(screen_id="dashboard"),
    )
    assert resp.consent_required is True
    assert CATEGORY_AI_PROCESSING in resp.missing_consents
