"""Clinical Insight Service (PA-11).

Composes patient-facing guidance from existing rules engines — **rules-first**,
no LLM in v1. Pipeline per metric:

    latest + history (health_metrics)
      → status   (HealthMetric.status, else lab_interpreter.classify_value)
      → trend    (latest vs previous: direction, %, improved?)
      → content  (insight_content.get_content: meaning / risks / lifestyle / retest)
      → guardrail-validated output (+ DISCLAIMER_VI)

Nothing is persisted. Read-only. No diagnosis / prescription / dose advice — the
content is pre-vetted against policies and every composed string is re-checked
through ``guardrails.check_output`` (defense in depth).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import insight_content as ic
from app.domain import policies
from app.domain.guardrails import check_output
from app.domain.lab_interpreter import (
    _ALIAS_INDEX,
    LabStatus,
    classify_value,
    normalize_biomarker,
)
from app.domain.metabolic_score import ScoreBand
from app.models.clinical import HealthMetric
from app.services import metabolic_live

ABNORMAL: frozenset[str] = frozenset({"low", "high", "critical"})
_SEVERITY: dict[str, int] = {"normal": 0, "unknown": 0, "low": 1, "high": 1, "critical": 2}

# Direction-of-good per content key (for same-severity trend judgement). TSH is
# intentionally absent (both directions can be unfavourable → severity-only).
_LOWER_BETTER: frozenset[str] = frozenset({
    "fasting_glucose", "hba1c", "ldl", "total_cholesterol", "triglyceride",
    "alt", "ast", "blood_pressure", "weight", "waist_cm",
})
_HIGHER_BETTER: frozenset[str] = frozenset({"hdl"})

# mmol/L → mg/dL: reuse the live-score factors + lipids the classifier needs.
_MMOL_TO_MGDL: dict[str, float] = {
    **metabolic_live._MMOL_TO_MGDL,
    "ldl": 38.67,
    "total_cholesterol": 38.67,
}

# Vietnamese display labels for the authored metrics (fallback = metric_type).
_LABELS: dict[str, str] = {
    "tsh": "TSH",
    "fasting_glucose": "Đường huyết lúc đói",
    "hba1c": "HbA1c",
    "alt": "Men gan ALT",
    "ast": "Men gan AST",
    "ldl": "LDL (cholesterol xấu)",
    "total_cholesterol": "Cholesterol toàn phần",
    "hdl": "HDL (cholesterol tốt)",
    "triglyceride": "Triglyceride",
    "blood_pressure": "Huyết áp",
    "weight": "Cân nặng",
    "waist_cm": "Vòng eo",
}

_TONE_THRESHOLD_PCT = 2.0  # |%| below this is "flat"


@dataclass(frozen=True)
class Trend:
    direction: str           # "up" | "down" | "flat" | "none"
    pct: float | None        # signed % change vs previous reading
    improved: bool | None    # True=better, False=worse, None=stable/unknown
    label: str               # patient-facing narrative


@dataclass(frozen=True)
class MetricInsight:
    metric_type: str
    label: str
    value: float
    unit: str | None
    status: str              # normal | low | high | critical | unknown
    trend: Trend
    meaning: str
    risks: list[str]
    lifestyle: list[str]
    follow_up: str
    priority: str            # monitor | watch | see_doctor
    priority_label: str
    disclaimer: str = policies.DISCLAIMER_VI


@dataclass(frozen=True)
class HealthSummary:
    abnormal_count: int
    improved: list[str] = field(default_factory=list)
    worsened: list[str] = field(default_factory=list)
    stable: list[str] = field(default_factory=list)
    positives: list[str] = field(default_factory=list)
    focus: list[str] = field(default_factory=list)
    overall_risk: str = "low"   # low | medium | high
    top_action: str = ""
    disclaimer: str = policies.DISCLAIMER_VI


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _safe(text: str) -> str:
    """Re-validate composed patient text; replace with a neutral line if blocked."""
    if check_output(text).allowed:
        return text
    return "Bạn nên trao đổi với bác sĩ để được tư vấn cụ thể."


def _to_mgdl(canon: str, value: float, unit: str | None) -> float:
    if unit and "mmol" in unit.lower() and canon in _MMOL_TO_MGDL:
        return value * _MMOL_TO_MGDL[canon]
    return value


def _status(row: HealthMetric) -> str:
    """Prefer the stored status (computed in the reading's own unit at write
    time); fall back to the lab classifier for known biomarkers."""
    stored = (row.status or "").strip().lower()
    if stored in {"normal", "low", "high", "critical"}:
        return stored
    canon = normalize_biomarker(row.metric_type)
    if canon and canon in _ALIAS_INDEX:
        st = classify_value(canon, _to_mgdl(canon, row.value, row.unit))
        if st != LabStatus.UNKNOWN:
            return st.value
    return "unknown"


def _trend_label(direction: str, pct: float | None, improved: bool | None) -> str:
    if direction == "none" or pct is None:
        return "Chưa có dữ liệu lần trước để so sánh."
    if direction == "flat":
        base = "≈ gần như không thay đổi"
    else:
        verb = "tăng" if direction == "up" else "giảm"
        base = f"{'↑' if direction == 'up' else '↓'} {verb} {abs(pct):.1f}%"
    if improved is True:
        return base + " — xu hướng tốt hơn"
    if improved is False:
        return base + " — xu hướng cần chú ý"
    return base


def _improved(ckey: str, prev: float, cur: float, prev_status: str, cur_status: str) -> bool | None:
    if _SEVERITY[cur_status] != _SEVERITY[prev_status]:
        return _SEVERITY[cur_status] < _SEVERITY[prev_status]
    if cur_status == "normal":
        return None  # stable and within range
    if ckey in _LOWER_BETTER:
        return None if cur == prev else cur < prev
    if ckey in _HIGHER_BETTER:
        return None if cur == prev else cur > prev
    return None  # ambiguous marker, same severity


def _compute_trend(metric_type: str, rows: list[HealthMetric]) -> Trend:
    if len(rows) < 2 or rows[1].value == 0:
        return Trend("none", None, None, _trend_label("none", None, None))
    cur, prev = rows[0].value, rows[1].value
    pct = (cur - prev) / abs(prev) * 100.0
    direction = "flat" if abs(pct) < _TONE_THRESHOLD_PCT else ("up" if pct > 0 else "down")
    ckey = ic.content_key(metric_type)
    improved = _improved(ckey, prev, cur, _status(rows[1]), _status(rows[0]))
    pct_r = round(pct, 1)
    return Trend(direction, pct_r, improved, _trend_label(direction, pct_r, improved))


def _retest_phrase(weeks: int) -> str:
    return f"Xét nghiệm/đo lại sau khoảng {weeks} tuần."


def _label(metric_type: str) -> str:
    return _LABELS.get(ic.content_key(metric_type), metric_type)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def _history(db: Session, patient_id: str) -> dict[str, list[HealthMetric]]:
    rows = list(
        db.execute(
            select(HealthMetric)
            .where(HealthMetric.patient_id == patient_id)
            .order_by(HealthMetric.measured_at.desc())
        ).scalars()
    )
    by_type: dict[str, list[HealthMetric]] = {}
    for r in rows:
        by_type.setdefault(r.metric_type, []).append(r)  # newest-first per type
    return by_type


def build_metric_insight(metric_type: str, rows: list[HealthMetric]) -> MetricInsight:
    """Compose the full insight for one metric from its reading history
    (newest-first). Always returns meaning + trend + risks + lifestyle +
    follow-up (AC1–AC4)."""
    cur = rows[0]
    status = _status(cur)
    content = ic.get_content(metric_type)
    status_content = content["by_status"].get(status)
    if status_content is not None:
        risks = [_safe(r) for r in status_content["risks"]]
        priority = status_content["priority"]
    else:
        # normal / unknown → reassurance, no risk bullets, lowest priority.
        risks = []
        priority = "monitor"
    trend = _compute_trend(metric_type, rows)
    follow_up = _safe(
        f"{_retest_phrase(content['retest_weeks'])} {ic.FOLLOWUP_BY_PRIORITY[priority]}"
    )
    return MetricInsight(
        metric_type=metric_type,
        label=_label(metric_type),
        value=cur.value,
        unit=cur.unit,
        status=status,
        trend=trend,
        meaning=_safe(content["meaning"]),
        risks=risks,
        lifestyle=[_safe(x) for x in content["lifestyle"]],
        follow_up=follow_up,
        priority=priority,
        priority_label=ic.PRIORITY_LABEL_VI[priority],
    )


def list_insights(
    db: Session, *, patient_id: str, abnormal_only: bool = True
) -> list[MetricInsight]:
    """Insights for the patient's metrics (latest reading each). By default only
    noteworthy (abnormal) metrics, worst-first."""
    insights = [build_metric_insight(mt, rows) for mt, rows in _history(db, patient_id).items()]
    if abnormal_only:
        insights = [i for i in insights if i.status in ABNORMAL]
    insights.sort(key=lambda i: _SEVERITY.get(i.status, 0), reverse=True)
    return insights


def get_insight(db: Session, *, patient_id: str, metric_type: str) -> MetricInsight | None:
    """Single-metric insight for the detail card (returns even when normal)."""
    rows = _history(db, patient_id).get(metric_type)
    if not rows:
        return None
    return build_metric_insight(metric_type, rows)


def _overall_risk(db: Session, patient_id: str, abnormal_count: int) -> str:
    result = metabolic_live.compute_live_score(db, patient_id=patient_id)
    if result is not None:
        if result.band in (ScoreBand.GOOD,):
            return "low"
        if result.band in (ScoreBand.FAIR,):
            return "medium"
        return "high"  # ELEVATED / HIGH_CONCERN
    if abnormal_count == 0:
        return "low"
    return "medium" if abnormal_count <= 2 else "high"


def build_health_summary(db: Session, *, patient_id: str) -> HealthSummary:
    """'Tóm tắt sức khỏe lần này' + 'Điều gì thay đổi từ lần trước?' data (AC5/AC6)."""
    insights = [build_metric_insight(mt, rows) for mt, rows in _history(db, patient_id).items()]
    abnormal = [i for i in insights if i.status in ABNORMAL]
    abnormal.sort(key=lambda i: _SEVERITY.get(i.status, 0), reverse=True)

    def _change_entry(i: MetricInsight) -> str:
        t = i.trend
        if t.direction in ("up", "down") and t.pct is not None:
            return f"{i.label} {'tăng' if t.direction == 'up' else 'giảm'} {abs(t.pct):.1f}%"
        return f"{i.label} gần như không đổi"

    improved = [_change_entry(i) for i in insights if i.trend.improved is True]
    worsened = [_change_entry(i) for i in insights if i.trend.improved is False]
    stable = [i.label for i in insights if i.trend.improved is None and i.trend.direction != "none"]
    positives = [i.label for i in insights if i.trend.improved is True]
    focus = [i.label for i in abnormal]

    overall_risk = _overall_risk(db, patient_id, len(abnormal))
    if focus:
        lead = ", ".join(focus[:2])
        top_action = _safe(
            f"Tháng này nên tập trung theo dõi: {lead}. "
            "Hãy trao đổi với bác sĩ về các chỉ số cần chú ý."
        )
    else:
        top_action = _safe("Duy trì thói quen lành mạnh và theo dõi chỉ số định kỳ.")

    return HealthSummary(
        abnormal_count=len(abnormal),
        improved=improved,
        worsened=worsened,
        stable=stable,
        positives=positives,
        focus=focus,
        overall_risk=overall_risk,
        top_action=top_action,
    )
