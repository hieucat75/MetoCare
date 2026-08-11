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

from app.core.clinical_thresholds import get_vital_thresholds_dict
from app.domain import insight_content as ic
from app.domain import policies
from app.domain.guardrails import check_output
from app.domain.lab_interpreter import (
    _ALIAS_INDEX,
    LabStatus,
    classify_value,
)
from app.domain.metabolic_score import ScoreBand
from app.models.clinical import HealthMetric
from app.services import metabolic_live

ABNORMAL: frozenset[str] = frozenset({"low", "high", "critical"})
_SEVERITY: dict[str, int] = {"normal": 0, "unknown": 0, "low": 1, "high": 1, "critical": 2}

# mmol/L → mg/dL: reuse the live-score factors + lipids the classifier needs.
_MMOL_TO_MGDL: dict[str, float] = {
    **metabolic_live._MMOL_TO_MGDL,
    "ldl": 38.67,
    "total_cholesterol": 38.67,
}

# Supported manual VITALS (not lab biomarkers): board-sourced CRITICAL bounds from
# clinical_thresholds + normal-range (low_below, high_at) bounds aligned to the
# metabolic score (systolic ≥140 = high). Lets us classify a manually-logged BP
# instead of trusting a possibly-wrong stored status.
_VITAL_CRITICAL: dict[str, dict[str, float]] = get_vital_thresholds_dict()
_VITAL_RANGES: dict[str, tuple[float, float]] = {
    "blood_pressure_systolic": (90.0, 140.0),
    "blood_pressure_diastolic": (60.0, 90.0),
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
    "blood_pressure_systolic": "Huyết áp (tâm thu)",
    "blood_pressure_diastolic": "Huyết áp (tâm trương)",
    "weight": "Cân nặng",
    "waist_cm": "Vòng eo",
}

_TONE_THRESHOLD_PCT = 2.0  # |%| below this is "flat"


@dataclass(frozen=True)
class Trend:
    direction: str  # "up" | "down" | "flat" | "none"
    pct: float | None  # signed % change vs previous reading
    improved: bool | None  # True=better, False=worse, None=stable/unknown
    label: str  # patient-facing narrative


@dataclass(frozen=True)
class MetricInsight:
    metric_type: str
    label: str
    value: float
    unit: str | None
    # P0 clinical-integrity: ORIGINAL value+unit as recorded (value/unit stay
    # canonical for internal classification). Surfaced by MetricInsightOut.
    original_value: float | None
    original_unit: str | None
    status: str  # normal | low | high | critical | unknown
    trend: Trend
    meaning: str
    risks: list[str]
    lifestyle: list[str]
    follow_up: str
    priority: str  # monitor | watch | see_doctor
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
    overall_risk: str = "low"  # low | medium | high
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


def _canonical(metric_type: str) -> str | None:
    """Exact canonical biomarker key for a metric_type, or None for non-lab
    metrics. Uses ONLY exact alias lookup — never fuzzy substring matching, which
    would mis-map 'diastolic'→ast or 'pressure'→urea."""
    spec = _ALIAS_INDEX.get((metric_type or "").strip().lower())
    return spec.canonical if spec else None


def _lab_canonical(metric_type: str) -> str | None:
    """Lab canonical for a metric_type, resolving exact lab aliases AND the
    insight-only aliases (ldl_c→ldl, hdl_c→hdl, cholesterol→total_cholesterol) so
    those are classified, not dropped. None for non-lab metrics (BP, weight, …)."""
    canon = _canonical(metric_type)
    if canon:
        return canon
    aliased = ic.METRIC_TYPE_ALIASES.get((metric_type or "").strip().lower())
    return _canonical(aliased) if aliased else None


def _classify_vital(metric_type: str, value: float, unit: str) -> str | None:
    """Classify a supported manual vital (blood pressure) from board-sourced
    critical bounds + normal-range bounds — so a manually-logged systolic 150
    (which `create_metric` may store as 'normal') is correctly 'high'. Returns
    None for non-vital metrics or a mismatched unit."""
    if metric_type not in _VITAL_RANGES:
        return None
    if unit and "mmhg" not in unit:
        return None
    crit = _VITAL_CRITICAL.get(metric_type, {})
    if crit.get("critical_high") is not None and value >= crit["critical_high"]:
        return "critical"
    if crit.get("critical_low") is not None and value <= crit["critical_low"]:
        return "critical"
    low_below, high_at = _VITAL_RANGES[metric_type]
    if value >= high_at:
        return "high"
    if value < low_below:
        return "low"
    return "normal"


def _status(row: HealthMetric) -> str:
    """Resolve a metric's status, unit-safely.

    For a known lab biomarker, classify whenever the value can be expressed in
    the classifier's reference unit — either the unit already matches, or it is a
    convertible mmol/L. The classifier is then **authoritative**: it applies the
    CRITICAL thresholds that the generic metric writer / lab promotion does NOT,
    so e.g. HbA1c 12%, ALT 400 U/L or TSH 0.005 mIU/L are escalated to
    ``critical`` even if stored merely as ``high``/``low`` (and glucose 5.73
    mmol/L is read as HIGH rather than a wrongly-stored ``normal``).

    Otherwise (non-lab metric like BP/weight, or an unconvertible SI unit such as
    creatinine µmol/L) trust the stored status, which was computed in the
    reading's own unit at write time. This avoids SI-vs-mg/dL false positives."""
    canon = _lab_canonical(row.metric_type)
    unit = (row.unit or "").lower()

    # CBC dimensional guard — this surface feeds abnormal_findings, the overall
    # risk escalation and the Meto AI context, so a row the two patient screens
    # already refuse to classify must not re-enter as "critical" here. The
    # `not unit` branch below would otherwise classify a unitless `rbc 0.50`
    # directly, which is the incident value.
    from app.domain.analyte_units import ALLOWED_UNITS, is_unsafe_pair, to_canonical_unit

    if canon and canon in ALLOWED_UNITS:
        if is_unsafe_pair(canon, row.unit):
            return "unknown"
        _conv = to_canonical_unit(canon, row.value, row.unit)
        if _conv is None:
            return "unknown"
        _st = classify_value(canon, _conv[0])
        return "unknown" if _st == LabStatus.UNKNOWN else _st.value

    if canon and canon in _ALIAS_INDEX:
        spec = _ALIAS_INDEX[canon]
        value_in_ref: float | None = None
        if canon in _MMOL_TO_MGDL and "mmol" in unit:
            value_in_ref = _to_mgdl(canon, row.value, row.unit)
        elif not unit or unit == spec.unit.lower():
            value_in_ref = row.value
        if value_in_ref is not None:
            st = classify_value(canon, value_in_ref)
            if st != LabStatus.UNKNOWN:
                return st.value
    stored = (row.status or "").strip().lower()
    # Supported manual vital (BP) — classify rather than trust a default 'normal',
    # but NEVER downgrade an abnormal status that was set from supplied custom
    # ranges (e.g. systolic 135 stored 'high' via normal_range_max=130). Take the
    # more severe of stored-abnormal vs the default-range classification.
    vital = _classify_vital(row.metric_type, row.value, unit)
    if vital is not None:
        if stored in ABNORMAL and _SEVERITY[stored] > _SEVERITY[vital]:
            return stored
        return vital
    if stored in {"normal", "low", "high", "critical"}:
        return stored
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


def _improved(prev: float, cur: float, prev_status: str, cur_status: str) -> bool | None:
    """Did the metric move favourably?

    Cross-severity → toward/away from normal. Same-severity abnormal → toward the
    normal range, which is status-aware: a too-high value improves by falling, a
    too-low value improves by rising (so a low BP that drops further is NOT
    'improved')."""
    if _SEVERITY[cur_status] != _SEVERITY[prev_status]:
        return _SEVERITY[cur_status] < _SEVERITY[prev_status]
    if cur == prev:
        return None
    if cur_status == "high":  # too high → lower is better
        return cur < prev
    if cur_status == "low":  # too low → higher is better
        return cur > prev
    return None  # normal / unknown / same-bucket critical


def _compute_trend(metric_type: str, rows: list[HealthMetric]) -> Trend:
    if len(rows) < 2:
        return Trend("none", None, None, _trend_label("none", None, None))
    # Normalise both readings to a common unit (mg/dL) so a mixed-unit history
    # (e.g. mg/dL self-report then a mmol/L lab upload) yields a correct % change.
    canon = _canonical(metric_type) or ""
    cur = _to_mgdl(canon, rows[0].value, rows[0].unit)
    prev = _to_mgdl(canon, rows[1].value, rows[1].unit)
    if prev == 0:
        return Trend("none", None, None, _trend_label("none", None, None))
    pct = (cur - prev) / abs(prev) * 100.0
    direction = "flat" if abs(pct) < _TONE_THRESHOLD_PCT else ("up" if pct > 0 else "down")
    improved = _improved(prev, cur, _status(rows[1]), _status(rows[0]))
    pct_r = round(pct, 1)
    return Trend(direction, pct_r, improved, _trend_label(direction, pct_r, improved))


def _retest_phrase(weeks: int) -> str:
    return f"Xét nghiệm/đo lại sau khoảng {weeks} tuần."


def canonical_metric_key(metric_type: str) -> str:
    """Identity key for grouping a metric's history. Canonicalises TRUE lab
    aliases (glucose→fasting_glucose, ldl_c→ldl) so they form one trend, but
    keeps distinct measurements distinct — notably systolic vs diastolic blood
    pressure, which share content/label but must never share a trend.

    Public (no leading underscore): shared with ``app.services.clinical_copilot``
    so both modules use the exact same alias-folding identity for a metric_type
    — never duplicate this table/logic in the copilot module."""
    raw = (metric_type or "").strip().lower()
    canon = _canonical(raw)
    if canon:
        return canon
    # Insight-only aliases (ldl_c→ldl, weight_kg→weight, waist→waist_cm, …) merge
    # too, EXCEPT the blood-pressure collapse (systolic/diastolic stay distinct).
    aliased = ic.METRIC_TYPE_ALIASES.get(raw)
    if aliased and aliased != "blood_pressure":
        return aliased
    return raw


# Backward-compat alias — some existing tests/call sites reference the original
# private name directly. The implementation lives in exactly one place above.
_group_key = canonical_metric_key


def _label(metric_type: str) -> str:
    # Raw metric_type first (distinguishes BP components), then the content key.
    return _LABELS.get(metric_type) or _LABELS.get(ic.content_key(metric_type), metric_type)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def _history(db: Session, patient_id: str) -> dict[str, list[HealthMetric]]:
    rows = list(
        db.execute(
            select(HealthMetric)
            .where(
                HealthMetric.patient_id == patient_id,
                HealthMetric.deleted_at.is_(None),
            )
            .order_by(HealthMetric.measured_at.desc())
        ).scalars()
    )
    by_type: dict[str, list[HealthMetric]] = {}
    for r in rows:
        by_type.setdefault(canonical_metric_key(r.metric_type), []).append(r)  # newest-first
    return by_type


def build_metric_insight(metric_type: str, rows: list[HealthMetric]) -> MetricInsight:
    """Compose the full insight for one metric from its reading history
    (newest-first). Always returns meaning + trend + risks + lifestyle +
    follow-up (AC1–AC4)."""
    cur = rows[0]
    status = _status(cur)
    content = ic.get_content(metric_type)
    status_content = content["by_status"].get(status)
    if status_content is None and status in ABNORMAL:
        # Abnormal but no bespoke block (e.g. low HbA1c, high HDL) → safe generic
        # abnormal content so the insight still carries risk + appropriate urgency.
        status_content = ic._GENERIC["by_status"].get(status)
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
        original_value=(
            cur.original_value if cur.original_value is not None else cur.value
        ),
        original_unit=(cur.original_unit if cur.original_unit is not None else cur.unit),
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
    key = canonical_metric_key(metric_type)
    rows = _history(db, patient_id).get(key)
    if not rows:
        return None
    return build_metric_insight(key, rows)


_RISK_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2}


def _overall_risk(
    db: Session, patient_id: str, abnormal_count: int, *, has_critical: bool = False
) -> str:
    """Overall risk = the higher of the metabolic-band risk and the findings risk,
    so non-metabolic findings (e.g. a critical TSH while metabolic inputs are
    GOOD) are never understated. Any critical finding ⇒ high."""
    if has_critical:
        count_risk = "high"
    else:
        count_risk = "low" if abnormal_count == 0 else ("medium" if abnormal_count <= 2 else "high")
    band_risk = count_risk
    result = metabolic_live.compute_live_score(db, patient_id=patient_id)
    if result is not None:
        if result.band == ScoreBand.GOOD:
            band_risk = "low"
        elif result.band == ScoreBand.FAIR:
            band_risk = "medium"
        else:
            band_risk = "high"  # ELEVATED / HIGH_CONCERN
    return max(band_risk, count_risk, key=lambda r: _RISK_RANK[r])


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

    has_critical = any(i.status == "critical" for i in abnormal)
    overall_risk = _overall_risk(db, patient_id, len(abnormal), has_critical=has_critical)
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
