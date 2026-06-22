"""Insight content + composition safety (PA-11, AC8).

Asserts the authored rule content and every composed insight string:
  - pass guardrails.check_output (no diagnosis / prescription / dose / downplay),
  - carry the mandatory disclaimer,
  - and that abnormal statuses always yield meaning + risk + lifestyle + follow-up
    (AC1–AC4 at the unit level, no DB needed).
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.domain import insight_content as ic
from app.domain.guardrails import check_output
from app.domain.policies import DISCLAIMER_VI
from app.models.clinical import HealthMetric
from app.services import clinical_insight as ci


def _all_content_strings():
    for c in [*ic.CONTENT.values(), ic._GENERIC]:
        yield c["meaning"]
        yield from c["lifestyle"]
        for sc in c["by_status"].values():
            yield from sc["risks"]


def test_authored_content_passes_guardrails():
    for text in _all_content_strings():
        assert check_output(text + " " + DISCLAIMER_VI).allowed, f"blocked: {text!r}"


def test_all_authored_biomarkers_present():
    # 12 priority biomarkers authored + generic fallback wired.
    assert len(ic.CONTENT) == 12
    assert ic.get_content("totally_unknown_marker") is ic._GENERIC


def _metric(metric_type, value, unit, status, days_ago=0):
    return HealthMetric(
        patient_id="p",
        metric_type=metric_type,
        value=value,
        unit=unit,
        status=status,
        measured_at=dt.datetime(2026, 6, 1) - dt.timedelta(days=days_ago),
        source="manual",
    )


@pytest.mark.parametrize(
    "metric_type,value,unit,status",
    [
        ("tsh", 0.03, "mIU/L", "low"),
        ("fasting_glucose", 5.73, "mmol/L", "high"),
        ("ldl", 3.59, "mmol/L", "high"),
        ("alt", 80.0, "U/L", "high"),  # > ref_high 56 → genuinely high
        ("blood_pressure_systolic", 150.0, "mmHg", "high"),
    ],
)
def test_abnormal_insight_has_all_fields_and_disclaimer(metric_type, value, unit, status):
    insight = ci.build_metric_insight(metric_type, [_metric(metric_type, value, unit, status)])
    assert insight.meaning.strip()          # AC1
    assert insight.trend.label.strip()      # AC2
    assert len(insight.risks) >= 1          # AC3
    assert len(insight.lifestyle) >= 1      # AC4
    assert insight.follow_up.strip()        # AC4
    assert insight.disclaimer == DISCLAIMER_VI
    # AC8: composed strings carry no prohibited language.
    for text in [insight.meaning, insight.follow_up, *insight.risks, *insight.lifestyle]:
        assert check_output(text).allowed, f"prohibited: {text!r}"


def test_normal_metric_has_no_risk_bullets():
    insight = ci.build_metric_insight(
        "fasting_glucose", [_metric("fasting_glucose", 5.0, "mmol/L", "normal")]
    )
    assert insight.status == "normal"
    assert insight.risks == []
    assert insight.priority == "monitor"
    assert insight.meaning.strip()  # still explains meaning


def test_unknown_marker_uses_safe_generic():
    insight = ci.build_metric_insight(
        "some_rare_marker", [_metric("some_rare_marker", 1.0, "x", "high")]
    )
    assert insight.meaning == ic._GENERIC["meaning"]
    assert len(insight.lifestyle) >= 1
    assert check_output(insight.meaning).allowed


def test_mmol_lab_status_reclassified_over_wrong_stored():
    """Codex P1: glucose 5.73 mmol/L (~103 mg/dL = HIGH) may be promoted with a
    wrong stored status 'normal'. The unit-aware classifier must win for known
    biomarkers, so the abnormal value is not hidden from /insights."""
    insight = ci.build_metric_insight(
        "fasting_glucose", [_metric("fasting_glucose", 5.73, "mmol/L", "normal")]
    )
    assert insight.status == "high"
    assert len(insight.risks) >= 1


def test_mixed_unit_trend_is_normalized():
    """Codex P2: prev 129 mg/dL then cur 3.59 mmol/L (~138.8 mg/dL) is a slight
    increase, not a ~97% drop — both readings normalised before % change."""
    rows = [
        _metric("ldl", 3.59, "mmol/L", "high", days_ago=0),   # newest
        _metric("ldl", 129.0, "mg/dL", "high", days_ago=2),   # previous
    ]
    insight = ci.build_metric_insight("ldl", rows)
    assert insight.trend.direction == "up"
    assert insight.trend.improved is False  # LDL up = worse
    assert insight.trend.pct is not None and 0 < insight.trend.pct < 25


def test_si_unit_lab_not_falsely_flagged():
    """Codex P1 (round 2): creatinine 80 µmol/L (~0.9 mg/dL, normal) must NOT be
    compared to the mg/dL range and become critical — trust the stored status when
    the unit is unconvertible; classify-from-raw only when the unit matches."""
    insight = ci.build_metric_insight(
        "creatinine", [_metric("creatinine", 80.0, "µmol/L", "normal")]
    )
    assert insight.status == "normal"
    assert insight.risks == []
    # And with no stored status, an unconvertible SI unit stays 'unknown', not high.
    unknown = ci.build_metric_insight(
        "creatinine", [_metric("creatinine", 80.0, "µmol/L", None)]
    )
    assert unknown.status == "unknown"


def test_low_blood_pressure_dropping_is_not_improved():
    """Codex P2: a low BP falling 90 → 80 (still low) is worse, not improved."""
    rows = [
        _metric("blood_pressure_systolic", 80.0, "mmHg", "low", days_ago=0),
        _metric("blood_pressure_systolic", 90.0, "mmHg", "low", days_ago=2),
    ]
    insight = ci.build_metric_insight("blood_pressure", rows)
    assert insight.trend.improved is False


def test_abnormal_without_bespoke_status_gets_generic_risk():
    """Codex P2: low HbA1c has no bespoke 'low' block → generic abnormal content
    so the insight still carries a risk bullet (not an empty 'monitor')."""
    insight = ci.build_metric_insight("hba1c", [_metric("hba1c", 3.0, "%", "low")])
    assert insight.status == "low"
    assert len(insight.risks) >= 1
    assert insight.priority in {"watch", "see_doctor"}
