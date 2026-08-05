"""Cross-path parity: one printed CBC value, one normalized clinical result.

The defect this exists to prevent is not a wrong number in one place. It is
DISAGREEMENT: the same haemoglobin printed as ``140 g/L`` was REFUSED by the
document path and stored as a fabricated CRITICAL by manual entry, because each
path did its own unit handling. Whichever path a patient happened to use decided
what their chart said.

So these are contract tests. They push equivalent values through every path that
can write a canonical ``LabResult`` and assert the paths agree on the canonical
analyte, the normalized value and unit, the preserved original and the
interpretation.

The paths:
  1. manual entry           -> lab.create_manual_entry (through the HTTP endpoint)
  2. patient correction     -> lab.correct_lab_result
  3. OCR document promotion -> mdi.promoters.LabPromoter
  4. the shared classifier  -> lab.normalize_and_classify, which is what
                               /lab-uploads and lab_pipeline both call

A path that stops routing through the registry fails here — "no path may bypass
the central guard" has to be enforced by a test, not by everyone remembering.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.models.clinical import LabResult
from app.models.medical_document import (
    DocumentExtraction,
    ExtractionCandidate,
    MedicalDocument,
)
from app.services import lab
from app.services.lab_batch import LabUploadBatch
from sqlalchemy import select

# (analyte, printed value, printed unit, expected canonical value, canonical unit)
CBC_CASES = [
    ("hemoglobin", 140.0, "g/L", 14.0, "g/dL"),
    ("hemoglobin", 70.0, "g/L", 7.0, "g/dL"),
    ("hemoglobin", 14.0, "g/dL", 14.0, "g/dL"),
    ("platelet", 20.0, "G/L", 20.0, "10^9/L"),
    ("platelet", 230.0, "10^9/L", 230.0, "10^9/L"),
    ("wbc", 0.8, "G/L", 0.8, "10^9/L"),
    ("wbc", 7.2, "G/L", 7.2, "10^9/L"),
    ("rbc", 4.5, "T/L", 4.5, "10^12/L"),
]

CBC_LABELS = {
    "hemoglobin": "Hemoglobin",
    "platelet": "Tiểu cầu",
    "wbc": "Bạch cầu",
    "rbc": "Hồng cầu",
}


def _expected(analyte, value, unit) -> dict:
    """The one authoritative answer every path must reproduce."""
    return lab.normalize_and_classify(analyte, value, unit)


@pytest.fixture
def make_candidate(db, patient):
    """Build a promotable lab candidate. No shared fixture exists for this."""
    state = {"n": 0}

    def _make(fields: dict) -> ExtractionCandidate:
        state["n"] += 1
        n = state["n"]
        doc = MedicalDocument(
            id=f"pd{n}",
            patient_id=patient["patient_id"],
            quarantine_key="q",
            status="accepted",
            object_state="accepted",
            source="upload",
            data_classification="sensitive_health",
        )
        extraction = DocumentExtraction(
            id=f"pe{n}",
            document_id=doc.id,
            schema_version="mdi-1",
            provider="tesseract",
            extraction_run_id=f"pr{n}",
            review_state="pending",
        )
        candidate = ExtractionCandidate(
            id=f"pc{n}",
            extraction_id=extraction.id,
            document_id=doc.id,
            patient_id=patient["patient_id"],
            candidate_type="lab_result",
            ordinal=0,
            fields_json=fields,
            dedupe_key=f"pk{n}",
            status="needs_review",
        )
        db.add_all([doc, extraction, candidate])
        db.flush()
        return candidate

    return _make


def _latest(db, patient, analyte) -> LabResult | None:
    return db.execute(
        select(LabResult)
        .where(LabResult.patient_id == patient["patient_id"])
        .where(LabResult.canonical_name == analyte)
        .order_by(LabResult.created_at.desc())
    ).scalars().first()


# ── 1. The shared classifier is the reference ───────────────────────────────


@pytest.mark.parametrize("analyte,value,unit,exp_value,exp_unit", CBC_CASES)
def test_shared_classifier_produces_the_expected_canonical_value(
    analyte, value, unit, exp_value, exp_unit
):
    r = _expected(analyte, value, unit)
    assert r["conversion_ok"] is True
    assert r["normalized_value_si"] == pytest.approx(exp_value)
    assert r["normalized_unit_si"] == exp_unit
    assert r["status"] is not None


# ── 2. Manual entry, end to end through the API ─────────────────────────────


@pytest.mark.parametrize("analyte,value,unit,exp_value,exp_unit", CBC_CASES)
def test_manual_entry_matches_the_shared_classifier(
    client, patient, db, analyte, value, unit, exp_value, exp_unit
):
    resp = client.post(
        f"/api/v1/patients/{patient['patient_id']}/lab-results",
        json={
            "test_date": "2026-05-20",
            "results": [{"test_name": CBC_LABELS[analyte], "value": value, "unit": unit}],
        },
        headers=patient["headers"],
    )
    assert resp.status_code in (200, 201), resp.text

    row = _latest(db, patient, analyte)
    assert row is not None, f"{analyte} was not stored"

    expected = _expected(analyte, value, unit)
    assert row.canonical_name == analyte
    assert row.normalized_value_si == pytest.approx(exp_value)
    assert row.normalized_unit_si == exp_unit
    assert row.status == expected["status"]
    # §E — the original is preserved verbatim, never overwritten by the conversion.
    assert row.original_value == pytest.approx(value)
    assert row.original_unit == unit


# ── 3. The OCR document path — the one that refused all of these ────────────


@pytest.mark.parametrize("analyte,value,unit,exp_value,exp_unit", CBC_CASES)
def test_ocr_promotion_matches_the_shared_classifier(
    db, patient, make_candidate, analyte, value, unit, exp_value, exp_unit
):
    from app.services.mdi.promoters import LabPromoter

    candidate = make_candidate(
        {
            "test_name": CBC_LABELS[analyte],
            "original_test_name": CBC_LABELS[analyte],
            "canonical": analyte,
            "value": value,
            "unit": unit,
            "specimen_date": "20/05/2026",
        }
    )
    outcome = LabPromoter().promote(db, candidate, actor_user_id=patient["user_id"])
    db.flush()

    row = db.get(LabResult, outcome.canonical_id)
    expected = _expected(analyte, value, unit)
    assert row.canonical_name == analyte
    assert row.normalized_value_si == pytest.approx(exp_value)
    assert row.normalized_unit_si == exp_unit
    assert row.status == expected["status"]
    assert row.original_value == pytest.approx(value)
    assert row.original_unit == unit


# ── 4. Patient correction ───────────────────────────────────────────────────


@pytest.mark.parametrize("analyte,value,unit,exp_value,exp_unit", CBC_CASES)
def test_patient_correction_matches_the_shared_classifier(
    db, patient, analyte, value, unit, exp_value, exp_unit
):
    batch = LabUploadBatch(
        patient_id=patient["patient_id"], lab_name="P", test_date=dt.date(2026, 5, 20)
    )
    db.add(batch)
    db.flush()
    row = LabResult(
        patient_id=patient["patient_id"],
        batch_id=batch.id,
        test_name=CBC_LABELS[analyte],
        canonical_name=analyte,
        value=1.0,
        unit=exp_unit,
        test_date=dt.date(2026, 5, 20),
        verified_by_user=True,
        original_value=1.0,
        original_unit=exp_unit,
    )
    db.add(row)
    db.flush()

    lab.correct_lab_result(
        db,
        result_id=row.id,
        patient_id=patient["patient_id"],
        requester_id=patient["user_id"],
        new_value=value,
        new_unit=unit,
    )
    db.flush()
    db.refresh(row)

    expected = _expected(analyte, value, unit)
    assert row.normalized_value_si == pytest.approx(exp_value)
    assert row.normalized_unit_si == exp_unit
    assert row.status == expected["status"]
    assert row.original_value == pytest.approx(value)
    assert row.original_unit == unit


# ── 5. The paths must agree with EACH OTHER ─────────────────────────────────


@pytest.mark.parametrize("analyte,value,unit,exp_value,exp_unit", CBC_CASES)
def test_manual_and_ocr_paths_agree_with_each_other(
    client, patient, db, make_candidate, analyte, value, unit, exp_value, exp_unit
):
    """The property that actually matters. Comparing each path to a constant
    would still pass if two paths were wrong in the same way; this compares the
    stored rows themselves."""
    from app.services.mdi.promoters import LabPromoter

    resp = client.post(
        f"/api/v1/patients/{patient['patient_id']}/lab-results",
        json={
            "test_date": "2026-05-20",
            "results": [{"test_name": CBC_LABELS[analyte], "value": value, "unit": unit}],
        },
        headers=patient["headers"],
    )
    assert resp.status_code in (200, 201), resp.text
    manual = _latest(db, patient, analyte)

    candidate = make_candidate(
        {
            "test_name": CBC_LABELS[analyte],
            "original_test_name": CBC_LABELS[analyte],
            "canonical": analyte,
            "value": value,
            "unit": unit,
            "specimen_date": "20/05/2026",
        }
    )
    ocr_row = db.get(
        LabResult,
        LabPromoter().promote(db, candidate, actor_user_id=patient["user_id"]).canonical_id,
    )
    db.flush()

    for attr in ("canonical_name", "normalized_unit_si", "status", "original_unit"):
        assert getattr(manual, attr) == getattr(ocr_row, attr), (
            f"{analyte}: manual and OCR disagree on {attr} — "
            f"{getattr(manual, attr)!r} vs {getattr(ocr_row, attr)!r}"
        )
    assert manual.normalized_value_si == pytest.approx(ocr_row.normalized_value_si)
    assert manual.original_value == pytest.approx(ocr_row.original_value)


# ── 6. A refusal is a refusal on every path ─────────────────────────────────


REFUSED = [
    ("hemoglobin", 140.0, "G/L"),    # count unit for a mass analyte
    ("wbc", 7.2, "g/L"),             # mass unit for a cell count
    ("hemoglobin", 14.0, "banana"),  # unknown
]


@pytest.mark.parametrize("analyte,value,unit", REFUSED)
def test_manual_entry_refuses_what_the_registry_refuses(
    client, patient, analyte, value, unit
):
    """422 with the accepted units named — a bare "fix the unit" is how g/L gets
    retyped as g/dL with the number untouched."""
    resp = client.post(
        f"/api/v1/patients/{patient['patient_id']}/lab-results",
        json={
            "test_date": "2026-05-20",
            "results": [{"test_name": CBC_LABELS[analyte], "value": value, "unit": unit}],
        },
        headers=patient["headers"],
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail.get("accepted_units"), detail


@pytest.mark.parametrize("analyte,value,unit", REFUSED)
def test_ocr_promotion_refuses_what_the_registry_refuses(
    db, patient, make_candidate, analyte, value, unit
):
    from app.services.mdi.promoter import PromotionInvalid
    from app.services.mdi.promoters import LabPromoter

    candidate = make_candidate(
        {
            "test_name": CBC_LABELS[analyte],
            "canonical": analyte,
            "value": value,
            "unit": unit,
        }
    )
    with pytest.raises(PromotionInvalid):
        LabPromoter().promote(db, candidate, actor_user_id=patient["user_id"])
