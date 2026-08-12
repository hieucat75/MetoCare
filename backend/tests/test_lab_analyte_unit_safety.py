"""P0: an analyte and a unit from different dimensions must never yield a severity.

Production showed one stored CBC row as `rbc 0.50 L/L` = "Nguy hiểm" on the labs
screen and "Rất thấp" on the health-metrics screen. Both were confident, they
contradicted each other, and both were wrong: the row was a hematocrit fraction
filed as a red cell count.

Three defects compounded, and each is pinned here:
  1. every VN hematocrit phrase CONTAINS the RBC alias "hồng cầu", and only
     "dung tích hồng cầu" was registered as hematocrit;
  2. unit compatibility was a DENYLIST (`spec.incompatible_units`), empty for
     both analytes, so `rbc + L/L` was accepted;
  3. `rbc.physiological_min` is 0.5, so the fraction 0.50 passed the magnitude
     check and then classified CRITICAL against `critical_low = 2.5`.
"""

from __future__ import annotations

import datetime as _dt

import pytest
from app.domain.analyte_units import (
    NEEDS_REVIEW_MESSAGE,
    UnitCompatibility,
    is_unsafe_pair,
    resolve_erythrocyte_analyte,
    to_canonical_unit,
    unit_compatibility,
)
from app.schemas.health import MetricOut
from app.schemas.lab import LabResultOut
from app.services.lab_parser import parse_lab_text

_NOW = _dt.datetime(2026, 6, 15, tzinfo=_dt.UTC)

# --------------------------------------------------------------------------- #
# Unit compatibility — fail closed
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("unit", ["10^12/L", "10¹²/L", "T/L", "x10^12/L", "10^6/uL"])
def test_rbc_accepts_only_count_per_volume_units(unit):
    assert unit_compatibility("rbc", unit) in (
        UnitCompatibility.CANONICAL,
        UnitCompatibility.CONVERTIBLE,
    )
    assert not is_unsafe_pair("rbc", unit)


@pytest.mark.parametrize("unit", ["L/L", "%", "ratio"])
def test_rbc_rejects_volume_fraction_units(unit):
    """The exact pair that produced a false "Nguy hiểm" in production."""
    assert unit_compatibility("rbc", unit) is UnitCompatibility.INCOMPATIBLE
    assert is_unsafe_pair("rbc", unit)


@pytest.mark.parametrize("unit", ["%", "L/L"])
def test_hematocrit_accepts_percent_and_fraction(unit):
    assert not is_unsafe_pair("hematocrit", unit)


@pytest.mark.parametrize("unit", ["10^12/L", "T/L"])
def test_hematocrit_rejects_count_units(unit):
    assert unit_compatibility("hematocrit", unit) is UnitCompatibility.INCOMPATIBLE
    assert is_unsafe_pair("hematocrit", unit)


@pytest.mark.parametrize("unit", ["mg/dL", "mmol/L", "banana", "", None])
def test_unknown_unit_is_refused_not_assumed_compatible(unit):
    """A denylist accepts anything unlisted. An allowlist must not."""
    assert unit_compatibility("rbc", unit) is UnitCompatibility.UNKNOWN
    assert is_unsafe_pair("rbc", unit)


def test_unguarded_analytes_are_untouched():
    """Scoped hotfix: analytes without an allowlist keep existing behaviour."""
    assert unit_compatibility("glucose", "mg/dL") is UnitCompatibility.NOT_GUARDED
    assert not is_unsafe_pair("glucose", "anything")


# --------------------------------------------------------------------------- #
# Conversion — relabelling without converting is the original bug
# --------------------------------------------------------------------------- #


def test_hematocrit_fraction_converts_to_percent():
    assert to_canonical_unit("hematocrit", 0.50, "L/L") == (50.0, "%")
    assert to_canonical_unit("hematocrit", 0.42, "L/L") == (42.0, "%")
    assert to_canonical_unit("hematocrit", 0.47, "L/L") == (47.0, "%")


def test_percent_is_already_canonical():
    assert to_canonical_unit("hematocrit", 50.0, "%") == (50.0, "%")


def test_conversion_refused_for_foreign_unit():
    assert to_canonical_unit("rbc", 0.50, "L/L") is None


def test_analyte_is_resolved_by_dimension_not_magnitude():
    assert resolve_erythrocyte_analyte("L/L") == "hematocrit"
    assert resolve_erythrocyte_analyte("%") == "hematocrit"
    assert resolve_erythrocyte_analyte("10^12/L") == "rbc"
    assert resolve_erythrocyte_analyte("T/L") == "rbc"
    assert resolve_erythrocyte_analyte("mg/dL") is None


# --------------------------------------------------------------------------- #
# Parser: Vietnamese label matrix
# --------------------------------------------------------------------------- #


def _parse_one(line: str):
    rows = parse_lab_text(line)
    return rows[0] if rows else None


@pytest.mark.parametrize(
    "label",
    [
        "Dung tích hồng cầu",
        "Thể tích khối hồng cầu",
        "Tỷ lệ thể tích hồng cầu",
        "Hematocrit",
        "HCT",
    ],
)
def test_vietnamese_hematocrit_labels_resolve_to_hematocrit(label):
    """Every one of these contains "hồng cầu"; none may become an RBC count."""
    row = _parse_one(f"{label}: 0.50 L/L")
    assert row is not None, label
    assert row.test_name == "hematocrit", f"{label} -> {row.test_name}"
    assert row.value == 50.0, f"{label} kept the fraction instead of converting"
    assert row.unit == "%"


def test_ambiguous_hong_cau_with_fraction_unit_becomes_hematocrit():
    row = _parse_one("Hồng cầu: 0.50 L/L")
    assert row is not None
    assert row.test_name == "hematocrit"
    assert row.value == 50.0
    assert row.unit == "%"


def test_ambiguous_hong_cau_with_count_unit_stays_rbc():
    for unit in ("10^12/L", "T/L"):
        row = _parse_one(f"Hồng cầu: 5.0 {unit}")
        assert row is not None, unit
        assert row.test_name == "rbc", unit
        assert row.value == 5.0


@pytest.mark.parametrize("unit", ["10^12/L", "T/L"])
def test_explicit_rbc_with_count_unit_is_accepted(unit):
    row = _parse_one(f"RBC: 5.0 {unit}")
    assert row is not None
    assert row.test_name == "rbc"
    assert row.value == 5.0


def test_explicit_rbc_with_fraction_unit_is_not_emitted():
    """Never relabel an explicit analyte — that guesses which half is wrong."""
    assert _parse_one("RBC: 0.50 L/L") is None


def test_explicit_hct_with_count_unit_is_not_emitted():
    assert _parse_one("HCT: 5.0 10^12/L") is None


def test_hct_percent_is_parsed_directly():
    row = _parse_one("HCT: 50 %")
    assert row is not None
    assert row.test_name == "hematocrit"
    assert row.value == 50.0


# --------------------------------------------------------------------------- #
# Read path: rows ALREADY in production, before any remediation
# --------------------------------------------------------------------------- #


def _lab_row(**kw) -> LabResultOut:
    base = dict(
        id="r1",
        patient_id="p1",
        document_id=None,
        test_name="Hồng cầu (RBC)",
        canonical_name="rbc",
        value=0.50,
        unit="L/L",
        reference_range="0.42-0.47 L/L",
        status="critical",
        test_date=None,
        verified_by_user=False,
        created_at=_NOW,
    )
    base.update(kw)
    return LabResultOut(**base)


def test_labs_screen_refuses_to_classify_the_stored_bad_row():
    """The row that displayed "Nguy hiểm". It must make no clinical claim."""
    out = _lab_row()
    assert out.status == "unknown"
    assert out.clinical_message == NEEDS_REVIEW_MESSAGE


def test_metrics_screen_refuses_to_classify_the_same_row():
    """The screen that displayed "Rất thấp" for that same record."""
    out = MetricOut(
        id="m1",
        patient_id="p1",
        metric_type="rbc",
        value=0.50,
        unit="L/L",
        status="low",
        measured_at=_NOW,
    )
    assert out.status == "unknown"
    assert out.is_critical is False
    assert out.clinical_message == NEEDS_REVIEW_MESSAGE


def test_both_screens_agree_on_the_same_stored_row():
    """The defining symptom was disagreement. Pin agreement, not just safety."""
    lab = _lab_row()
    metric = MetricOut(
        id="m1",
        patient_id="p1",
        metric_type="rbc",
        value=0.50,
        unit="L/L",
        status="critical",
        measured_at=_NOW,
    )
    assert lab.status == metric.status == "unknown"
    assert lab.clinical_message == metric.clinical_message == NEEDS_REVIEW_MESSAGE


def test_an_upstream_supplied_severity_is_still_overridden():
    """A severity handed in by a caller is exactly as unsupportable."""
    out = MetricOut(
        id="m1",
        patient_id="p1",
        metric_type="rbc",
        value=0.50,
        unit="L/L",
        status="critical",
        is_critical=True,
        clinical_message="Nguy hiểm",
        measured_at=_NOW,
    )
    assert out.is_critical is False
    assert out.clinical_message == NEEDS_REVIEW_MESSAGE


def test_a_healthy_rbc_row_is_unaffected():
    """The guard must not blunt real classification."""
    out = _lab_row(value=5.0, unit="10^12/L", reference_range="4.2-5.9", status="normal")
    assert out.status != "unknown"
    assert out.clinical_message != NEEDS_REVIEW_MESSAGE


def test_a_correct_hematocrit_row_is_unaffected():
    out = _lab_row(
        canonical_name="hematocrit",
        test_name="Hematocrit (HCT)",
        value=50.0,
        unit="%",
        reference_range="36-50",
        status="normal",
    )
    assert out.status != "unknown"


# --------------------------------------------------------------------------- #
# Clinical-review findings (PR #153 round 1)
# --------------------------------------------------------------------------- #


def test_stored_hematocrit_fraction_is_converted_not_called_critical():
    """P0-1: `hematocrit + L/L` is CONVERTIBLE, so the old guard called it safe —
    but nothing converted, so 0.45 classified against critical_low=20 and a
    NORMAL hematocrit rendered "Nguy hiểm". This is the population that never hit
    the RBC mis-mapping at all, because its label was already correct."""
    out = _lab_row(
        canonical_name="hematocrit",
        test_name="Dung tích hồng cầu",
        value=0.45,
        unit="L/L",
        reference_range="0.36-0.50 L/L",
        status=None,
    )
    assert out.status == "normal", out.status
    assert out.status != "critical"


def test_metrics_screen_also_converts_the_stored_fraction():
    out = MetricOut(
        id="m1",
        patient_id="p1",
        metric_type="hematocrit",
        value=0.45,
        unit="L/L",
        status="critical",
        measured_at=_NOW,
    )
    assert out.status == "normal"
    assert out.is_critical is False


def test_a_genuinely_low_hematocrit_still_classifies_low():
    """The conversion must not blunt a real abnormality: 0.25 L/L = 25 %."""
    out = _lab_row(
        canonical_name="hematocrit", value=0.25, unit="L/L", status=None
    )
    assert out.status in ("low", "critical")


def test_parser_never_fabricates_a_unit_for_a_guarded_analyte():
    """P0-2: `unit or spec.unit` turned an unlabelled "Hồng cầu 0.50" into
    `rbc 0.50 10^12/L` — canonical-looking, boundary-plausible, then CRITICAL.
    The row must not carry an invented count unit."""
    row = _parse_one("Hồng cầu: 0.50")
    if row is not None:
        assert row.unit != "10^12/L", "fabricated the canonical unit"
        assert row.unit in (None, ""), row.unit


def test_clinical_insight_does_not_resurrect_the_false_critical():
    """P1-5: this surface feeds abnormal_findings, risk escalation and AI context,
    so it must not classify what the two screens refuse to classify."""
    from types import SimpleNamespace

    from app.services.clinical_insight import _status

    incompatible = SimpleNamespace(
        metric_type="rbc", unit="L/L", value=0.50, status="critical"
    )
    assert _status(incompatible) == "unknown"

    unitless = SimpleNamespace(metric_type="rbc", unit=None, value=0.50, status=None)
    assert _status(unitless) == "unknown"


def test_clinical_insight_still_classifies_a_valid_cbc_row():
    from types import SimpleNamespace

    from app.services.clinical_insight import _status

    ok = SimpleNamespace(metric_type="rbc", unit="10^12/L", value=5.0, status=None)
    assert _status(ok) == "normal"


def test_older_vietnamese_count_units_are_not_deleted():
    """P1-3: an unlisted spelling is REFUSED, so an omission loses a real result.
    "triệu/mm³" is numerically identical to 10^12/L."""
    for unit in ("trieu/mm3", "10^6/mm3", "T/1"):
        assert not is_unsafe_pair("rbc", unit), unit


# --------------------------------------------------------------------------- #
# Clinical-review round 2: the layer BELOW the parser
# --------------------------------------------------------------------------- #


def test_interpret_panel_never_fabricates_a_unit_or_a_critical():
    """Round-2 P0: the parser stopped fabricating the unit, but `interpret_value`
    did it again one layer down (`raw.unit or spec.unit`), producing a persisted
    `rbc 0.50 10^12/L critical` — which then looked CANONICAL to the read guard.
    This drives the real chain rather than a hand-built schema object, which is
    why the round-1 fix looked complete and was not."""
    from app.domain.lab_interpreter import interpret_panel

    rows = parse_lab_text("Hồng cầu: 0.50")
    interpreted = interpret_panel(rows)
    assert "rbc" not in interpreted.critical, "false critical on a unit-free row"
    for item in interpreted.biomarkers:
        if item.canonical == "rbc":
            assert item.unit != "10^12/L", "fabricated the canonical unit"
            assert item.status.value != "critical"


def test_interpret_value_refuses_an_incompatible_pair():
    from app.domain.lab_interpreter import RawLabValue, interpret_value

    out = interpret_value(RawLabValue(test_name="rbc", value=0.50, unit="L/L"))
    assert out.status.value == "unknown"
    assert out.unit != "10^12/L"


def test_interpret_value_converts_a_hematocrit_fraction():
    """Must convert BEFORE the physiological check, or a valid 0.45 L/L is
    rejected as 'ngoài giới hạn sinh lý' against the percent bounds."""
    from app.domain.lab_interpreter import RawLabValue, interpret_value

    out = interpret_value(RawLabValue(test_name="hematocrit", value=0.45, unit="L/L"))
    assert out.status.value == "normal", out.status


def test_rbc_physiological_floor_no_longer_admits_a_fraction():
    from app.domain.lab_interpreter import _ALIAS_INDEX

    assert _ALIAS_INDEX["rbc"].physiological_min > 0.5


def test_alias_typed_metric_cannot_bypass_the_guard():
    """Round-2 P1: ALLOWED_UNITS is canonical-keyed, classify_value is alias-keyed,
    so metric_type="hct" skipped the guard and was then classified anyway."""
    out = MetricOut(
        id="m1",
        patient_id="p1",
        metric_type="hct",
        value=0.45,
        unit="L/L",
        status="critical",
        measured_at=_NOW,
    )
    assert out.is_critical is False
    assert out.status == "normal"


# --------------------------------------------------------------------------- #
# Clinical-review round 3: LEGACY rows already in the database
# --------------------------------------------------------------------------- #


def test_legacy_row_with_a_fabricated_canonical_unit_is_not_critical():
    """Round-3 P0. Before this fix the write path stamped the canonical unit onto
    unit-free rows, so `rbc 0.50 10^12/L` is ALREADY stored. It now reads as
    perfectly CANONICAL — compatible, convertible 1:1 — and classified critical
    against critical_low=2.5. The domain layer calls 0.50 impossible for a red
    cell count (physiological_min=1.0); every read path must agree."""
    out = _lab_row(value=0.50, unit="10^12/L", status="critical")
    assert out.status == "unknown", out.status
    assert out.clinical_message == NEEDS_REVIEW_MESSAGE

    metric = MetricOut(
        id="m1",
        patient_id="p1",
        metric_type="rbc",
        value=0.50,
        unit="10^12/L",
        status="critical",
        measured_at=_NOW,
    )
    assert metric.status == "unknown"
    assert metric.is_critical is False


def test_severe_anaemia_is_still_classified_not_suppressed():
    """The physiological floor must not swallow real disease: 1.5 and 2.0 are
    implausible-looking but clinically real, and must stay critical."""
    for value in (1.5, 2.0):
        out = _lab_row(value=value, unit="10^12/L", status=None)
        assert out.status == "critical", f"{value} -> {out.status}"


def test_reclassify_clears_a_stale_severity_instead_of_leaving_it_stored():
    """Round-3 P0: skipping left `status='critical'` in the DB, and four surfaces
    read the stored status raw — the Meto AI context, the doctor consult summary,
    the health timeline and the lab explanation route. Masking it on two screens
    while the LLM still calls the count critically low is not a fix."""
    from app.domain.analyte_units import guarded_status

    assert guarded_status("rbc", 0.50, "L/L")[0] == "unknown"
    assert guarded_status("rbc", 0.50, "10^12/L")[0] == "unknown"
    # and the converted, legitimate values still classify
    assert guarded_status("hematocrit", 0.45, "L/L") == ("normal", 45.0)
    assert guarded_status("rbc", 5.0, "10^12/L") == ("normal", 5.0)


def test_non_cbc_analytes_are_not_touched_by_the_guard():
    """Scope check: the helper must return None so legacy paths run unchanged."""
    from app.domain.analyte_units import guarded_status

    for canonical in ("fasting_glucose", "creatinine", "alt", "weight", "systolic"):
        assert guarded_status(canonical, 5.0, "mmol/L") is None, canonical


def test_interpret_value_quotes_the_value_in_the_range_unit():
    """Round-3: "hematocrit = 0.45 %" beside "36.0–50.0 %" let a patient derive
    catastrophic anaemia from a row classified normal."""
    from app.domain.lab_interpreter import RawLabValue, interpret_value

    out = interpret_value(RawLabValue(test_name="hematocrit", value=0.45, unit="L/L"))
    assert "0.45 %" not in out.patient_note, out.patient_note
    assert "45" in out.patient_note


# --------------------------------------------------------------------------- #
# Clinical-review round 5: the fix's OWN output must not read as reassurance
# --------------------------------------------------------------------------- #


def test_a_cleared_status_is_not_counted_as_within_normal_limits():
    """Round-5 P0. The guard clears `status` for an uninterpretable row; the
    timeline then counted it among "tất cả N chỉ số trong giới hạn bình thường"
    — a clean-result claim manufactured out of a refusal to interpret, and a
    false reassurance that did NOT exist before this hotfix."""
    from types import SimpleNamespace

    from app.domain.health_timeline import HealthTimelineEngine

    batch = SimpleNamespace(
        id="b1", test_date=_NOW.date(), lab_name="QA", created_at=_NOW
    )
    rows = [
        SimpleNamespace(
            batch_id="b1", status="normal",
            test_name="Glucose", canonical_name="fasting_glucose",
        ),
        SimpleNamespace(
            batch_id="b1", status=None,
            test_name="Hồng cầu (RBC)", canonical_name="rbc",
        ),
    ]
    events = HealthTimelineEngine()._lab_events([batch], rows)
    text = " ".join(e.summary_vi for e in events)
    assert "Tất cả 2 chỉ số trong giới hạn bình thường" not in text, text
    assert "kiểm tra lại" in text, text


def test_a_cleared_status_does_not_become_an_improvement_claim():
    """Round-5 P0, second half: `last_status` defaulted to "normal", so a
    neutralised false-critical produced "Rbc đang cải thiện — tiếp tục duy trì."."""
    import datetime as _d
    from types import SimpleNamespace

    from app.domain.health_timeline import HealthTimelineEngine, TimelineEvent

    results = [
        SimpleNamespace(canonical_name="rbc", status="critical", test_date=_d.date(2026, 1, 1)),
        SimpleNamespace(canonical_name="rbc", status=None, test_date=_d.date(2026, 6, 1)),
    ]
    events = [
        TimelineEvent(
            event_id="e1", event_type="lab_result", date=_d.date(2026, 6, 1),
            title_vi="t", summary_vi="s", source="lab_result", importance="info",
        )
    ]
    summary = HealthTimelineEngine().summarize(events, results)
    assert "rbc" not in summary.improved_areas, summary.improved_areas
    assert "cải thiện" not in (summary.biggest_change_vi or "")


# --------------------------------------------------------------------------- #
# The Azure DI table path — the one production actually runs
# --------------------------------------------------------------------------- #


def _table_row(name: str, value: str, unit: str | None):
    from app.domain.lab_table_extractor import OcrTableRow

    return OcrTableRow(
        original_test_name=name,
        display_test_name=name,
        original_value_str=value,
        original_unit=unit,
        original_reference_range=None,
    )


def test_table_path_disambiguates_the_erythrocyte_label_by_unit():
    """Staging showed the table path DROPPING "Hồng cầu 0.50 L/L" where the text
    parser converts it. Safe, but the patient loses the value — and production
    runs table-first, so the drop was the live behaviour."""
    from app.domain.lab_table_extractor import map_table_rows_to_raw_values

    rows = map_table_rows_to_raw_values(
        [_table_row("Hồng cầu", "0.50", "L/L")], hospital_id="vinmec"
    )
    assert rows, "row was dropped instead of disambiguated"
    assert rows[0].test_name == "hematocrit", rows[0].test_name
    assert rows[0].value == 50.0
    assert rows[0].unit == "%"


def test_table_path_keeps_a_real_rbc_count():
    from app.domain.lab_table_extractor import map_table_rows_to_raw_values

    rows = map_table_rows_to_raw_values(
        [_table_row("Hồng cầu", "5.0", "T/L")], hospital_id="vinmec"
    )
    assert rows and rows[0].test_name == "rbc"
    assert rows[0].value == 5.0


def test_table_path_refuses_an_explicit_analyte_with_a_foreign_unit():
    """An explicit label is never relabelled — that guesses which half is wrong."""
    from app.domain.lab_table_extractor import map_table_rows_to_raw_values

    assert map_table_rows_to_raw_values(
        [_table_row("RBC", "0.50", "L/L")], hospital_id="vinmec"
    ) == []


# --------------------------------------------------------------------------- #
# #155 — a reference-range cell must never become the measured value
# --------------------------------------------------------------------------- #


def _cell(ri: int, ci: int, text: str, header: bool = False) -> dict:
    c = {"rowIndex": ri, "columnIndex": ci, "content": text}
    if header:
        c["kind"] = "columnHeader"
    return c


def _analyze_result(header: list[str] | None, rows: list[list[str]]) -> dict:
    cells: list[dict] = []
    offset = 0
    if header is not None:
        cells += [_cell(0, ci, h, header=True) for ci, h in enumerate(header)]
        offset = 1
    for ri, row in enumerate(rows, start=offset):
        cells += [_cell(ri, ci, v) for ci, v in enumerate(row)]
    ncols = len(header or rows[0])
    return {"tables": [{"rowCount": len(rows) + offset, "columnCount": ncols, "cells": cells}]}


VN_HEADER = ["STT", "Tên xét nghiệm", "Kết quả", "Đơn vị", "Khoảng tham chiếu"]
CBC_ROWS = [
    ["1", "Hemoglobin", "140", "g/L", "130 - 170"],
    ["2", "Bạch cầu", "7.2", "G/L", "4.0 - 10.0"],
    ["3", "Tiểu cầu", "230", "G/L", "150 - 400"],
    ["4", "Hồng cầu (HCT)", "0.50", "L/L", "0.42 - 0.47"],
]


def test_range_like_cells_are_distinguished_from_measurements():
    """The discriminator already existed in _parse_reference_cell; #155 was that
    the value path never consulted it."""
    from app.domain.lab_table_extractor import _is_range_like

    for interval in ("130 - 170", "4.0-10.0", "0.42–0.47", "3.5 — 5.0", "< 5", "> 10"):
        assert _is_range_like(interval), interval
    for measurement in ("140", "7.2", "230", "140 g/L", "0.50 L/L"):
        assert not _is_range_like(measurement), measurement


def test_a_real_table_keeps_the_measured_values_and_ranges_apart():
    """The realistic Vinmec-shaped fixture: headers present, roles unambiguous."""
    from app.domain.lab_table_extractor import extract_and_map

    diag: dict = {}
    got = {
        v.test_name: (v.value, v.unit, v.ocr_reference_range)
        for v in extract_and_map(_analyze_result(VN_HEADER, CBC_ROWS), diagnostics=diag)
    }
    assert diag["ambiguous_structure"] is False
    assert got["hemoglobin"][0] == 140.0, got["hemoglobin"]
    assert got["wbc"][0] == 7.2, got["wbc"]
    assert got["platelet"][0] == 230.0, got["platelet"]
    # HCT/Hồng cầu + L/L stays disambiguated and converted (#154 must not regress).
    assert got["hematocrit"][0] == 50.0 and got["hematocrit"][1] == "%"
    assert got["hemoglobin"][2] == "130–170"
    assert got["wbc"][2] == "4.0–10.0"
    assert got["platelet"][2] == "150–400"


def test_a_range_bound_never_becomes_the_measured_value():
    """No header row, so column roles are guessed — and the guess lands on the
    reference-range column. 130 must not become the haemoglobin result."""
    from app.domain.lab_table_extractor import extract_and_map

    diag: dict = {}
    rows = extract_and_map(
        _analyze_result(
            None,
            [["Hemoglobin", "130 - 170"], ["Bạch cầu", "4.0 - 10.0"], ["Tiểu cầu", "150 - 400"]],
        ),
        diagnostics=diag,
    )
    assert diag["ambiguous_structure"] is True
    # Fails closed to the text parser rather than emitting a partial panel.
    assert rows == [], [(r.test_name, r.value) for r in rows]
    for forbidden in (130.0, 4.0, 150.0):
        assert forbidden not in [r.value for r in rows]


# --------------------------------------------------------------------------- #
# #155 remaining acceptance items — RED. These encode the three defects
# confirmed diagnostically on the realistic Azure fixture. `strict=True` means
# each one FAILS the moment the defect is fixed: delete the marker then, do not
# weaken the assertion. Layer attribution is in each docstring.
# --------------------------------------------------------------------------- #


def _cbc_row(name: str) -> object:
    from app.domain.lab_table_extractor import extract_and_map

    rows = extract_and_map(_analyze_result(VN_HEADER, CBC_ROWS))
    return next(r for r in rows if r.test_name == name)


@pytest.mark.xfail(strict=True, reason="#155 item 1 — confidence precedes normalization")
def test_hematocrit_confidence_is_computed_after_reassignment():
    """A: `clin_conf` is computed from the PRE-reassignment (value, spec) pair —
    0.50 judged against rbc's physiological floor of 1.0 — and the row is only
    then reassigned to hematocrit and converted to 50 %. Hematocrit's own bounds
    are [5, 75], so 50 is perfectly plausible; the 0.0 is purely the old analyte's
    verdict surviving. Layer: map_table_rows_to_raw_values."""
    hct = _cbc_row("hematocrit")
    assert (hct.value, hct.unit) == (50.0, "%")
    assert hct.confidence_detail.clinical == 1.0, hct.confidence_detail.clinical
    assert hct.ocr_confidence > 0.0
    assert not any("ngoài khoảng sinh lý" in r for r in hct.confidence_detail.reasons)


@pytest.mark.xfail(strict=True, reason="#155 item 2 — hemoglobin absent from the unit registry")
def test_hemoglobin_is_normalised_to_the_canonical_unit():
    """B: hemoglobin is NOT in analyte_units.ALLOWED_UNITS, so
    to_canonical_unit('hemoglobin', 140, 'g/L') returns None and 140 g/L survives
    unconverted. Its canonical unit is g/dL with bounds [1, 25], so 140 then reads
    as physiologically impossible. Same underlying fault as A: plausibility is
    judged before normalization. Layer: analyte_units registry."""
    hb = _cbc_row("hemoglobin")
    assert (hb.value, hb.unit) == (14.0, "g/dL"), (hb.value, hb.unit)
    assert hb.confidence_detail.clinical == 1.0


@pytest.mark.xfail(strict=True, reason="#155 item 3 — range is never handed to the converter")
def test_the_reference_range_is_converted_with_its_value():
    """C: the measured value is converted (0.50 L/L -> 50 %) while the range is
    carried through as the raw printed string. The converter already handles it —
    to_canonical_unit('hematocrit', 0.42, 'L/L') == (42.0, '%') — nothing calls it.
    Converting the value alone leaves 50 % sitting against a 0.42-0.47 range.
    Layer: ocr_reference_range is a raw passthrough string."""
    hct = _cbc_row("hematocrit")
    assert hct.value == 50.0
    assert hct.ocr_reference_range == "42–47", hct.ocr_reference_range


def test_the_text_parser_reads_the_same_lines_correctly():
    """Why deferring to the text path is safe rather than merely conservative."""
    from app.services import lab_parser

    got = {
        v.test_name: (v.value, v.unit)
        for v in lab_parser.parse_lab_text(
            "Hemoglobin: 140 g/L  (130 - 170)\n"
            "Bach cau: 7.2 G/L  (4.0 - 10.0)\n"
            "Tieu cau: 230 G/L  (150 - 400)\n"
            "Hong cau: 0.50 L/L  (0.42 - 0.47)\n"
        )
    }
    assert got["hemoglobin"][0] == 140.0
    assert got["wbc"][0] == 7.2
    assert got["platelet"][0] == 230.0
    assert got["hematocrit"] == (50.0, "%")
