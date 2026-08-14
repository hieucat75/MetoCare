"""Regression: Meto must (1) report lab values in the stored unit (no conversion)
and (2) compute age by the Vietnamese year-based convention.

User report (2026-07-02):
- Meto silently converted lab units (e.g. mg/dL ↔ mmol/L) so the number no
  longer matched the patient's lab sheet — users think Meto is fabricating.
- Age was off by one: a patient born in 1975 must read 51 in 2026 (year-based),
  not 50 (birthday-precise).
"""
from __future__ import annotations

import datetime as dt

from app.ai.context.builder import ContextBuilder
from app.ai.context.schemas import AssembledContext
from app.ai.prompt.assembler import SYSTEM_PROMPT, PromptAssembler
from app.models.patient import PatientProfile


class _FakeResult:
    def __init__(self, rows: list):
        self._rows = rows

    def fetchall(self) -> list:
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    """Minimal stand-in so _build_* row shaping can be tested without a real DB."""

    def __init__(self, rows: list):
        self._rows = rows

    def execute(self, *args, **kwargs) -> _FakeResult:
        return _FakeResult(self._rows)

    def rollback(self) -> None:
        pass


def test_system_prompt_forbids_unit_conversion():
    """The system prompt must explicitly forbid converting lab units."""
    assert "KHÔNG quy đổi" in SYSTEM_PROMPT
    assert "đơn vị" in SYSTEM_PROMPT
    # Concrete conversion the model must not perform.
    assert "mg/dL" in SYSTEM_PROMPT and "mmol/L" in SYSTEM_PROMPT


def test_system_prompt_hard_locks_conversion():
    """Hard-lock: prompt must ban the conversion arithmetic and pin to `display`."""
    # The exact failure mode: 5.73 mmol/L × 18 → 103.24 mg/dL. Ban the factor.
    assert "×18" in SYSTEM_PROMPT
    # The verbatim token the model must copy instead of recomputing.
    assert "display" in SYSTEM_PROMPT
    # A reference_range in a different unit must NOT trigger value conversion.
    assert "reference_range" in SYSTEM_PROMPT


def test_recent_labs_carry_verbatim_display_token():
    """Lab rows must expose a `display` = ORIGINAL value + unit, with no conversion.

    Columns (P0): test_name, value, unit, reference_range, status, test_date,
    original_test_name, original_value, original_unit, original_reference_range.
    Here original_* are NULL so the builder falls back to the canonical columns and
    formats them in the ORIGINAL unit (5.73 mmol/L → "5.7 mmol/L", never mg/dL).
    """
    row = (
        "Glucose (fasting)", "5.73", "mmol/L", "70 - 100", "high",
        dt.date(2026, 6, 30), None, None, None, None,
        # canonical_name, normalized_value_si, normalized_unit_si — added when
        # the builder started resolving status fresh via lab_semantics
        # instead of trusting this stored 'high'. None here (no canonical
        # match / no SI pair) keeps this test on the legacy-status fallback
        # path, same as before.
        None, None, None,
    )
    labs = ContextBuilder()._build_recent_labs(_FakeDB([row]), "u1")

    assert labs is not None
    # format_lab_value rounds mmol/L to 1 decimal (5.73 → 5.7) — still the ORIGINAL unit.
    assert labs[0]["value"] == "5.7"
    assert labs[0]["unit"] == "mmol/L"
    assert labs[0]["display"] == "5.7 mmol/L"
    # The converted mg/dL number must never be pre-computed into the context.
    assert "103.24" not in labs[0]["display"]
    assert "mg/dL" not in labs[0]["display"]


def test_recent_metrics_carry_verbatim_display_token():
    """Metric rows must expose a `display` = ORIGINAL value + unit.

    Columns (P0): metric_type, value, unit, measured_at, status,
    original_value, original_unit (original_* NULL → fall back + format).
    """
    row = (
        "blood_glucose", "5.73", "mmol/L", dt.datetime(2026, 6, 30, 8, 0), "high",
        None, None,
    )
    metrics = ContextBuilder()._build_recent_metrics(_FakeDB([row]), "u1")

    assert metrics is not None
    assert metrics[0]["latest_value"] == "5.7"
    assert metrics[0]["display"] == "5.7 mmol/L"


def test_assembled_labs_block_has_no_convert_reminder():
    """The labs section must carry a no-conversion reminder next to the data."""
    ctx = AssembledContext(
        recent_labs=[{
            "test_name": "Glucose (fasting)",
            "value": "5.73",
            "unit": "mmol/L",
            "display": "5.73 mmol/L",
            "reference_range": "70 - 100",
            "status": "high",
            "collected_date": "2026-06-30",
        }],
        screen_context={"screen_id": "labs"},
    )
    system_prompt, _ = PromptAssembler().assemble(ctx, "đường huyết của tôi thế nào?", [])

    # Verbatim stored value is present; the converted value is never injected by us.
    assert "5.73 mmol/L" in system_prompt
    assert "103.24" not in system_prompt
    # Inline reminder sits in the labs block, not just the far-away system rule.
    assert "KHÔNG quy đổi" in system_prompt


def test_age_is_year_based(db, patient):
    """Born in Dec of (this_year - 51) → age must be 51 (year-based), not 50."""
    user_id = patient["user_id"]
    this_year = dt.date.today().year
    birth_year = this_year - 51
    # December DOB → birthday not yet passed for most of the year, so the old
    # birthday-precise calc would return 50. Year-based must return 51.
    dob = f"{birth_year}-12-31"

    profile = db.query(PatientProfile).filter(PatientProfile.user_id == user_id).first()
    original_dob = profile.dob
    try:
        profile.dob = dob
        db.commit()

        result = ContextBuilder()._build_user_profile(db, user_id)

        assert result is not None
        assert result["age"] == 51, (
            f"expected year-based age 51 (born {birth_year}), got {result['age']}"
        )
    finally:
        profile.dob = original_dob
        db.commit()
