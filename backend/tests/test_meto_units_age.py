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
from app.ai.prompt.assembler import SYSTEM_PROMPT
from app.models.patient import PatientProfile


def test_system_prompt_forbids_unit_conversion():
    """The system prompt must explicitly forbid converting lab units."""
    assert "KHÔNG quy đổi" in SYSTEM_PROMPT
    assert "đơn vị" in SYSTEM_PROMPT
    # Concrete conversion the model must not perform.
    assert "mg/dL" in SYSTEM_PROMPT and "mmol/L" in SYSTEM_PROMPT


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
