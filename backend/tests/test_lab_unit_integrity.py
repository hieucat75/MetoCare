"""P0 clinical-integrity regression: original lab units reach AI/UI; no float artifacts.

Covers branch ``fix/lab-unit-integrity-p0``:

* ``format_lab_value`` trims insignificant trailing zeros, caps at 2 decimals,
  and never emits a raw IEEE float artifact.
* ``ContextBuilder._build_recent_labs`` / ``_build_recent_metrics`` and
  ``patient_summary.build_summary`` surface the ORIGINAL value + unit
  (e.g. ``88 µmol/L``) — never the canonical/SI-converted number.
* A full ``PromptAssembler`` system prompt for a µmol/L creatinine patient shows
  the original ``88 µmol/L`` and none of the four known artifact substrings.
* ``normalize_value_to_si`` internal conversion is unaffected (classification
  keeps working on canonical units).
"""

from __future__ import annotations

import datetime as dt
import json
import os

import pytest
from app.ai.context.builder import ContextBuilder
from app.ai.context.schemas import ScreenContext
from app.ai.prompt.assembler import PromptAssembler
from app.domain.lab_normalization import normalize_value_to_si
from app.models.clinical import HealthMetric, LabResult, LabUploadBatch
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from app.services import patient_summary
from app.utils.number_format import format_lab_value

# The four canonical/SI IEEE-float artifacts that must NEVER surface to a user/AI.
ARTIFACTS = [
    "0.9916099199999999",
    "174.48289999999997",
    "103.24314000000001",
    "39.056700000000001",
]

# (metric_type, test_name, original_value, original_unit, canonical_value, canonical_unit)
# Each row's ORIGINAL unit is one of the 8 units required by the spec. The canonical
# `value`/`unit` deliberately differ (and four of them ARE the artifact literals) so a
# leak of the canonical number would be caught by the artifact assertions below.
SEED_ROWS: list[tuple[str, str, float, str, float, str]] = [
    ("creatinine", "Creatinine", 88.0, "µmol/L", 0.9916099199999999, "mg/dL"),
    ("total_cholesterol", "Cholesterol", 9.68, "mmol/L", 174.48289999999997, "mg/dL"),
    ("fasting_glucose", "Glucose", 103.0, "mg/dL", 103.24314000000001, "mg/dL"),
    ("hba1c", "HbA1c", 6.5, "%", 39.056700000000001, "mg/dL"),
    ("alt", "ALT", 32.0, "IU/L", 32.0, "IU/L"),
    ("ast", "AST", 28.0, "U/L", 28.0, "U/L"),
    ("tsh", "TSH", 2.5, "µIU/mL", 2.5, "µIU/mL"),
    ("free_t4", "Free T4", 15.0, "pmol/L", 15.0, "pmol/L"),
]

# Original value+unit tokens every surface MUST show (creatinine first — it is the
# newest metric, so it survives the 5-most-recent cap in metrics/vitals).
EXPECTED_ORIGINAL_TOKENS = [
    "88",  # creatinine µmol/L → integer
    "µmol/L",
    "mmol/L",
    "IU/L",
    "U/L",
    "µIU/mL",
    "pmol/L",
]


@pytest.fixture
def seeded(db):
    """Seed a user + profile + one lab batch with 8 labs and 8 metrics.

    Both the lab_results (canonical value differs from original) and the
    health_metrics carry ``original_value``/``original_unit``. Creatinine is the
    newest reading so it is guaranteed to appear in the 5-row metric/vital caps.
    """
    user = User(
        email=f"integrity-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Integrity Test",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Integrity Test", waist_cm=90)
    db.add(profile)
    db.flush()

    today = dt.date.today()
    now = dt.datetime.now(dt.UTC)
    batch = LabUploadBatch(patient_id=profile.id, lab_name="Test Lab", test_date=today)
    db.add(batch)
    db.flush()

    for idx, (mtype, tname, ov, ou, cv, cu) in enumerate(SEED_ROWS):
        db.add(
            LabResult(
                patient_id=profile.id,
                batch_id=batch.id,
                test_name=tname,
                canonical_name=mtype,
                value=cv,  # canonical (converted) — internal only
                unit=cu,
                reference_range="—",
                status="normal",
                test_date=today,
                verified_by_user=True,
                original_value=ov,
                original_unit=ou,
                original_reference_range="ref",
                original_test_name=tname,
            )
        )
        db.add(
            HealthMetric(
                patient_id=profile.id,
                metric_type=mtype,
                value=cv,  # canonical (converted) — internal classification only
                unit=cu,
                original_value=ov,
                original_unit=ou,
                # Creatinine (idx 0) newest → survives the 5-most-recent cap.
                measured_at=now - dt.timedelta(minutes=idx),
                source="lab_result",
                status="normal",
            )
        )
    db.commit()
    return {"user_id": user.id, "patient_id": profile.id}


# ---------------------------------------------------------------------------
# format_lab_value — table-driven artifact/precision guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,unit,expected",
    [
        (0.9916099199999999, "mg/dL", "1"),
        (0.9916099199999999, "µmol/L", "1"),
        (174.48289999999997, "mg/dL", "174"),
        (103.24314000000001, "mg/dL", "103"),
        (39.056700000000001, "mg/dL", "39"),
        (25.0, None, "25"),
        (88.0, "µmol/L", "88"),
        (14.50, "g/dL", "14.5"),
        (14.0, "g/dL", "14"),
    ],
)
def test_format_lab_value_strips_artifacts_and_zeros(value, unit, expected) -> None:
    out = format_lab_value(value, unit)
    assert out == expected
    # Never an IEEE artifact.
    for art in ARTIFACTS:
        assert art not in out
    # Never more than 2 decimals; trailing zeros trimmed.
    if "." in out:
        assert len(out.split(".", 1)[1]) <= 2
        assert not out.endswith("0")


def test_format_lab_value_never_exceeds_two_decimals() -> None:
    for v in [1.23456, 0.99999, 123.45678, 88.0, 14.50, 0.9916099199999999]:
        out = format_lab_value(v, "foobar")
        if "." in out:
            assert len(out.split(".", 1)[1]) <= 2
            assert not out.endswith("0")
        for art in ARTIFACTS:
            assert art not in out


# ---------------------------------------------------------------------------
# Unit-preservation regression — the core acceptance
# ---------------------------------------------------------------------------


def test_context_builders_surface_original_units(seeded, db) -> None:
    builder = ContextBuilder()
    labs = builder._build_recent_labs(db, seeded["user_id"])
    metrics = builder._build_recent_metrics(db, seeded["user_id"])

    assert labs is not None and metrics is not None
    labs_text = json.dumps(labs, ensure_ascii=False)
    metrics_text = json.dumps(metrics, ensure_ascii=False)

    # Every original unit shows up in the labs block (limit 10 → all 8 present).
    for token in EXPECTED_ORIGINAL_TOKENS:
        assert token in labs_text, f"missing original token {token!r} in labs"
    # Creatinine original present as a verbatim display token.
    assert "88 µmol/L" in labs_text
    # Metrics block (capped at 5, creatinine newest) shows the original creatinine.
    assert "88" in metrics_text and "µmol/L" in metrics_text

    # No canonical/converted number or artifact ever leaks into either block.
    for art in ARTIFACTS:
        assert art not in labs_text, f"artifact {art} leaked into labs"
        assert art not in metrics_text, f"artifact {art} leaked into metrics"


def test_patient_summary_surfaces_original_units(seeded, db) -> None:
    summary = patient_summary.build_summary(db, patient_id=seeded["patient_id"])
    summary_text = summary.model_dump_json()

    # Doctor summary vitals show the original creatinine value+unit.
    assert "88 µmol/L" in summary_text
    # No artifact / canonical float leaks.
    for art in ARTIFACTS:
        assert art not in summary_text, f"artifact {art} leaked into patient summary"

    # The most-recent vital (creatinine) is formatted in its ORIGINAL unit.
    creat = next(v for v in summary.vitals.latest if v["metric_type"] == "creatinine")
    assert creat["value"] == "88"
    assert creat["unit"] == "µmol/L"
    assert creat["display"] == "88 µmol/L"


# ---------------------------------------------------------------------------
# Full prompt snapshot
# ---------------------------------------------------------------------------


def test_prompt_shows_original_creatinine_no_artifacts(seeded, db) -> None:
    builder = ContextBuilder()
    ctx = builder.build(db, seeded["user_id"], ScreenContext(screen_id="dashboard"))
    system_prompt, _messages = PromptAssembler().assemble(ctx, "Xem kết quả xét nghiệm", [])

    # Original creatinine unit is present in the assembled system prompt.
    assert "88 µmol/L" in system_prompt
    # None of the four artifact substrings — and specifically no mg/dL conversion
    # of creatinine (0.9916099199999999) — reaches the LLM.
    for art in ARTIFACTS:
        assert art not in system_prompt, f"artifact {art} leaked into prompt"


# ---------------------------------------------------------------------------
# Internal conversion still works (classification unaffected)
# ---------------------------------------------------------------------------


def test_normalize_value_to_si_still_converts() -> None:
    # µmol/L creatinine → mg/dL: value must actually change (not identity).
    value, unit = normalize_value_to_si(88.0, "µmol/L", "creatinine")
    assert value is not None
    assert abs(value - 88.0) > 0.5  # converted, not passed through
    assert value < 5.0  # plausible creatinine in mg/dL
    # mmol/L cholesterol → mg/dL conversion also intact.
    chol_value, _ = normalize_value_to_si(9.68, "mmol/L", "total_cholesterol")
    assert chol_value is not None and chol_value > 100  # mg/dL magnitude
