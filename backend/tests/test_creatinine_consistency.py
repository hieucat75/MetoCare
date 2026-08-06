"""Tests for creatinine unit consistency — P0 clinical safety.

Validates:
- Correct normalization of µmol/L → mg/dL (si_factor=0.011312, i.e. 1/88.42)
- pmol/L and other incompatible units are blocked (overall=0.0, needs_verification)
- Plausibility detection catches creatinine in mg/dL that looks like µmol/L value
- _clean_reference_range preserves qualitative strings (regression guard)
- LabResultOut schema exposes data_quality_flag
"""

from __future__ import annotations

from app.api.v1.routes.lab import _clean_reference_range
from app.domain.lab_interpreter import _ALIAS_INDEX, classify_value
from app.domain.lab_normalization import normalize_value_to_si
from app.models.clinical import LabResult, LabUploadBatch
from app.services.biomarker_specs import check_plausibility
from app.services.lab import normalize_and_classify

# ---------------------------------------------------------------------------
# Helpers / imports
# ---------------------------------------------------------------------------
from sqlalchemy import select

# ---------------------------------------------------------------------------
# Test 1: creatinine 88 µmol/L normalises to ≈0.995 mg/dL → normal
# ---------------------------------------------------------------------------

def test_creatinine_88_umol_is_normal():
    """88 µmol/L × 0.011312 = 0.9954 mg/dL — within [0.6, 1.3] → normal."""
    value, unit = normalize_value_to_si(88.0, "µmol/L", "creatinine")
    assert unit == "mg/dL", f"Expected mg/dL, got {unit}"
    assert abs(value - (88.0 * 0.011312)) < 0.001, f"Unexpected value {value}"
    status = classify_value("creatinine", value)
    assert status is not None
    assert status.value == "normal", f"Expected normal, got {status.value}"


# ---------------------------------------------------------------------------
# Test 2: creatinine 0.99 mg/dL → normal
# ---------------------------------------------------------------------------

def test_creatinine_099_mgdl_is_normal():
    """0.99 mg/dL is within [0.6, 1.3] → normal."""
    status = classify_value("creatinine", 0.99)
    assert status is not None
    assert status.value == "normal", f"Expected normal, got {status.value}"


# ---------------------------------------------------------------------------
# Test 3: creatinine 88 mg/dL → critical (impossibly high in mg/dL units)
# ---------------------------------------------------------------------------

def test_creatinine_88_mgdl_is_critical():
    """88 mg/dL far exceeds critical_high=4.0 → critical."""
    status = classify_value("creatinine", 88.0)
    assert status is not None
    assert status.value == "critical", f"Expected critical, got {status.value}"


# ---------------------------------------------------------------------------
# Test 4: creatinine + pmol/L → incompatible, overall=0.0, suspicious=True
# ---------------------------------------------------------------------------

def test_creatinine_pmol_l_flagged_as_incompatible():
    """pmol/L is clinically impossible for creatinine — must be flagged overall=0.0."""
    result = check_plausibility("creatinine", 88.0, "pmol/L")
    assert result["plausible"] is False, "pmol/L must NOT be plausible for creatinine"
    assert result["suspicious"] is True, "pmol/L must be flagged as suspicious"
    assert result.get("overall", 1.0) == 0.0, f"overall must be 0.0, got {result.get('overall')}"


# ---------------------------------------------------------------------------
# Test 5: creatinine + µmol/L → plausible=True
# ---------------------------------------------------------------------------

def test_creatinine_umol_l_accepted():
    """µmol/L is the canonical SI unit for creatinine — must be accepted."""
    result = check_plausibility("creatinine", 88.0, "µmol/L")
    assert result["plausible"] is True, f"µmol/L should be plausible: {result}"


# ---------------------------------------------------------------------------
# Test 6: encoding variants of µmol/L all convert correctly
# ---------------------------------------------------------------------------

def test_creatinine_umol_encoding_variants():
    """umol/L and μmol/L (unicode variants) must convert to mg/dL correctly."""
    for variant in ("umol/L", "μmol/L"):
        value, unit = normalize_value_to_si(88.0, variant, "creatinine")
        assert unit == "mg/dL", f"Variant {variant!r} did not convert: got {unit}"
        assert abs(value - (88.0 * 0.011312)) < 0.001, (
            f"Variant {variant!r} gave wrong value {value}"
        )


# ---------------------------------------------------------------------------
# Test 7: plausibility of 88 mg/dL → suspicious (value fits µmol/L better)
# ---------------------------------------------------------------------------

def test_creatinine_plausibility_88_mgdl():
    """88 mg/dL exceeds physiological_max for mg/dL but fits µmol/L → suspicious."""
    result = check_plausibility("creatinine", 88.0, "mg/dL")
    # value 88 is above si_max_plausible=30 for mg/dL
    # and within alt_max_plausible=2650 for µmol/L → suspicious
    assert result["plausible"] is False, f"88 mg/dL should not be plausible: {result}"
    assert result["suspicious"] is True, f"88 mg/dL should be suspicious: {result}"


# ---------------------------------------------------------------------------
# Test 8: BiomarkerSpec.incompatible_units includes "pmol/L"
# ---------------------------------------------------------------------------

def test_creatinine_incompatible_units_list():
    """BiomarkerSpec for creatinine must list pmol/L as incompatible."""
    spec = _ALIAS_INDEX.get("creatinine")
    assert spec is not None, "creatinine spec not found in _ALIAS_INDEX"
    assert "pmol/L" in spec.incompatible_units, (
        f"pmol/L not in incompatible_units: {spec.incompatible_units}"
    )


# ---------------------------------------------------------------------------
# Test 9: _clean_reference_range preserves "Âm tính"
# ---------------------------------------------------------------------------

def test_clean_ref_range_preserves_am_tinh():
    """Qualitative result 'Âm tính' must not be stripped."""
    result = _clean_reference_range("Âm tính", "mg/dL")
    assert result == "Âm tính", f"Expected 'Âm tính', got {result!r}"


# ---------------------------------------------------------------------------
# Test 10: _clean_reference_range preserves "Bình thường"
# ---------------------------------------------------------------------------

def test_clean_ref_range_preserves_binh_thuong():
    """Qualitative result 'Bình thường' must not be stripped."""
    result = _clean_reference_range("Bình thường", "mg/dL")
    assert result == "Bình thường", f"Expected 'Bình thường', got {result!r}"


# ---------------------------------------------------------------------------
# Test 11: _clean_reference_range preserves "Negative"
# ---------------------------------------------------------------------------

def test_clean_ref_range_preserves_negative():
    """Qualitative result 'Negative' must not be stripped."""
    result = _clean_reference_range("Negative", "mg/dL")
    assert result == "Negative", f"Expected 'Negative', got {result!r}"


# ---------------------------------------------------------------------------
# Test 12: _clean_reference_range strips unit suffix from numeric range
# ---------------------------------------------------------------------------

def test_clean_ref_range_strips_unit():
    """'0.6–1.3 mg/dL' → '0.6–1.3'."""
    result = _clean_reference_range("0.6–1.3 mg/dL", "mg/dL")
    assert result == "0.6–1.3", f"Expected '0.6–1.3', got {result!r}"


# ---------------------------------------------------------------------------
# Test 13: _clean_reference_range strips double unit suffix
# ---------------------------------------------------------------------------

def test_clean_ref_range_strips_double_unit():
    """'53–115 µmol/L µmol/L' → '53–115'."""
    result = _clean_reference_range("53–115 µmol/L µmol/L", "µmol/L")
    assert result == "53–115", f"Expected '53–115', got {result!r}"


# ---------------------------------------------------------------------------
# Test 14: _clean_reference_range preserves "< 200"
# ---------------------------------------------------------------------------

def test_clean_ref_range_preserves_lt_200():
    """'< 200' has no unit slash token — must be preserved."""
    result = _clean_reference_range("< 200", "mg/dL")
    assert result == "< 200", f"Expected '< 200', got {result!r}"


# ---------------------------------------------------------------------------
# Test 15: LabResultOut schema exposes data_quality_flag field
# ---------------------------------------------------------------------------

def test_data_quality_flag_in_schema():
    """LabResultOut must expose data_quality_flag as an optional field."""
    from app.schemas.lab import LabResultOut
    fields = LabResultOut.model_fields
    assert "data_quality_flag" in fields, (
        f"data_quality_flag missing from LabResultOut fields: {list(fields.keys())}"
    )
    field = fields["data_quality_flag"]
    # Should be Optional[str] — default None
    assert field.default is None or field.is_required() is False, (
        "data_quality_flag should be optional (default None)"
    )


# ---------------------------------------------------------------------------
# HealthMetric promotion severity tests — fix(metrics): preserve critical severity
# ---------------------------------------------------------------------------


# ── Behaviour change, 2026-08-05 (unit-normalization registry) ─────────────
#
# Creatinine 88 mg/dL is beyond `physiological_max` (30 mg/dL) — no survivable
# concentration reaches it, and it is almost certainly a mislabelled 88 µmol/L.
# The unit registry therefore REFUSES the conversion ("reject impossible
# converted values") instead of classifying it.
#
# The tests below previously asserted the older model: "classify whatever unit
# the patient asserts", i.e. 88 mg/dL -> critical. They are updated, not deleted,
# because the property they actually protect is still essential and is now
# asserted in its stronger form: a refused conversion must NOT leave a stale,
# reassuring metric standing. Refusing to classify AND refusing to withdraw would
# be worse than either alone — the dashboard would keep telling the patient their
# kidney function is fine on the strength of a value the system just declined to
# interpret.
#
# So: no metric at all (an honest gap the UI can surface as "unit unclear"),
# never a normal one. The clinically dangerous direction — a real critical being
# shown as normal — remains covered by the µmol/L cases in this file, which
# convert successfully and still classify.

def test_promoted_health_metric_from_creatinine_88_mgdl_is_refused(db, patient):
    """88 mg/dL is physiologically impossible: refuse, and write NO metric."""
    import datetime as _dt

    from app.services.lab import _promote_row

    batch = LabUploadBatch(patient_id=patient["patient_id"], lab_name="Lab", test_date=_dt.date(2024, 1, 1))
    db.add(batch)
    db.flush()

    row = LabResult(
        patient_id=patient["patient_id"],
        batch_id=batch.id,
        test_name="Creatinine",
        canonical_name="creatinine",
        value=88.0,
        unit="mg/dL",
        normalized_value_si=88.0,
        normalized_unit_si="mg/dL",
        status="critical",
        source_type="manual",
        verified_by_user=True,
        original_value=88.0,
        original_unit="mg/dL",
    )
    db.add(row)
    db.flush()

    _promote_row(db, row, _dt.datetime(2024, 1, 1, 8, 0))
    db.flush()

    from app.models.clinical import HealthMetric as HM
    metric = db.execute(
        select(HM).where(HM.source_ref == row.id, HM.deleted_at.is_(None))
    ).scalar_one_or_none()
    assert metric is None, (
        "an impossible value must not be promoted to the trend surface at all; "
        f"got a metric with status={getattr(metric, 'status', None)!r}"
    )


def test_promoted_health_metric_from_creatinine_88_umol_is_normal(db, patient):
    """HealthMetric promoted from creatinine 88 µmol/L (≈0.995 mg/dL) must be normal."""
    import datetime as _dt

    from app.services.lab import _promote_row

    clf = normalize_and_classify("creatinine", 88.0, "µmol/L")
    norm_val = clf["normalized_value_si"]
    norm_unit = clf["normalized_unit_si"]

    batch = LabUploadBatch(patient_id=patient["patient_id"], lab_name="Lab2", test_date=_dt.date(2024, 2, 1))
    db.add(batch)
    db.flush()

    row = LabResult(
        patient_id=patient["patient_id"],
        batch_id=batch.id,
        test_name="Creatinine",
        canonical_name="creatinine",
        value=88.0,
        unit="µmol/L",
        normalized_value_si=norm_val,
        normalized_unit_si=norm_unit,
        status="normal",
        source_type="manual",
        verified_by_user=True,
        original_value=88.0,
        original_unit="µmol/L",
    )
    db.add(row)
    db.flush()

    _promote_row(db, row, _dt.datetime(2024, 2, 1, 8, 0))
    db.flush()

    from app.models.clinical import HealthMetric as HM
    metric = db.execute(
        select(HM).where(HM.source_ref == row.id, HM.deleted_at.is_(None))
    ).scalar_one()
    assert metric.status == "normal", (
        f"Promoted HealthMetric from creatinine 88 µmol/L must be normal, got {metric.status}"
    )


def test_correcting_creatinine_88mgdl_to_88umol_changes_metric_to_normal(db, patient):
    """Correcting creatinine 88 mg/dL → 88 µmol/L must change HealthMetric critical→normal."""
    import datetime as _dt

    from app.services.lab import _promote_row, correct_lab_result

    batch = LabUploadBatch(patient_id=patient["patient_id"], lab_name="Lab3", test_date=_dt.date(2024, 3, 1))
    db.add(batch)
    db.flush()

    row = LabResult(
        patient_id=patient["patient_id"],
        batch_id=batch.id,
        test_name="Creatinine",
        canonical_name="creatinine",
        value=88.0,
        unit="mg/dL",
        normalized_value_si=88.0,
        normalized_unit_si="mg/dL",
        status="critical",
        source_type="ocr_upload",
        verified_by_user=True,
        original_value=88.0,
        original_unit="mg/dL",
    )
    db.add(row)
    db.flush()
    _promote_row(db, row, _dt.datetime(2024, 3, 1))
    db.flush()

    from app.models.clinical import HealthMetric as HM
    # 88 mg/dL is impossible, so it is refused and never promoted.
    assert db.execute(
        select(HM).where(HM.source_ref == row.id, HM.deleted_at.is_(None))
    ).scalar_one_or_none() is None

    # Correct to 88 µmol/L — now convertible. The RECOVERY property: fixing the
    # unit the app complained about must bring the trend back, otherwise the
    # patient does what they were asked and nothing happens.
    correct_lab_result(db, result_id=row.id, patient_id=patient["patient_id"],
                       requester_id=patient["user_id"], new_value=88.0, new_unit="µmol/L")

    metric = db.execute(
        select(HM).where(HM.source_ref == row.id, HM.deleted_at.is_(None))
    ).scalar_one_or_none()
    assert metric is not None, "correcting to a valid unit did not restore the metric"
    assert metric.status == "normal", (
        f"After correcting to 88 µmol/L, HealthMetric must be normal, got {metric.status}"
    )


def test_correcting_creatinine_88umol_to_88mgdl_withdraws_the_metric(db, patient):
    """Correcting 88 µmol/L → 88 mg/dL must WITHDRAW the metric, not leave it normal."""
    import datetime as _dt

    from app.services.lab import _promote_row, correct_lab_result

    clf = normalize_and_classify("creatinine", 88.0, "µmol/L")

    batch = LabUploadBatch(patient_id=patient["patient_id"], lab_name="Lab4", test_date=_dt.date(2024, 4, 1))
    db.add(batch)
    db.flush()

    row = LabResult(
        patient_id=patient["patient_id"],
        batch_id=batch.id,
        test_name="Creatinine",
        canonical_name="creatinine",
        value=88.0,
        unit="µmol/L",
        normalized_value_si=clf["normalized_value_si"],
        normalized_unit_si=clf["normalized_unit_si"],
        status="normal",
        source_type="ocr_upload",
        verified_by_user=True,
        original_value=88.0,
        original_unit="µmol/L",
    )
    db.add(row)
    db.flush()
    _promote_row(db, row, _dt.datetime(2024, 4, 1))
    db.flush()

    from app.models.clinical import HealthMetric as HM
    metric = db.execute(
        select(HM).where(HM.source_ref == row.id, HM.deleted_at.is_(None))
    ).scalar_one()
    assert metric.status == "normal"

    # Correct to 88 mg/dL — physiologically impossible, so the conversion is
    # refused. The metric must be WITHDRAWN, never left at its previous `normal`:
    # a stale normal is a false reassurance about kidney function.
    correct_lab_result(db, result_id=row.id, patient_id=patient["patient_id"],
                       requester_id=patient["user_id"], new_value=88.0, new_unit="mg/dL")

    remaining = db.execute(
        select(HM).where(HM.source_ref == row.id, HM.deleted_at.is_(None))
    ).scalar_one_or_none()
    assert remaining is None, (
        "the earlier `normal` metric survived a refused conversion — the dashboard "
        f"would keep reassuring the patient; got status={getattr(remaining, 'status', None)!r}"
    )
