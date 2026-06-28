"""Lab reference catalog + GET /api/v1/lab-reference."""

from __future__ import annotations

from app.domain.lab_catalog import get_catalog
from app.domain.lab_interpreter import BIOMARKERS


def test_catalog_covers_all_ocr_canonicals():
    """Every biomarker the OCR parser recognises must exist in the catalog so
    manual entry + OCR stay consistent."""
    cat = set(get_catalog()["biomarkers"])
    parser = {s.canonical for s in BIOMARKERS}
    assert parser <= cat, f"missing from catalog: {parser - cat}"


def test_catalog_biomarker_shape_valid():
    cat = get_catalog()
    for key, b in cat["biomarkers"].items():
        assert b["name_vn"] and b["name_en"], key
        assert b["category"], key
        units = b["units"]
        assert units, f"{key} has no units"
        primaries = [u for u in units if u.get("is_primary")]
        assert len(primaries) == 1, f"{key} must have exactly one primary unit"
        for u in units:
            assert u["key"] and u["label"], key
            r = u["ref_range"]
            assert isinstance(r["low"], (int, float)) and isinstance(r["high"], (int, float))
            assert r["low"] <= r["high"], f"{key}/{u['key']} low>high"


def test_catalog_categories_reference_real_biomarkers():
    cat = get_catalog()
    keys = set(cat["biomarkers"])
    seen = set()
    for c in cat["categories"]:
        assert c["key"] and c["name"]
        for bk in c["biomarkers"]:
            assert bk in keys, f"category {c['key']} references unknown {bk}"
            seen.add(bk)
    # Every biomarker belongs to exactly one listed category.
    assert seen == keys, f"uncategorised: {keys - seen}"


def test_catalog_has_multi_unit_examples():
    bm = get_catalog()["biomarkers"]
    assert len(bm["fasting_glucose"]["units"]) >= 2  # mmol/L + mg/dL
    assert any(u["label"] == "mmol/L" for u in bm["fasting_glucose"]["units"])


def test_endpoint_returns_catalog_for_patient(client, patient):
    r = client.get("/api/v1/lab-reference", headers=patient["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert "categories" in body and "biomarkers" in body
    assert "fasting_glucose" in body["biomarkers"]
    assert r.headers.get("cache-control", "").find("max-age") >= 0


def test_endpoint_requires_auth(client):
    assert client.get("/api/v1/lab-reference").status_code == 401


def test_endpoint_forbidden_for_doctor(client, token_for):
    r = client.get("/api/v1/lab-reference", headers=token_for("doc-1", role="doctor"))
    assert r.status_code == 403
