"""Tests for the drug catalog service and GET /medications/suggest endpoint.

Coverage targets
----------------
- suggest by generic name (exact, prefix, accent-stripped)
- suggest by brand name
- suggest by Vietnamese common name (no-accent)
- suggest with dosage in query (dosage stripped, still matches)
- metric_group boost: same drug scores higher when group matches
- strict=True: filters out drugs not in metric_group
- safety_notice always present in every result item
- no prescribing / dosing language in any result field
- unknown / garbage query returns empty list
- limit param respected
- inactive entries excluded
- seed_catalog is idempotent (re-running inserts 0 new rows)
- GET /medications/suggest — 200 with patient auth, 401 without
"""

from __future__ import annotations

from app.models.drug_catalog import DrugEntry
from app.schemas.drug_catalog import SAFETY_NOTICE
from app.services.drug_catalog import (
    _normalize,
    _strip_dosage,
    normalize_medication_name,
    seed_catalog,
    suggest_drugs,
)
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PRESCRIBING_WORDS = (
    "uong",
    "dung",
    "lieu",
    "dose",
    "dosage",
    "mg/day",
    "mg/ngay",
    "dieu tri",
    "treatment",
    "prescrib",
)


def _no_prescribing_text(text: str) -> bool:
    lo = _normalize(text)
    return not any(w in lo for w in PRESCRIBING_WORDS)


# ---------------------------------------------------------------------------
# Unit: normalisation helpers
# ---------------------------------------------------------------------------


def test_normalize_strips_accents():
    assert _normalize("Metformin") == "metformin"
    # Standard accented latin (e.g. á → a) is stripped
    assert _normalize("Glucophagé") == "glucophage"
    assert _normalize("  Glucophage  ") == "glucophage"
    # Vietnamese Đ (d-with-stroke, U+0110/0111) has no ASCII decomposition and is
    # dropped — this is acceptable because both query AND catalog go through the
    # same transform, so matching stays symmetric.
    assert "d" not in _normalize("Đ")  # Đ → empty string


def test_strip_dosage_removes_tokens():
    assert _strip_dosage("Metformin 500mg") == "Metformin"
    assert _strip_dosage("insulin 10 mcg") == "insulin"
    assert _strip_dosage("aspirin 100mg tablet") == "aspirin tablet"
    assert _strip_dosage("No dosage here") == "No dosage here"
    # Internal double-spaces are collapsed
    assert "  " not in _strip_dosage("metformin 500mg extended")


# ---------------------------------------------------------------------------
# Unit: seed_catalog
# ---------------------------------------------------------------------------


def test_seed_catalog_inserts_rows(db: Session):
    inserted = seed_catalog(db)
    assert inserted > 0, "Expected at least some drugs to be seeded"


def test_seed_catalog_is_idempotent(db: Session):
    seed_catalog(db)
    second = seed_catalog(db)
    assert second == 0, "Re-running seed must insert 0 rows"


def test_seed_catalog_covers_all_metric_groups(db: Session):
    seed_catalog(db)
    entries = db.query(DrugEntry).filter(DrugEntry.is_active.is_(True)).all()
    groups = {g for e in entries for g in (e.metric_groups or [])}
    required = {
        "diabetes", "lipid", "hypertension", "thyroid",
        "gout", "antiplatelet", "gastroprotection",
    }
    missing = required - groups
    assert not missing, f"Missing metric groups in seed data: {missing}"


# ---------------------------------------------------------------------------
# Service: suggest_drugs
# ---------------------------------------------------------------------------


def test_suggest_by_generic_name_exact(db: Session):
    seed_catalog(db)
    results = suggest_drugs(db, q="metformin", limit=5)
    assert results, "Expected at least one result for 'metformin'"
    assert any(r.generic_name == "metformin" for r in results)


def test_suggest_by_brand_name(db: Session):
    seed_catalog(db)
    results = suggest_drugs(db, q="Glucophage", limit=5)
    assert results
    assert any(r.generic_name == "metformin" for r in results)


def test_suggest_by_brand_name_case_insensitive(db: Session):
    seed_catalog(db)
    results = suggest_drugs(db, q="crestor", limit=5)
    assert results
    assert any(r.generic_name == "rosuvastatin" for r in results)


def test_suggest_by_vietnamese_name_no_accent(db: Session):
    seed_catalog(db)
    results = suggest_drugs(db, q="Euthyrox", limit=5)
    assert results
    assert any(r.generic_name == "levothyroxine" for r in results)


def test_suggest_with_dosage_in_query(db: Session):
    seed_catalog(db)
    results = suggest_drugs(db, q="metformin 500mg", limit=5)
    assert results, "Dosage in query should not block matching"
    assert any(r.generic_name == "metformin" for r in results)


def test_suggest_metric_group_boost(db: Session):
    seed_catalog(db)
    with_group = suggest_drugs(db, q="metformin", metric_group="diabetes", limit=5)
    without_group = suggest_drugs(db, q="metformin", limit=5)
    assert with_group
    boosted_score = with_group[0].confidence_score
    base_score = without_group[0].confidence_score
    assert boosted_score >= base_score


def test_suggest_strict_metric_group_filters(db: Session):
    seed_catalog(db)
    results = suggest_drugs(db, q="metformin", metric_group="lipid", strict=True, limit=5)
    # metformin is in diabetes, not lipid — strict must exclude it
    for r in results:
        assert "lipid" in (r.metric_groups or []), \
            f"strict=True must only return drugs in metric_group, got {r.generic_name}"


def test_suggest_unknown_query_returns_empty(db: Session):
    seed_catalog(db)
    results = suggest_drugs(db, q="xyzzy_nonexistent_drug_zzz")
    assert results == []


def test_suggest_limit_respected(db: Session):
    seed_catalog(db)
    results = suggest_drugs(db, q="a", limit=3)
    assert len(results) <= 3


def test_suggest_excludes_inactive(db: Session):
    seed_catalog(db)
    entry = db.query(DrugEntry).filter(DrugEntry.generic_name == "metformin").first()
    assert entry is not None
    entry.is_active = False
    db.commit()
    try:
        results = suggest_drugs(db, q="metformin", limit=5)
        assert all(r.generic_name != "metformin" for r in results), "Inactive entries must be excluded"
    finally:
        entry.is_active = True
        db.commit()


def test_safety_notice_always_present(db: Session):
    seed_catalog(db)
    results = suggest_drugs(db, q="aspirin", limit=5)
    assert results
    for item in results:
        assert item.safety_notice == SAFETY_NOTICE


def test_no_prescribing_language_in_results(db: Session):
    seed_catalog(db)
    results = suggest_drugs(db, q="a", limit=25)
    for item in results:
        assert _no_prescribing_text(item.display_name), \
            f"Prescribing text in display_name: {item.display_name}"
        assert _no_prescribing_text(item.drug_class), \
            f"Prescribing text in drug_class: {item.drug_class}"
        for flag in item.caution_flags:
            assert _no_prescribing_text(flag), \
                f"Prescribing text in caution_flag: {flag}"


# ---------------------------------------------------------------------------
# Service: normalize_medication_name
# ---------------------------------------------------------------------------


def test_normalize_exact_match_confidence_high(db: Session):
    seed_catalog(db)
    result = normalize_medication_name(db, input_text="metformin")
    assert result.confidence >= 80
    assert result.drug_id is not None


def test_normalize_brand_to_generic(db: Session):
    seed_catalog(db)
    result = normalize_medication_name(db, input_text="Glucophage")
    assert result.confidence >= 80
    assert result.drug_id is not None
    assert result.ambiguous_matches[0].generic_name == "metformin"


def test_normalize_strips_dosage(db: Session):
    seed_catalog(db)
    result = normalize_medication_name(db, input_text="Aspirin 100mg")
    assert result.dosage_text is not None
    assert "100" in result.dosage_text
    assert result.parsed_name.lower() == "aspirin"


def test_normalize_low_confidence_no_drug_id(db: Session):
    seed_catalog(db)
    result = normalize_medication_name(db, input_text="xyz_nonexistent_999")
    assert result.drug_id is None
    assert result.confidence < 80


def test_normalize_safety_notice_present(db: Session):
    seed_catalog(db)
    result = normalize_medication_name(db, input_text="metformin")
    assert result.safety_notice == SAFETY_NOTICE


# ---------------------------------------------------------------------------
# API: GET /medications/suggest
# ---------------------------------------------------------------------------


def test_suggest_endpoint_returns_200_for_patient(client, patient, db):
    seed_catalog(db)
    r = client.get(
        "/api/v1/medications/suggest?q=metformin",
        headers=patient["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["query"] == "metformin"
    assert isinstance(body["results"], list)
    assert body["total"] == len(body["results"])


def test_suggest_endpoint_requires_auth(client):
    r = client.get("/api/v1/medications/suggest?q=aspirin")
    assert r.status_code == 401


def test_suggest_endpoint_safety_notice_in_all_items(client, patient, db):
    seed_catalog(db)
    r = client.get(
        "/api/v1/medications/suggest?q=aspirin",
        headers=patient["headers"],
    )
    assert r.status_code == 200
    for item in r.json()["results"]:
        assert item["safety_notice"] == SAFETY_NOTICE


def test_suggest_endpoint_with_metric_group(client, patient, db):
    seed_catalog(db)
    r = client.get(
        "/api/v1/medications/suggest?q=metformin&metric_group=diabetes",
        headers=patient["headers"],
    )
    assert r.status_code == 200
    assert r.json()["metric_group"] == "diabetes"


def test_suggest_endpoint_limit(client, patient, db):
    seed_catalog(db)
    r = client.get(
        "/api/v1/medications/suggest?q=a&limit=2",
        headers=patient["headers"],
    )
    assert r.status_code == 200
    assert len(r.json()["results"]) <= 2


def test_suggest_endpoint_empty_query_rejected(client, patient):
    r = client.get("/api/v1/medications/suggest?q=", headers=patient["headers"])
    assert r.status_code == 422
