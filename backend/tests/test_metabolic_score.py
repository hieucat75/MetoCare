"""Metabolic score tests — explainable, bounded, reference-only."""

from __future__ import annotations

from app.domain import metabolic_score
from app.domain.metabolic_score import MetabolicInputs, ScoreBand


def test_healthy_profile_is_good():
    r = metabolic_score.compute(
        MetabolicInputs(waist_cm=80, hba1c=5.2, triglyceride=100, hdl=55, systolic_bp=118)
    )
    assert r.band == ScoreBand.GOOD
    assert 0 <= r.score < 25


def test_high_risk_profile_is_high_concern():
    r = metabolic_score.compute(
        MetabolicInputs(
            waist_cm=110, hba1c=7.5, triglyceride=260, hdl=30, systolic_bp=150, is_male=True
        )
    )
    assert r.band == ScoreBand.HIGH_CONCERN
    assert r.score >= 75


def test_score_is_clamped_and_explained():
    r = metabolic_score.compute(
        MetabolicInputs(waist_cm=130, hba1c=11, triglyceride=600, hdl=20, systolic_bp=190)
    )
    assert 0 <= r.score <= 100
    assert r.factors
    assert "không thay thế tư vấn bác sĩ" in r.explanation


def test_missing_inputs_contribute_zero():
    r = metabolic_score.compute(MetabolicInputs())
    assert r.score == 0
    assert r.band == ScoreBand.GOOD
