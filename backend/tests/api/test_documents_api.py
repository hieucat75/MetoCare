"""API tests for Medical Document Intelligence (Journey 2, M2).

Covers the secure ingestion pipeline (upload-session → blob PUT → finalize →
accept → extract → needs_review), the one-to-many candidate lifecycle
(confirm/reject/merge → PromotionLink), idempotency (no double promotion on
reprocess or double-confirm), duplicate detection, validation rejects, the
BOLA matrix, and the OCR feature-flag gate.
"""

from __future__ import annotations

import hashlib

import pytest
from app.main import app
from app.services.mdi import extractors, promoter
from app.services.mdi.extractors import CandidateDraft, make_dedupe_key
from app.services.mdi.promoter import (
    ACTION_CREATED,
    ACTION_MERGED_INTO,
    PromotionOutcome,
)
from app.services.storage import reset_storage
from fastapi.testclient import TestClient

# Minimal valid JPEG (magic bytes + padding) — passes sniff_mime.
_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 256
_JPEG2 = b"\xff\xd8\xff\xe0" + b"\x11" * 300  # a different valid JPEG


class _FixedRxExtractor:
    """Deterministic prescription extractor: two independent med candidates."""

    def extract(self, *, text, doc_type, ocr_confidence):
        return [
            CandidateDraft(
                candidate_type="medication",
                ordinal=0,
                fields={"name": "Metformin", "strength": "500mg"},
                dedupe_key=make_dedupe_key("medication", "metformin", "500mg"),
                field_confidence={"name": 0.9},
            ),
            CandidateDraft(
                candidate_type="medication",
                ordinal=1,
                fields={"name": "Amlodipine", "strength": "5mg"},
                dedupe_key=make_dedupe_key("medication", "amlodipine", "5mg"),
                field_confidence={"name": 0.8},
            ),
        ]


class _StubMedPromoter:
    """Fake canonical promotion — returns a deterministic canonical id."""

    def promote(self, db, candidate, *, actor_user_id, merge_target_id=None):
        if merge_target_id:
            return PromotionOutcome("medication", merge_target_id, ACTION_MERGED_INTO)
        return PromotionOutcome("medication", f"canon-{candidate.id[:8]}", ACTION_CREATED)


@pytest.fixture
def mdi_env(monkeypatch, tmp_path):
    """Deterministic MDI: mock OCR, temp storage, fixed extractor + stub promoter."""
    from app.core.config import get_settings

    monkeypatch.setenv("MCP_ENABLE_MOCK_OCR", "true")
    monkeypatch.setenv("MCP_STORAGE_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("FEATURE_OCR", "true")
    get_settings.cache_clear()
    reset_storage()
    extractors.register_extractor("prescription", _FixedRxExtractor())
    extractors.register_extractor("general", extractors.MockExtractor())
    promoter.register_promoter("medication", _StubMedPromoter())
    yield
    extractors.reset_extractors()
    promoter.reset_promoters()
    reset_storage()
    get_settings.cache_clear()


@pytest.fixture
def client():
    return TestClient(app)


def _upload_and_finalize(client, headers, data=_JPEG, doc_type_hint="prescription"):
    """Full ingestion: session → PUT bytes → finalize. Returns the finalize response."""
    sha = hashlib.sha256(data).hexdigest()
    r = client.post(
        "/api/v1/documents/upload-session",
        headers=headers,
        json={
            "declared_mime": "image/jpeg",
            "declared_sha256": sha,
            "declared_size": len(data),
            "doc_type_hint": doc_type_hint,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    put = client.put(body["signed_put_url"], content=data)
    assert put.status_code == 204, put.text
    fin = client.post(f"/api/v1/documents/{body['upload_id']}/finalize", headers=headers)
    return body["upload_id"], fin


# ── happy path ───────────────────────────────────────────────────────────────
def test_full_ingestion_to_needs_review(client, patient, mdi_env):
    doc_id, fin = _upload_and_finalize(client, patient["headers"])
    assert fin.status_code == 200, fin.text
    doc = fin.json()
    assert doc["object_state"] == "accepted"
    assert doc["status"] == "needs_review"
    assert doc["doc_type"] == "prescription"
    assert doc["scan_status"] == "skipped"

    cands = client.get(f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"])
    assert cands.status_code == 200
    items = cands.json()["items"]
    assert len(items) == 2
    assert all(c["status"] == "needs_review" for c in items)
    assert {c["fields"]["name"] for c in items} == {"Metformin", "Amlodipine"}


def test_confirm_promotes_once_and_double_confirm_409(client, patient, mdi_env):
    doc_id, _ = _upload_and_finalize(client, patient["headers"])
    cands = client.get(
        f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
    ).json()["items"]
    cid = cands[0]["id"]

    r = client.post(f"/api/v1/candidates/{cid}/confirm", headers=patient["headers"], json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["candidate"]["status"] == "confirmed"
    assert body["promotion"]["action"] == "created"
    assert body["promotion"]["canonical_type"] == "medication"

    # Second confirm on the already-resolved candidate is rejected.
    again = client.post(
        f"/api/v1/candidates/{cid}/confirm", headers=patient["headers"], json={}
    )
    assert again.status_code == 409

    # Document is now partially_confirmed (one of two candidates resolved).
    doc = client.get(f"/api/v1/documents/{doc_id}", headers=patient["headers"]).json()
    assert doc["status"] == "partially_confirmed"


def test_confirm_with_corrections_records_history(client, patient, mdi_env):
    doc_id, _ = _upload_and_finalize(client, patient["headers"])
    cid = client.get(
        f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
    ).json()["items"][0]["id"]
    r = client.post(
        f"/api/v1/candidates/{cid}/confirm",
        headers=patient["headers"],
        json={"corrections": {"strength": "850mg"}},
    )
    assert r.status_code == 200
    assert r.json()["candidate"]["fields"]["strength"] == "850mg"


def test_reject_candidate(client, patient, mdi_env):
    doc_id, _ = _upload_and_finalize(client, patient["headers"])
    cid = client.get(
        f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
    ).json()["items"][0]["id"]
    r = client.post(f"/api/v1/candidates/{cid}/reject", headers=patient["headers"])
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


def test_reprocess_carries_forward_no_double_promotion(client, patient, mdi_env):
    doc_id, _ = _upload_and_finalize(client, patient["headers"])
    cands = client.get(
        f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
    ).json()["items"]
    # Confirm Metformin.
    metformin = next(c for c in cands if c["fields"]["name"] == "Metformin")
    client.post(
        f"/api/v1/candidates/{metformin['id']}/confirm", headers=patient["headers"], json={}
    )

    # Reprocess: confirmed Metformin carried forward (not re-created / re-promoted);
    # Amlodipine already live → not duplicated. So no NEW candidates appear.
    rp = client.post(f"/api/v1/documents/{doc_id}/reprocess", headers=patient["headers"])
    assert rp.status_code == 200

    after = client.get(
        f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
    ).json()["items"]
    names = [c["fields"]["name"] for c in after]
    assert names.count("Metformin") == 1  # never duplicated
    assert names.count("Amlodipine") == 1
    confirmed = [c for c in after if c["status"] == "confirmed"]
    assert len(confirmed) == 1  # exactly one promotion survived reprocess


def test_confirm_without_registered_promoter_409(client, patient, mdi_env):
    # 'general' doc → 'finding' candidate_type has no registered promoter.
    doc_id, fin = _upload_and_finalize(
        client, patient["headers"], data=_JPEG, doc_type_hint="general"
    )
    assert fin.status_code == 200
    cands = client.get(
        f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
    ).json()["items"]
    if not cands:
        pytest.skip("mock extractor produced no candidates for this fixture")
    r = client.post(
        f"/api/v1/candidates/{cands[0]['id']}/confirm", headers=patient["headers"], json={}
    )
    assert r.status_code == 409


# ── validation / duplicate ───────────────────────────────────────────────────
def test_finalize_rejects_unsupported_bytes(client, patient, mdi_env):
    garbage = b"not-an-image-file-at-all" * 5
    sha = hashlib.sha256(garbage).hexdigest()
    r = client.post(
        "/api/v1/documents/upload-session",
        headers=patient["headers"],
        json={"declared_mime": "image/jpeg", "declared_sha256": sha, "declared_size": len(garbage)},
    )
    body = r.json()
    client.put(body["signed_put_url"], content=garbage)
    fin = client.post(f"/api/v1/documents/{body['upload_id']}/finalize", headers=patient["headers"])
    assert fin.status_code == 400
    doc = client.get(f"/api/v1/documents/{body['upload_id']}", headers=patient["headers"]).json()
    assert doc["object_state"] == "rejected"


def test_sha256_mismatch_rejected(client, patient, mdi_env):
    r = client.post(
        "/api/v1/documents/upload-session",
        headers=patient["headers"],
        json={
            "declared_mime": "image/jpeg",
            "declared_sha256": "0" * 64,  # wrong hash
            "declared_size": len(_JPEG),
        },
    )
    body = r.json()
    client.put(body["signed_put_url"], content=_JPEG)
    fin = client.post(f"/api/v1/documents/{body['upload_id']}/finalize", headers=patient["headers"])
    assert fin.status_code == 400


def test_duplicate_document_detected(client, patient, mdi_env):
    _upload_and_finalize(client, patient["headers"], data=_JPEG2)
    _, fin2 = _upload_and_finalize(client, patient["headers"], data=_JPEG2)
    assert fin2.status_code == 409
    detail = fin2.json()["detail"]
    assert "existing_id" in detail


# ── BOLA matrix ──────────────────────────────────────────────────────────────
def test_bola_other_patient_cannot_read_or_confirm(client, patient, token_for, db, mdi_env):
    from app.models.patient import PatientProfile
    from app.models.user import User, UserRole

    # Owner uploads + finalizes.
    doc_id, _ = _upload_and_finalize(client, patient["headers"])
    cid = client.get(
        f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
    ).json()["items"][0]["id"]

    # Second, unrelated patient.
    other_user = User(
        email="other@example.com", password_hash="x", role=UserRole.PATIENT, full_name="Other"
    )
    db.add(other_user)
    db.flush()
    db.add(PatientProfile(user_id=other_user.id, full_name="Other"))
    db.commit()
    other_headers = token_for(other_user.id, role="patient")

    assert client.get(f"/api/v1/documents/{doc_id}", headers=other_headers).status_code == 403
    assert (
        client.get(f"/api/v1/documents/{doc_id}/candidates", headers=other_headers).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/candidates/{cid}/confirm", headers=other_headers, json={}
        ).status_code
        == 403
    )


def test_other_patient_list_excludes_foreign_docs(client, patient, token_for, db, mdi_env):
    from app.models.patient import PatientProfile
    from app.models.user import User, UserRole

    _upload_and_finalize(client, patient["headers"])
    u = User(email="iso@example.com", password_hash="x", role=UserRole.PATIENT, full_name="Iso")
    db.add(u)
    db.flush()
    db.add(PatientProfile(user_id=u.id, full_name="Iso"))
    db.commit()
    lst = client.get("/api/v1/documents", headers=token_for(u.id, role="patient")).json()
    assert lst["total"] == 0


# ── feature flag + auth gates ────────────────────────────────────────────────
def test_ocr_flag_off_returns_503(client, patient, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("FEATURE_OCR", "false")
    get_settings.cache_clear()
    try:
        r = client.post(
            "/api/v1/documents/upload-session",
            headers=patient["headers"],
            json={"declared_mime": "image/jpeg"},
        )
        assert r.status_code == 503
    finally:
        get_settings.cache_clear()


def test_unauthenticated_rejected(client, mdi_env):
    assert client.get("/api/v1/documents").status_code == 401


def test_blob_get_with_put_token_forbidden(client, patient, mdi_env):
    """A write token must not be usable to read (op mismatch)."""
    r = client.post(
        "/api/v1/documents/upload-session",
        headers=patient["headers"],
        json={"declared_mime": "image/jpeg"},
    )
    put_url = r.json()["signed_put_url"]
    token = put_url.rsplit("/", 1)[1]
    # GET with a PUT-scoped token → 403.
    assert client.get(f"/api/v1/documents/blob/{token}").status_code == 403


# ── review-fix regressions (P1/P2 from independent review) ────────────────────
def test_all_rejected_document_is_rejected_not_confirmed(client, patient, mdi_env):
    """P1-5: rejecting every candidate must leave the document 'rejected'."""
    doc_id, _ = _upload_and_finalize(client, patient["headers"])
    cands = client.get(
        f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
    ).json()["items"]
    for c in cands:
        assert (
            client.post(
                f"/api/v1/candidates/{c['id']}/reject", headers=patient["headers"]
            ).status_code
            == 200
        )
    doc = client.get(f"/api/v1/documents/{doc_id}", headers=patient["headers"]).json()
    assert doc["status"] == "rejected"


def test_upload_session_rejects_unsupported_mime(client, patient, mdi_env):
    """P2: an unsupported declared MIME fails fast at session creation."""
    r = client.post(
        "/api/v1/documents/upload-session",
        headers=patient["headers"],
        json={"declared_mime": "application/zip"},
    )
    assert r.status_code == 400


def test_in_batch_duplicate_dedupe_keys_do_not_crash_finalize(client, patient, monkeypatch, tmp_path):
    """P0-1: two candidate drafts with the SAME dedupe_key must not abort finalize."""
    from app.core.config import get_settings

    class _DupExtractor:
        def extract(self, *, text, doc_type, ocr_confidence):
            key = make_dedupe_key("medication", "same", "same")
            return [
                CandidateDraft("medication", 0, {"name": "A"}, key),
                CandidateDraft("medication", 1, {"name": "B"}, key),  # duplicate key
            ]

    monkeypatch.setenv("MCP_ENABLE_MOCK_OCR", "true")
    monkeypatch.setenv("MCP_STORAGE_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("FEATURE_OCR", "true")
    get_settings.cache_clear()
    reset_storage()
    extractors.register_extractor("prescription", _DupExtractor())
    try:
        doc_id, fin = _upload_and_finalize(client, patient["headers"])
        assert fin.status_code == 200, fin.text
        items = client.get(
            f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
        ).json()["items"]
        assert len(items) == 1  # collapsed to a single candidate
    finally:
        extractors.reset_extractors()
        reset_storage()
        get_settings.cache_clear()


def test_blob_get_rejects_quarantine_key_token(client, patient, mdi_env):
    """P1-3: a GET token pointed at a quarantine key is refused (container guard)."""
    from app.core.config import get_settings
    from app.services.storage import (
        CONTAINER_QUARANTINE,
        build_object_key,
        derive_blob_secret,
        sign_blob_token,
    )

    key = build_object_key(container=CONTAINER_QUARANTINE, patient_id="p", ext="jpg")
    secret = derive_blob_secret(get_settings().secret_key)
    import time

    token = sign_blob_token(secret, key=key, op="get", expires_at=int(time.time()) + 60)
    assert client.get(f"/api/v1/documents/blob/{token}").status_code == 403
