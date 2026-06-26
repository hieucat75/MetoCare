"""Longitudinal analysis for verified lab results only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .lab_interpreter import BIOMARKERS
from .lab_normalization import classify_status, normalize_value_to_si


@dataclass
class BiomarkerTrend:
    canonical: str
    display_name_vi: str
    data_points: list[tuple[date, float]]
    trend: str      # improving | stable | worsening | insufficient_data
    change_pct: float | None
    explanation_vi: str


_SPEC = {s.canonical: s for s in BIOMARKERS}


def compute_trends(results: list[object], canonical: str) -> BiomarkerTrend:
    spec = _SPEC.get(canonical)
    points: list[tuple[date, float]] = []
    for r in results:
        if not (getattr(r, "verified_by_user", False) or getattr(r, "verified_by_doctor", False)):
            continue
        c = getattr(r, "canonical_name", None) or getattr(r, "test_name", None)
        if c != canonical:
            continue
        v = getattr(r, "normalized_value_si", None)
        if v is None:
            val = getattr(r, "value", None)
            unit = getattr(r, "unit", None) or (spec.si_unit if spec else "")
            if val is None:
                continue
            if spec and unit:
                v, _ = normalize_value_to_si(val, unit, canonical)
            else:
                v = val
        d = getattr(r, "test_date", None)
        if d is None:
            continue
        points.append((d, float(v)))
    points.sort(key=lambda x: x[0])
    if len(points) < 2:
        return BiomarkerTrend(canonical, canonical, points, "insufficient_data", None, "Chưa đủ dữ liệu để đánh giá xu hướng.")  # noqa: E501
    first, last = points[0][1], points[-1][1]
    change_pct = ((last - first) / abs(first) * 100.0) if first else None
    if change_pct is not None and abs(change_pct) < 10:
        trend = "stable"
    else:
        # crude direction toward normal: compare last status to first status
        if spec:
            fs = classify_status(first, canonical)
            ls = classify_status(last, canonical)
            better = {"normal": 0, "low": 1, "high": 1, "critical": 2, "unknown": 3}
            trend = "improving" if better.get(ls.value, 9) < better.get(fs.value, 9) else "worsening"  # noqa: E501
        else:
            trend = "worsening" if last > first else "improving"
    return BiomarkerTrend(canonical, spec.canonical if spec else canonical, points, trend, round(change_pct, 2) if change_pct is not None else None, "Xu hướng được tính từ các giá trị đã xác minh và chuẩn hóa SI.")  # noqa: E501
