"""API tests for the QA fixture ingestion path (dev/staging automation).

POST /documents/qa-fixture ingests a BUNDLED synthetic prescription through the
SAME pipeline a camera upload uses (upload-session → finalize → extract), so
Journey A is deterministically automatable without the native camera. Verifies:
enabled → a needs_review document with real medication candidates; disabled →
404; and that it reuses the real extractor (no test stub).
"""

from __future__ import annotations

import pytest
from app.main import app
from app.services.storage import reset_storage
from fastapi.testclient import TestClient


@pytest.fixture
def qa_env(monkeypatch, tmp_path):
    """Deterministic QA env: fixture path ON, OCR flag ON, temp storage.

    Deliberately does NOT override extractors/promoters — the point is to exercise
    the real PrescriptionExtractor on the bundled fixture text.
    """
    from app.core.config import get_settings

    monkeypatch.setenv("MCP_QA_FIXTURE_ENABLED", "true")
    monkeypatch.setenv("MCP_STORAGE_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("FEATURE_OCR", "true")
    get_settings.cache_clear()
    reset_storage()
    yield
    reset_storage()
    get_settings.cache_clear()


@pytest.fixture
def client():
    return TestClient(app)


def test_qa_fixture_produces_needs_review_document(client, patient, qa_env):
    r = client.post("/api/v1/documents/qa-fixture", headers=patient["headers"])
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["object_state"] == "accepted"
    assert doc["status"] == "needs_review"
    assert doc["doc_type"] == "prescription"

    # Real extractor turned the bundled synthetic text into medication candidates.
    cands = client.get(
        f"/api/v1/documents/{doc['id']}/candidates", headers=patient["headers"]
    ).json()["items"]
    assert len(cands) >= 1
    assert all(c["status"] == "needs_review" for c in cands)
    names = {c["fields"].get("name") for c in cands}
    assert {"Metformin", "Amlodipine"} <= names


def test_qa_fixture_404_when_disabled(client, patient, monkeypatch, tmp_path):
    from app.core.config import get_settings

    monkeypatch.setenv("MCP_QA_FIXTURE_ENABLED", "false")
    monkeypatch.setenv("MCP_STORAGE_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("FEATURE_OCR", "true")
    get_settings.cache_clear()
    reset_storage()
    try:
        r = client.post("/api/v1/documents/qa-fixture", headers=patient["headers"])
        assert r.status_code == 404
    finally:
        reset_storage()
        get_settings.cache_clear()


def test_qa_fixture_requires_auth(client, qa_env):
    assert client.post("/api/v1/documents/qa-fixture").status_code == 401


def test_qa_fixture_candidate_confirms_and_promotes(client, patient, qa_env):
    """The produced candidate flows through the real confirm→promote path."""
    doc = client.post(
        "/api/v1/documents/qa-fixture", headers=patient["headers"]
    ).json()
    cid = client.get(
        f"/api/v1/documents/{doc['id']}/candidates", headers=patient["headers"]
    ).json()["items"][0]["id"]
    r = client.post(
        f"/api/v1/candidates/{cid}/confirm", headers=patient["headers"], json={}
    )
    assert r.status_code == 200, r.text
    assert r.json()["candidate"]["status"] == "confirmed"
