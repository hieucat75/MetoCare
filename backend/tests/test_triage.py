"""Triage tests — the red-flag false-negative target is ZERO."""

from __future__ import annotations

import pytest
from app.domain import policies, triage
from app.domain.triage import EscalationAction, RiskLevel

# Build one representative phrase per red-flag symptom from the approved list.
RED_FLAG_PHRASES = [
    (symptom, f"Tôi đang {keywords[0]}.")
    for symptom, keywords in policies.RED_FLAG_SYMPTOMS.items()
]


@pytest.mark.parametrize("symptom,phrase", RED_FLAG_PHRASES)
def test_every_red_flag_symptom_escalates(symptom, phrase):
    result = triage.assess(triage.TriageInput(symptom_text=phrase))
    assert result.risk_level == RiskLevel.EMERGENCY, f"missed red flag: {symptom}"
    assert result.action == EscalationAction.EMERGENCY_ESCALATION
    assert result.escalated_to_doctor is True
    assert result.rule_forced is True


def test_critical_vital_escalates():
    result = triage.assess(
        triage.TriageInput(vitals=[triage.VitalSign("blood_pressure_systolic", 200)])
    )
    assert result.risk_level == RiskLevel.EMERGENCY
    assert any("vital_high" in f for f in result.red_flags)


def test_critical_low_glucose_escalates():
    result = triage.assess(
        triage.TriageInput(vitals=[triage.VitalSign("fasting_glucose", 40)])
    )
    assert result.risk_level == RiskLevel.EMERGENCY


def test_borderline_vital_is_high_not_emergency():
    # 160 systolic: >= 0.85*180 (153) but < 180 critical -> HIGH, not emergency.
    result = triage.assess(
        triage.TriageInput(vitals=[triage.VitalSign("blood_pressure_systolic", 160)])
    )
    assert result.risk_level == RiskLevel.HIGH
    assert result.action == EscalationAction.DOCTOR_HANDOFF
    assert result.rule_forced is False


def test_normal_input_is_low():
    result = triage.assess(triage.TriageInput(symptom_text="Hôm nay tôi thấy khỏe."))
    assert result.risk_level == RiskLevel.LOW
    assert result.action == EscalationAction.SELF_MONITOR
    assert result.escalated_to_doctor is False


def test_high_self_reported_severity_nudges_moderate():
    result = triage.assess(triage.TriageInput(symptom_text="hơi mệt", reported_severity=8))
    assert result.risk_level == RiskLevel.MODERATE
