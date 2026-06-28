"""Tests for HealthTimelineEngine (E20).

Uses simple mock objects (SimpleNamespace) for DB rows — no DB required.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from uuid import uuid4

from app.domain.health_timeline import (
    HealthTimelineEngine,
    TimelineEvent,
    classify_bp,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _batch(
    *,
    batch_id: str | None = None,
    test_date: dt.date | None = None,
    lab_name: str = "Lab A",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=batch_id or str(uuid4()),
        test_date=test_date or dt.date(2025, 3, 1),
        lab_name=lab_name,
        created_at=dt.datetime(2025, 3, 1),
    )


def _result(
    *,
    batch_id: str,
    test_name: str = "Glucose",
    canonical_name: str | None = "glucose",
    status: str = "normal",
    test_date: dt.date | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=str(uuid4()),
        batch_id=batch_id,
        test_name=test_name,
        canonical_name=canonical_name,
        status=status,
        test_date=test_date or dt.date(2025, 3, 1),
        value=5.0,
        unit="mmol/L",
    )


def _metric(
    *,
    metric_type: str,
    value: float,
    measured_at: dt.datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=str(uuid4()),
        metric_type=metric_type,
        value=value,
        measured_at=measured_at or dt.datetime(2025, 3, 15),
    )


def _medication(
    *,
    name: str = "Metformin",
    dose: str | None = "500mg",
    frequency: str | None = "2 lần/ngày",
    created_at: dt.datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=str(uuid4()),
        name=name,
        dose=dose,
        frequency=frequency,
        created_at=created_at or dt.datetime(2025, 2, 1),
    )


def _symptom(
    *,
    description: str = "Đau đầu",
    severity: int | None = 3,
    reported_at: dt.datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=str(uuid4()),
        description=description,
        severity=severity,
        reported_at=reported_at or dt.datetime(2025, 4, 1),
    )


def _engine() -> HealthTimelineEngine:
    return HealthTimelineEngine()


def _build(
    engine: HealthTimelineEngine | None = None,
    *,
    lab_batches=(),
    lab_results=(),
    health_metrics=(),
    medications=(),
    symptom_logs=(),
    **kwargs,
) -> list[TimelineEvent]:
    e = engine or _engine()
    return e.build(
        lab_batches=list(lab_batches),
        lab_results=list(lab_results),
        health_metrics=list(health_metrics),
        medications=list(medications),
        symptom_logs=list(symptom_logs),
        **kwargs,
    )


# ── Tests: basic ──────────────────────────────────────────────────────────────

def test_timeline_empty_sources():
    engine = _engine()
    events = _build(engine)
    assert events == []

    summary = engine.summarize(events, [])
    assert summary.total_events == 0
    assert len(summary.missing_longitudinal_vi) >= 1
    assert any("dữ liệu" in m for m in summary.missing_longitudinal_vi)


# ── Tests: lab events ─────────────────────────────────────────────────────────

def test_lab_event_normal():
    bid = str(uuid4())
    batch = _batch(batch_id=bid)
    results = [_result(batch_id=bid, status="normal"), _result(batch_id=bid, status="normal")]
    events = _build(lab_batches=[batch], lab_results=results)
    assert len(events) == 1
    e = events[0]
    assert e.event_type == "lab_result"
    assert e.importance == "info"
    assert e.source == "lab_result"


def test_lab_event_abnormal():
    bid = str(uuid4())
    batch = _batch(batch_id=bid)
    results = [
        _result(batch_id=bid, status="normal"),
        _result(batch_id=bid, test_name="LDL", canonical_name="ldl", status="high"),
    ]
    events = _build(lab_batches=[batch], lab_results=results)
    assert len(events) == 1
    e = events[0]
    assert e.event_type == "abnormal_lab"
    assert e.importance in ("watch", "warning")
    assert "ldl" in e.related_markers


def test_lab_event_abnormal_critical():
    bid = str(uuid4())
    batch = _batch(batch_id=bid)
    results = [_result(batch_id=bid, test_name="Glucose", status="critical")]
    events = _build(lab_batches=[batch], lab_results=results)
    assert events[0].importance == "warning"


# ── Tests: BP classification ──────────────────────────────────────────────────

def test_bp_classification_normal():
    level, label, summary = classify_bp(115, 75)
    assert level == "normal"
    assert "bình thường" in label


def test_bp_classification_elevated():
    level, label, summary = classify_bp(132, 82)
    assert level == "elevated"
    assert "tăng nhẹ" in label


def test_bp_classification_high():
    level, label, summary = classify_bp(145, 92)
    assert level == "high"
    assert "cao" in label


def test_bp_classification_urgent():
    level, label, summary = classify_bp(185, 110)
    assert level == "urgent_red_flag"
    assert "rất cao" in label or "y tế" in summary


# ── Tests: BP events ──────────────────────────────────────────────────────────

def test_bp_pairing_same_day():
    date = dt.datetime(2025, 5, 1, 9, 0)
    sys_m = _metric(metric_type="bp_systolic", value=125.0, measured_at=date)
    dia_m = _metric(metric_type="bp_diastolic", value=80.0, measured_at=date)
    events = _build(health_metrics=[sys_m, dia_m])
    bp_events = [e for e in events if e.event_type == "blood_pressure"]
    assert len(bp_events) == 1
    e = bp_events[0]
    assert e.metadata["systolic"] == 125.0
    assert e.metadata["diastolic"] == 80.0


def test_bp_unpaired_systolic():
    date = dt.datetime(2025, 5, 2, 9, 0)
    sys_m = _metric(metric_type="bp_systolic", value=130.0, measured_at=date)
    events = _build(health_metrics=[sys_m])
    bp_events = [e for e in events if e.event_type == "blood_pressure"]
    assert len(bp_events) == 1
    e = bp_events[0]
    assert e.metadata["diastolic"] is None


# ── Tests: weight events ──────────────────────────────────────────────────────

def test_weight_change_significant():
    m1 = _metric(metric_type="weight_kg", value=80.0, measured_at=dt.datetime(2025, 1, 1))
    m2 = _metric(metric_type="weight_kg", value=77.0, measured_at=dt.datetime(2025, 2, 1))
    events = _build(health_metrics=[m1, m2])
    weight_events = [e for e in events if e.event_type == "weight_change"]
    assert len(weight_events) == 1
    e = weight_events[0]
    assert e.metadata["delta_kg"] == -3.0
    assert "giảm" in e.title_vi


def test_weight_change_insignificant():
    m1 = _metric(metric_type="weight_kg", value=80.0, measured_at=dt.datetime(2025, 1, 1))
    m2 = _metric(metric_type="weight_kg", value=80.5, measured_at=dt.datetime(2025, 2, 1))
    events = _build(health_metrics=[m1, m2])
    weight_events = [e for e in events if e.event_type == "weight_change"]
    assert len(weight_events) == 0


# ── Tests: medication events ──────────────────────────────────────────────────

def test_medication_event():
    med = _medication(name="Metformin", dose="500mg", frequency="2 lần/ngày")
    events = _build(medications=[med])
    med_events = [e for e in events if e.event_type == "medication_started"]
    assert len(med_events) == 1
    e = med_events[0]
    assert "Metformin" in e.title_vi
    assert e.source == "medication"
    assert e.importance == "info"


# ── Tests: symptom events ─────────────────────────────────────────────────────

def test_symptom_event():
    log = _symptom(description="Đau đầu nhẹ", severity=2)
    events = _build(symptom_logs=[log])
    sym_events = [e for e in events if e.event_type == "symptom"]
    assert len(sym_events) == 1
    e = sym_events[0]
    assert "Đau đầu nhẹ" in e.summary_vi
    assert e.source == "symptom"


def test_symptom_severity_importance():
    log = _symptom(description="Đau ngực nặng", severity=8)
    events = _build(symptom_logs=[log])
    e = events[0]
    assert e.importance == "warning"


def test_symptom_medium_severity_importance():
    log = _symptom(description="Mệt mỏi", severity=5)
    events = _build(symptom_logs=[log])
    assert events[0].importance == "watch"


def test_symptom_low_severity_importance():
    log = _symptom(description="Nhẹ", severity=2)
    events = _build(symptom_logs=[log])
    assert events[0].importance == "info"


# ── Tests: ordering and filters ───────────────────────────────────────────────

def test_timeline_ordering():
    """Events should be sorted newest first."""
    sym1 = _symptom(reported_at=dt.datetime(2025, 1, 1))
    sym2 = _symptom(reported_at=dt.datetime(2025, 6, 1))
    sym3 = _symptom(reported_at=dt.datetime(2025, 3, 15))
    events = _build(symptom_logs=[sym1, sym2, sym3])
    dates = [e.date for e in events]
    assert dates == sorted(dates, reverse=True)


def test_date_filter_from():
    from_date = dt.date(2025, 4, 1)
    old = _symptom(reported_at=dt.datetime(2025, 1, 15))
    new = _symptom(reported_at=dt.datetime(2025, 5, 1))
    events = _build(symptom_logs=[old, new], from_date=from_date)
    assert len(events) == 1
    assert events[0].date >= from_date


def test_date_filter_to():
    to_date = dt.date(2025, 3, 31)
    old = _symptom(reported_at=dt.datetime(2025, 2, 1))
    new = _symptom(reported_at=dt.datetime(2025, 5, 1))
    events = _build(symptom_logs=[old, new], to_date=to_date)
    assert len(events) == 1
    assert events[0].date <= to_date


def test_limit():
    symptoms = [_symptom(reported_at=dt.datetime(2025, 1, i + 1)) for i in range(20)]
    events = _build(symptom_logs=symptoms, limit=5)
    assert len(events) == 5


def test_event_type_filter():
    med = _medication()
    sym = _symptom()
    events = _build(medications=[med], symptom_logs=[sym], event_type_filter="symptom")
    assert all(e.event_type == "symptom" for e in events)
    assert len(events) == 1


# ── Tests: summary ────────────────────────────────────────────────────────────

def test_summary_improved():
    """Canonical with high→normal over time → in improved_areas."""
    bid1 = str(uuid4())
    bid2 = str(uuid4())
    batch1 = _batch(batch_id=bid1, test_date=dt.date(2025, 1, 1))
    batch2 = _batch(batch_id=bid2, test_date=dt.date(2025, 6, 1))
    r1 = _result(batch_id=bid1, canonical_name="ldl", status="high", test_date=dt.date(2025, 1, 1))
    r2 = _result(batch_id=bid2, canonical_name="ldl", status="normal", test_date=dt.date(2025, 6, 1))

    engine = _engine()
    events = _build(engine, lab_batches=[batch1, batch2], lab_results=[r1, r2])
    summary = engine.summarize(events, [r1, r2])
    assert "ldl" in summary.improved_areas


def test_summary_worsened():
    """Canonical with normal→high → in worsened_areas."""
    bid1 = str(uuid4())
    bid2 = str(uuid4())
    batch1 = _batch(batch_id=bid1, test_date=dt.date(2025, 1, 1))
    batch2 = _batch(batch_id=bid2, test_date=dt.date(2025, 6, 1))
    r1 = _result(batch_id=bid1, canonical_name="glucose", status="normal", test_date=dt.date(2025, 1, 1))
    r2 = _result(batch_id=bid2, canonical_name="glucose", status="high", test_date=dt.date(2025, 6, 1))

    engine = _engine()
    events = _build(engine, lab_batches=[batch1, batch2], lab_results=[r1, r2])
    summary = engine.summarize(events, [r1, r2])
    assert "glucose" in summary.worsened_areas


# ── Tests: safety / no diagnosis language ─────────────────────────────────────

def test_no_diagnosis_language():
    """No event should contain forbidden clinical language."""
    bid = str(uuid4())
    batch = _batch(batch_id=bid)
    results = [_result(batch_id=bid, status="critical")]
    med = _medication()
    sym = _symptom(description="Đau ngực", severity=8)
    m1 = _metric(metric_type="weight_kg", value=80.0, measured_at=dt.datetime(2025, 1, 1))
    m2 = _metric(metric_type="weight_kg", value=85.0, measured_at=dt.datetime(2025, 3, 1))
    sys_m = _metric(metric_type="bp_systolic", value=185.0, measured_at=dt.datetime(2025, 4, 1))
    dia_m = _metric(metric_type="bp_diastolic", value=115.0, measured_at=dt.datetime(2025, 4, 1))

    events = _build(
        lab_batches=[batch],
        lab_results=results,
        medications=[med],
        symptom_logs=[sym],
        health_metrics=[m1, m2, sys_m, dia_m],
    )

    forbidden = ["chẩn đoán", "bệnh", "điều trị"]
    for event in events:
        text = f"{event.title_vi} {event.summary_vi}".lower()
        for word in forbidden:
            assert word not in text, (
                f"Forbidden word '{word}' found in event '{event.event_id}': {text!r}"
            )


# ── Tests: data span ──────────────────────────────────────────────────────────

def test_data_span_days():
    sym1 = _symptom(reported_at=dt.datetime(2025, 1, 1))
    sym2 = _symptom(reported_at=dt.datetime(2025, 6, 1))
    engine = _engine()
    events = _build(engine, symptom_logs=[sym1, sym2])
    summary = engine.summarize(events, [])
    # Jan 1 to Jun 1 = 151 days
    assert summary.data_span_days == 151
    assert summary.total_events == 2
