"""T20 — System endpoint tests: /health + /info observability hardening.

Covers P1-FIX-01 (DB connectivity in /health) and P1-FIX-02 (migration version
+ feature flags in /info), plus public-access checks for both endpoints.

Tests added: 7 (baseline 455 → 462+)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# T20-S01 — GET /health returns 200 with db status
# ---------------------------------------------------------------------------

def test_health_returns_200_when_db_up(client):
    """T20-S01: GET /health → 200 with status=ok and db=ok when DB is reachable."""
    r = client.get("/api/v1/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"


# ---------------------------------------------------------------------------
# T20-S02 — /health is public (no auth required)
# ---------------------------------------------------------------------------

def test_health_unauthenticated_allowed(client):
    """T20-S02: GET /health without Authorization header → 200 (public endpoint)."""
    r = client.get("/api/v1/health")
    # Must not require auth — 401 would be wrong here
    assert r.status_code != 401, "Health endpoint must be public (no auth required)"
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# T20-S03 — GET /info contains migration_version
# ---------------------------------------------------------------------------

def test_info_contains_migration_version(client):
    """T20-S03: GET /info → 200 with migration_version key (non-empty string)."""
    r = client.get("/api/v1/info")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "migration_version" in body, "Response must include migration_version"
    # migration_version must be a string (may be "unknown" for SQLite test DB)
    assert isinstance(body["migration_version"], str)
    assert body["migration_version"] != "", "migration_version must not be empty"


# ---------------------------------------------------------------------------
# T20-S04 — GET /info contains feature_flags dict
# ---------------------------------------------------------------------------

def test_info_contains_feature_flags(client):
    """T20-S04: GET /info → 200 with feature_flags as a dict."""
    r = client.get("/api/v1/info")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "feature_flags" in body, "Response must include feature_flags"
    flags = body["feature_flags"]
    assert isinstance(flags, dict), "feature_flags must be a dict"
    assert len(flags) > 0, "feature_flags must expose at least one flag"
    # All values must be booleans
    for flag_name, flag_value in flags.items():
        assert isinstance(flag_value, bool), (
            f"Feature flag '{flag_name}' must be a bool, got {type(flag_value)}"
        )


# ---------------------------------------------------------------------------
# T20-S05 — /info is public (no auth required)
# ---------------------------------------------------------------------------

def test_info_unauthenticated_allowed(client):
    """T20-S05: GET /info without Authorization header → 200 (public endpoint)."""
    r = client.get("/api/v1/info")
    assert r.status_code != 401, "Info endpoint must be public (no auth required)"
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# T20-S06 — GET /info returns known fields (regression guard)
# ---------------------------------------------------------------------------

def test_info_returns_known_fields(client):
    """T20-S06: GET /info → known static fields still present (regression guard)."""
    r = client.get("/api/v1/info")
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("app", "env", "ai_mode", "ocr_mode", "storage_mode"):
        assert key in body, f"Expected field '{key}' missing from /info response"


# ---------------------------------------------------------------------------
# T20-S07 — /health response shape (both fields present)
# ---------------------------------------------------------------------------

def test_health_response_has_required_shape(client):
    """T20-S07: GET /health → response has both 'status' and 'db' fields."""
    r = client.get("/api/v1/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "status" in body, "Health response must contain 'status'"
    assert "db" in body, "Health response must contain 'db'"
    assert body["status"] in ("ok", "degraded"), f"Unexpected status: {body['status']}"
    assert body["db"] in ("ok", "error"), f"Unexpected db value: {body['db']}"
