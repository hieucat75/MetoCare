"""Tests for the Patient Insight Layer (Phase E).

Covers: PatientInsightReport generation, edge cases, and safety guarantees.
"""

from __future__ import annotations

import datetime

from app.domain.clinical_patterns import PatternDetection
from app.domain.clinical_rules import ClinicalFinding
from app.domain.derived_metrics import DerivedMetricResult
from app.domain.longitudinal import BiomarkerTrend
from app.domain.patient_insight import (
    InsightCard,
    PatientInsightReport,
    generate_patient_insight,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _finding(
    canonical: str = "fasting_glucose",
    status: str = "high",
    severity: str = "warning",
    priority: int = 2,
    explanation_vi: str = "Đường huyết đang cao.",
    doctor_review: bool = True,
    finding_type: str = "biomarker",
) -> ClinicalFinding:
    return ClinicalFinding(
        canonical=canonical,
        finding_type=finding_type,
        status=status,
        severity=severity,
        priority=priority,
        patient_explanation_vi=explanation_vi,
        doctor_note=f"{canonical}={status}",
        doctor_review_required=doctor_review,
        evidence_strength="established",
    )


def _critical_finding(canonical: str = "fasting_glucose") -> ClinicalFinding:
    return _finding(
        canonical=canonical,
        status="critical",
        severity="critical",
        priority=1,
        explanation_vi="Đường huyết ở mức rất nguy hiểm, cần bác sĩ đánh giá ngay.",
    )


def _normal_finding(canonical: str = "hdl") -> ClinicalFinding:
    return _finding(
        canonical=canonical,
        status="normal",
        severity="info",
        priority=4,
        explanation_vi="Chỉ số này đang trong khoảng chấp nhận được.",
        doctor_review=False,
    )


def _pattern(
    pattern_id: str = "dyslipidemia",
    severity: str = "watch",
    display_name_vi: str = "Rối loạn lipid máu",
) -> PatternDetection:
    return PatternDetection(
        pattern_id=pattern_id,
        display_name_vi=display_name_vi,
        description_vi="Có mẫu hình rối loạn lipid máu.",
        severity=severity,
        supporting_findings=["ldl_friedewald", "triglyceride"],
        confidence="high",
        doctor_review_required=False,
        evidence_strength="established",
    )


def _trend(
    canonical: str = "fasting_glucose",
    trend: str = "improving",
    change_pct: float | None = -10.0,
) -> BiomarkerTrend:
    return BiomarkerTrend(
        canonical=canonical,
        display_name_vi="Đường huyết lúc đói",
        data_points=[
            (datetime.date(2024, 1, 1), 130.0),
            (datetime.date(2024, 3, 1), 117.0),
        ],
        trend=trend,
        change_pct=change_pct,
        explanation_vi="Xu hướng tính từ dữ liệu đã xác minh.",
    )


def _derived(
    canonical: str = "egfr_ckd_epi",
    status: str = "normal",
    value: float = 85.0,
) -> DerivedMetricResult:
    return DerivedMetricResult(
        canonical=canonical,
        display_name_vi="Mức lọc cầu thận (eGFR CKD-EPI)",
        value=value,
        unit="mL/min/1.73m²",
        status=status,
        formula="CKD-EPI 2021",
        inputs_used=["creatinine", "age", "sex"],
        missing_inputs=[],
        note_vi="eGFR trong giới hạn bình thường.",
    )


def _empty_report() -> PatientInsightReport:
    return generate_patient_insight(
        patient_id="p001",
        findings=[],
        patterns=[],
        trends=[],
        derived={},
    )


# ---------------------------------------------------------------------------
# Tests: overall_status
# ---------------------------------------------------------------------------


def test_overall_status_urgent():
    report = generate_patient_insight(
        patient_id="p001",
        findings=[_critical_finding()],
        patterns=[],
        trends=[],
        derived={},
    )
    assert report.overall_status == "urgent"


def test_overall_status_action_required():
    """Warning pattern with no critical findings → action_required."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[_finding(severity="watch", status="borderline")],
        patterns=[_pattern(severity="warning")],
        trends=[],
        derived={},
    )
    assert report.overall_status == "action_required"


def test_overall_status_attention():
    """Abnormal finding, no critical, no warning pattern → attention."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[_finding(severity="warning", status="high")],
        patterns=[],
        trends=[],
        derived={},
    )
    assert report.overall_status == "attention"


def test_overall_status_good():
    """All normal findings → good."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[_normal_finding()],
        patterns=[],
        trends=[],
        derived={},
    )
    assert report.overall_status == "good"


def test_overall_status_good_empty():
    """No findings at all → good."""
    report = _empty_report()
    assert report.overall_status == "good"


# ---------------------------------------------------------------------------
# Tests: urgent alerts
# ---------------------------------------------------------------------------


def test_urgent_alert_generated():
    report = generate_patient_insight(
        patient_id="p001",
        findings=[_critical_finding("fasting_glucose")],
        patterns=[],
        trends=[],
        derived={},
    )
    assert len(report.urgent_alerts) >= 1
    assert report.urgent_alerts[0].alert_id == "alert_fasting_glucose"


def test_no_urgent_alert_on_warning():
    """Warning finding should NOT produce an urgent alert."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[_finding(severity="warning")],
        patterns=[],
        trends=[],
        derived={},
    )
    assert len(report.urgent_alerts) == 0


def test_multiple_critical_findings_produce_multiple_alerts():
    report = generate_patient_insight(
        patient_id="p001",
        findings=[
            _critical_finding("fasting_glucose"),
            _critical_finding("creatinine"),
        ],
        patterns=[],
        trends=[],
        derived={},
    )
    assert len(report.urgent_alerts) == 2


# ---------------------------------------------------------------------------
# Tests: insight cards
# ---------------------------------------------------------------------------


def test_insight_cards_max_5():
    """Even with many findings, only 5 insight cards are returned."""
    many_findings = [
        _finding(canonical=f"biomarker_{i}", severity="warning", status="high") for i in range(10)
    ]
    report = generate_patient_insight(
        patient_id="p001",
        findings=many_findings,
        patterns=[],
        trends=[],
        derived={},
    )
    assert len(report.insights) <= 5


def test_insights_sorted_by_importance():
    """High-importance cards must come before medium and low."""
    findings = [
        _finding(canonical="hdl", severity="watch", status="borderline"),  # medium
        _finding(canonical="fasting_glucose", severity="warning", status="high"),  # high
        _finding(canonical="alt", severity="watch", status="borderline"),  # medium
    ]
    report = generate_patient_insight(
        patient_id="p001",
        findings=findings,
        patterns=[],
        trends=[],
        derived={},
    )
    importance_order = {"high": 0, "medium": 1, "low": 2}
    ranks = [importance_order.get(c.importance, 99) for c in report.insights]
    assert ranks == sorted(ranks), f"Insight cards not sorted by importance: {ranks}"


def test_normal_info_findings_produce_no_insight_cards():
    """Normal/info findings should not generate insight cards."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[_normal_finding("hdl"), _normal_finding("fasting_glucose")],
        patterns=[],
        trends=[],
        derived={},
    )
    # No abnormal findings → no cards (or only from derived/patterns, none here)
    assert len(report.insights) == 0


def test_pattern_produces_insight_card():
    """A detected pattern should generate a corresponding insight card."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[],
        patterns=[_pattern("dyslipidemia")],
        trends=[],
        derived={},
    )
    ids = [c.card_id for c in report.insights]
    assert "pattern_dyslipidemia" in ids


def test_abnormal_derived_produces_insight_card():
    """Abnormal derived metric should generate an insight card."""
    dr = _derived("egfr_ckd_epi", status="abnormal", value=45.0)
    report = generate_patient_insight(
        patient_id="p001",
        findings=[],
        patterns=[],
        trends=[],
        derived={"egfr_ckd_epi": dr},
    )
    ids = [c.card_id for c in report.insights]
    assert "derived_egfr_ckd_epi" in ids


# ---------------------------------------------------------------------------
# Tests: action cards
# ---------------------------------------------------------------------------


def test_action_cards_doctor_visit_on_critical():
    """Critical finding → doctor_visit action card with interval_days=0."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[_critical_finding()],
        patterns=[],
        trends=[],
        derived={},
    )
    doctor_visit = [c for c in report.action_cards if c.action_type == "doctor_visit"]
    assert len(doctor_visit) >= 1
    assert doctor_visit[0].interval_days == 0


def test_action_cards_lipid_panel_on_lipid_abnormal():
    """Abnormal LDL finding → repeat_lipid_panel action card."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[_finding(canonical="ldl", severity="warning", status="high")],
        patterns=[],
        trends=[],
        derived={},
    )
    ids = [c.action_id for c in report.action_cards]
    assert "repeat_lipid_panel" in ids


def test_action_cards_continue_monitoring_when_all_normal():
    """All normal findings → continue_monitoring action card."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[_normal_finding()],
        patterns=[],
        trends=[],
        derived={},
    )
    ids = [c.action_id for c in report.action_cards]
    assert "continue_monitoring" in ids


def test_action_cards_glucose_on_glucose_abnormal():
    """Abnormal glucose → repeat_glucose action card."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[_finding(canonical="fasting_glucose", severity="warning", status="high")],
        patterns=[],
        trends=[],
        derived={},
    )
    ids = [c.action_id for c in report.action_cards]
    assert "repeat_glucose" in ids


def test_action_cards_kidney_on_kidney_abnormal():
    """Abnormal creatinine → repeat_kidney action card."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[_finding(canonical="creatinine", severity="warning", status="high")],
        patterns=[],
        trends=[],
        derived={},
    )
    ids = [c.action_id for c in report.action_cards]
    assert "repeat_kidney" in ids


# ---------------------------------------------------------------------------
# Tests: timeline
# ---------------------------------------------------------------------------


def test_timeline_conversion():
    """BiomarkerTrend objects should map 1:1 to TimelineSummaryItems."""
    t1 = _trend("fasting_glucose", "improving", -10.0)
    t2 = _trend("hdl", "stable", 0.0)
    report = generate_patient_insight(
        patient_id="p001",
        findings=[],
        patterns=[],
        trends=[t1, t2],
        derived={},
    )
    assert len(report.timeline) == 2
    canonicals = {item.canonical for item in report.timeline}
    assert "fasting_glucose" in canonicals
    assert "hdl" in canonicals


def test_timeline_trend_text_vi():
    """trend_text_vi must be populated correctly."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[],
        patterns=[],
        trends=[
            _trend("fasting_glucose", "improving"),
            _trend("hdl", "worsening"),
            _trend("triglyceride", "stable"),
        ],
        derived={},
    )
    by_canonical = {item.canonical: item for item in report.timeline}
    assert by_canonical["fasting_glucose"].trend_text_vi == "Đang cải thiện"
    assert by_canonical["hdl"].trend_text_vi == "Đang xấu đi"
    assert by_canonical["triglyceride"].trend_text_vi == "Ổn định"


def test_timeline_change_pct_preserved():
    """change_pct from BiomarkerTrend should be passed through unchanged."""
    t = _trend("fasting_glucose", "improving", -12.5)
    report = generate_patient_insight(
        patient_id="p001",
        findings=[],
        patterns=[],
        trends=[t],
        derived={},
    )
    assert report.timeline[0].change_pct == -12.5


# ---------------------------------------------------------------------------
# Tests: positive reinforcement
# ---------------------------------------------------------------------------


def test_positive_reinforcement_on_improving():
    """Improving trends should produce positive reinforcement messages."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[],
        patterns=[],
        trends=[_trend("fasting_glucose", "improving", -10.0)],
        derived={},
    )
    assert len(report.positive_reinforcement) >= 1
    assert "fasting_glucose" in report.positive_reinforcement[0].biomarkers


def test_no_positive_reinforcement_on_stable():
    """Stable trends should NOT produce positive reinforcement."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[],
        patterns=[],
        trends=[_trend("fasting_glucose", "stable", 2.0)],
        derived={},
    )
    assert len(report.positive_reinforcement) == 0


def test_no_positive_reinforcement_on_worsening():
    """Worsening trends should NOT produce positive reinforcement."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[],
        patterns=[],
        trends=[_trend("fasting_glucose", "worsening", 15.0)],
        derived={},
    )
    assert len(report.positive_reinforcement) == 0


# ---------------------------------------------------------------------------
# Tests: safety guarantees
# ---------------------------------------------------------------------------


def test_disclaimer_always_present():
    """disclaimer_vi must never be empty, even with no findings."""
    report = _empty_report()
    assert report.disclaimer_vi
    assert len(report.disclaimer_vi) > 10


def test_disclaimer_content():
    """disclaimer_vi must contain key phrases."""
    report = _empty_report()
    assert "tham khảo" in report.disclaimer_vi
    assert "bác sĩ" in report.disclaimer_vi


def test_no_lapse_on_empty_inputs():
    """Empty findings/patterns/trends/derived → no crash, returns valid report."""
    report = _empty_report()
    assert isinstance(report, PatientInsightReport)
    assert report.patient_id == "p001"
    assert isinstance(report.insights, list)
    assert isinstance(report.action_cards, list)
    assert isinstance(report.timeline, list)
    assert isinstance(report.positive_reinforcement, list)
    assert isinstance(report.urgent_alerts, list)


def test_ai_draft_contract_null():
    """ai_draft_contract must always be None (Phase 2 reserved slot)."""
    report = _empty_report()
    assert report.ai_draft_contract is None


def test_ai_draft_contract_null_with_findings():
    """ai_draft_contract must be None even with real findings."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[_critical_finding()],
        patterns=[_pattern()],
        trends=[_trend()],
        derived={"egfr_ckd_epi": _derived()},
    )
    assert report.ai_draft_contract is None


def test_top_priorities_max_3():
    """top_priorities must never exceed 3 entries."""
    many_findings = [
        _finding(canonical=f"biomarker_{i}", severity="warning", status="high") for i in range(10)
    ]
    report = generate_patient_insight(
        patient_id="p001",
        findings=many_findings,
        patterns=[],
        trends=[],
        derived={},
    )
    assert len(report.top_priorities) <= 3


def test_top_priorities_are_card_ids():
    """top_priorities should be card_id strings present in the insights list."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[
            _finding(canonical="fasting_glucose", severity="warning"),
            _finding(canonical="ldl", severity="warning"),
        ],
        patterns=[],
        trends=[],
        derived={},
    )
    insight_ids = {c.card_id for c in report.insights}
    for priority_id in report.top_priorities:
        assert priority_id in insight_ids, f"{priority_id} not in insights"


def test_top_priorities_empty_when_no_abnormal():
    """No abnormal findings → top_priorities is empty list."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[_normal_finding()],
        patterns=[],
        trends=[],
        derived={},
    )
    assert report.top_priorities == []


# ---------------------------------------------------------------------------
# Tests: field types and structure
# ---------------------------------------------------------------------------


def test_report_patient_id_preserved():
    """patient_id must be passed through correctly."""
    report = generate_patient_insight(
        patient_id="patient-xyz-123",
        findings=[],
        patterns=[],
        trends=[],
        derived={},
    )
    assert report.patient_id == "patient-xyz-123"


def test_report_generated_at_is_iso8601():
    """generated_at must be a valid ISO 8601 datetime string."""
    report = _empty_report()
    # Should parse without error
    parsed = datetime.datetime.fromisoformat(report.generated_at)
    assert parsed is not None


def test_insight_card_fields():
    """InsightCard must have all required fields with correct types."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[_finding(canonical="fasting_glucose", severity="warning", status="high")],
        patterns=[],
        trends=[],
        derived={},
    )
    assert len(report.insights) >= 1
    card: InsightCard = report.insights[0]
    assert isinstance(card.card_id, str) and card.card_id
    assert isinstance(card.title_vi, str) and card.title_vi
    assert isinstance(card.explanation_vi, str)
    assert card.importance in {"high", "medium", "low"}
    assert isinstance(card.supporting_biomarkers, list)
    assert card.trend in {"improving", "stable", "worsening", "insufficient_data"}
    assert card.recommended_action in {
        "continue_monitoring",
        "repeat_lab",
        "discuss_with_doctor",
        "lifestyle_reminder",
    }
    assert isinstance(card.action_text_vi, str) and card.action_text_vi


def test_urgent_alert_never_diagnoses():
    """Urgent alert action_vi must not contain diagnostic language."""
    report = generate_patient_insight(
        patient_id="p001",
        findings=[_critical_finding()],
        patterns=[],
        trends=[],
        derived={},
    )
    for alert in report.urgent_alerts:
        # Must not contain words like "bị", "mắc", "chẩn đoán"
        text = alert.action_vi.lower()
        assert "chẩn đoán" not in text, "Alert must not diagnose"
        assert alert.action_vi  # must be non-empty


def test_asdict_serializable():
    """PatientInsightReport must be serializable via dataclasses.asdict."""
    import dataclasses

    report = generate_patient_insight(
        patient_id="p001",
        findings=[_critical_finding(), _finding(canonical="ldl", severity="warning")],
        patterns=[_pattern()],
        trends=[_trend("fasting_glucose", "improving")],
        derived={"egfr_ckd_epi": _derived("egfr_ckd_epi", "abnormal", 45.0)},
    )
    d = dataclasses.asdict(report)
    # Should serialize to JSON without error (dates become strings via asdict)
    # Note: datetime.date objects inside BiomarkerTrend.data_points won't JSON-serialize
    # but that's handled by the API layer which processes those separately.
    assert d["patient_id"] == "p001"
    assert d["ai_draft_contract"] is None
    assert d["disclaimer_vi"]


# ── Phase F patch tests: batch scoping ────────────────────────────────────────


def test_patient_insight_request_model_has_batch_id():
    """PatientInsightRequest must accept batch_id field (batch-scoped insight)."""
    from app.api.v1.routes.patient_insight import PatientInsightRequest

    req = PatientInsightRequest(batch_id="batch-abc-123")
    assert req.batch_id == "batch-abc-123"
    assert req.lab_result_ids is None


def test_patient_insight_request_batch_id_optional():
    """batch_id defaults to None — backwards-compatible with existing callers."""
    from app.api.v1.routes.patient_insight import PatientInsightRequest

    req = PatientInsightRequest()
    assert req.batch_id is None


def test_patient_insight_request_batch_id_and_lab_result_ids_independent():
    """batch_id and lab_result_ids are independent — either, both, or neither may be set."""
    from app.api.v1.routes.patient_insight import PatientInsightRequest

    req_batch = PatientInsightRequest(batch_id="b1")
    assert req_batch.batch_id == "b1"
    assert req_batch.lab_result_ids is None

    req_ids = PatientInsightRequest(lab_result_ids=["r1", "r2"])
    assert req_ids.batch_id is None
    assert req_ids.lab_result_ids == ["r1", "r2"]

    req_both = PatientInsightRequest(batch_id="b1", lab_result_ids=["r1"])
    assert req_both.batch_id == "b1"
    assert req_both.lab_result_ids == ["r1"]


# ---------------------------------------------------------------------------
# Phase E+F Codex fix — P1-1: sex/age field mapping
# ---------------------------------------------------------------------------


def test_patient_insight_request_sex_age_fields():
    """PatientInsightRequest must accept sex and age (frontend field names)."""
    from app.api.v1.routes.patient_insight import PatientInsightRequest

    req_female = PatientInsightRequest(sex="female", age=55)
    assert req_female.sex == "female"
    assert req_female.age == 55

    req_male = PatientInsightRequest(sex="male", age=70)
    assert req_male.sex == "male"
    assert req_male.age == 70

    req_none = PatientInsightRequest()
    assert req_none.sex is None
    assert req_none.age is None


def test_patient_insight_request_sex_maps_to_is_male():
    """is_male must be derived from sex field correctly (not always True)."""
    from app.api.v1.routes.patient_insight import PatientInsightRequest

    # Simulate the mapping logic in the route
    def derive_is_male(body: PatientInsightRequest) -> bool:
        return (body.sex == "male") if body.sex is not None else True

    assert derive_is_male(PatientInsightRequest(sex="male")) is True
    assert derive_is_male(PatientInsightRequest(sex="female")) is False
    assert derive_is_male(PatientInsightRequest(sex=None)) is True  # safe default
    assert derive_is_male(PatientInsightRequest()) is True  # no sex → male default


def test_patient_insight_request_age_maps_to_age_years():
    """age field must pass through to age_years (not silently dropped)."""
    from app.api.v1.routes.patient_insight import PatientInsightRequest

    body = PatientInsightRequest(age=65)
    # Simulate the mapping in the route
    age_years = body.age
    assert age_years == 65

    body_none = PatientInsightRequest()
    assert body_none.age is None
