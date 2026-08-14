"""Regression: the 5 call sites migrated onto `lab_semantics.resolve_lab_semantics`
must consume FRESH clinical semantics, never a stale stored `status` column, and
must never carry a parallel hand-typed threshold that can silently disagree with
the canonical registry.

Background (issues #153/#154/#155): before this migration, each of these sites
either (a) trusted a STORED `status` DB column that `reclassify` (operator-run,
not automatic) could leave stale relative to the current classification rules,
or (b) hand-rolled its own threshold comparison that could silently disagree
with `lab_interpreter.BIOMARKER_SPECS` on the same value. Sites:

  1. app/ai/context/builder.py       — _ctx_resolve_semantics (Meto AI chat context)
  2. app/services/patient_summary.py — _resolve_metric_semantics (doctor pre-visit summary)
  3. app/api/v1/routes/lab.py        — _build_clinical_input (lab explanation endpoint)
  4. app/services/clinical_insight.py — _status (patient insight cards)
  5. app/domain/clinical_rules.py    — assess_biomarker CRITICAL gate

Each site test below constructs a row whose STORED status says one thing
('normal') while the value, freshly classified against the canonical registry
right now, is something else ('critical') — simulating a row never touched by
a manual reclassify pass after a threshold/backfill change — and asserts the
migrated function surfaces the FRESH classification.

Also locks the display-name consolidation (`clinical_insight._label` /
`patient_insight._display_vi` now defer to the lab catalog for biomarker keys
that overlap with it) and clinical_rules.py's documented migration boundary
(only the CRITICAL gate for a specific biomarker subset was migrated; the
WARNING/WATCH hand-typed bands are an intentional, not accidental, scope cut).
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.domain.clinical_rules import assess_biomarker
from app.domain.lab_catalog import get_catalog
from app.domain.lab_semantics import LabSemantics, resolve_lab_semantics
from app.models.clinical import HealthMetric
from app.services import clinical_insight as ci
from app.services import patient_summary

# --------------------------------------------------------------------------- #
# Shared fakes — mirrors the _FakeDB convention already used for builder.py
# tests in tests/test_meto_units_age.py (raw-SQL row shaping, no real DB).
# --------------------------------------------------------------------------- #


class _FakeResult:
    def __init__(self, rows: list):
        self._rows = rows

    def fetchall(self) -> list:
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self, rows: list):
        self._rows = rows

    def execute(self, *args, **kwargs) -> _FakeResult:
        return _FakeResult(self._rows)

    def rollback(self) -> None:
        pass


class _LabRow:
    """Minimal stand-in for app.models.clinical.LabResult, matching the
    attributes _build_clinical_input reads (same shape as the fixture in
    tests/test_clinical_consistency.py)."""

    def __init__(
        self,
        *,
        test_name: str = "HbA1c",
        canonical_name: str | None = "hba1c",
        value: float | None = 12.0,
        unit: str | None = "%",
        original_value: float | None = None,
        original_unit: str | None = None,
        normalized_value_si: float | None = None,
        normalized_unit_si: str | None = None,
        reference_range: str | None = "4 - 6",
        original_reference_range: str | None = None,
        status: str | None = "normal",
    ):
        self.test_name = test_name
        self.canonical_name = canonical_name
        self.value = value
        self.unit = unit
        self.original_value = original_value
        self.original_unit = original_unit
        self.normalized_value_si = normalized_value_si
        self.normalized_unit_si = normalized_unit_si
        self.reference_range = reference_range
        self.original_reference_range = original_reference_range
        self.status = status


def _stale_hba1c_row() -> tuple:
    """A stale-column scenario the whole file reuses: HbA1c 12% is critical
    against the canonical registry (critical_high=10.0), but the value is
    paired with a stored status of 'normal' — as it would be if the row was
    written before a threshold tightened, or a backfill never re-ran
    `reclassify` (which only walks lab_results, operator-run)."""
    truth = resolve_lab_semantics("hba1c", 12.0, "%")
    assert truth is not None and truth.status == "critical", (
        "scenario sanity check failed — hba1c 12% must be fresh-critical for "
        "this test to actually exercise stale-vs-fresh disagreement"
    )
    return truth


# =========================================================================== #
# Site 1 — app/ai/context/builder.py (Meto AI chat context)
# =========================================================================== #


def test_recent_labs_surfaces_fresh_status_over_stale_stored_column():
    """`_build_recent_labs` must return the FRESH resolve_lab_semantics status
    for a canonical/value/unit whose stored `status` column disagrees — this
    block feeds the Meto AI chat context verbatim, so a stale 'normal' here
    would tell a patient with a critical HbA1c they are fine."""
    from app.ai.context.builder import ContextBuilder

    truth = _stale_hba1c_row()
    row = (
        "HbA1c", 12.0, "%", "4 - 6", "normal",  # <- STALE stored status
        dt.date(2026, 6, 30), None, None, None, None,
        "hba1c", None, None,
    )
    labs = ContextBuilder()._build_recent_labs(_FakeDB([row]), "u1")

    assert labs is not None
    assert labs[0]["status"] == truth.status == "critical"
    assert labs[0]["status"] != "normal"
    assert labs[0]["severity"] == "critical"
    assert labs[0]["needs_review"] is False


def test_recent_metrics_surfaces_fresh_status_over_stale_stored_column():
    """Same scenario through `_build_recent_metrics` — the metrics half of
    the same AI-context block, a separate SQL query and row-shaping path."""
    from app.ai.context.builder import ContextBuilder

    truth = _stale_hba1c_row()
    row = ("hba1c", 12.0, "%", dt.datetime(2026, 6, 30, 8, 0), "normal", None, None)
    metrics = ContextBuilder()._build_recent_metrics(_FakeDB([row]), "u1")

    assert metrics is not None
    assert metrics[0]["status"] == truth.status == "critical"
    assert metrics[0]["status"] != "normal"
    assert metrics[0]["severity"] == "critical"


# =========================================================================== #
# Site 2 — app/services/patient_summary.py (doctor pre-visit summary)
# =========================================================================== #


def test_vital_row_surfaces_fresh_status_over_stale_stored_column():
    """`_vital_row` feeds the doctor-facing consult summary
    (admin_patients.py/consultations.py/patients.py routes) — a stale
    'normal' status here is the exact hazard #153/#154 were filed over,
    now surfacing to a clinician instead of a patient."""
    truth = _stale_hba1c_row()
    hm = HealthMetric(
        id="m1",
        patient_id="p1",
        metric_type="hba1c",
        value=12.0,
        unit="%",
        status="normal",  # <- STALE stored status
        measured_at=dt.datetime(2026, 6, 30, 8, 0),
        source="lab_result",
    )
    row = patient_summary._vital_row(hm)

    assert row["status"] == truth.status == "critical"
    assert row["status"] != "normal"
    assert row["severity"] == "critical"
    assert row["needs_review"] is False


# =========================================================================== #
# Site 3 — app/api/v1/routes/lab.py (lab-result explanation endpoint)
# =========================================================================== #


def test_build_clinical_input_surfaces_fresh_status_over_stale_stored_column():
    """`_build_clinical_input` feeds the Claude explanation prompt
    (canonical_status/canonical_severity/doctor_review_required) — a stale
    'normal' would produce a reassuring explanation for a critical value.

    This is a genuine pre-existing gap: tests/test_clinical_consistency.py's
    TestStatusVocabularyParity exercises this function only with
    value=None/canonical_name='glucose' rows, which always resolve to
    `semantics is None` (resolve_lab_semantics short-circuits on a missing
    value) and therefore only ever hit the row.status FALLBACK branch — never
    the fresh-resolution branch this test targets.
    """
    from app.api.v1.routes.lab import _build_clinical_input

    truth = _stale_hba1c_row()
    row = _LabRow(status="normal")  # canonical_name='hba1c', value=12.0 (defaults)

    result = _build_clinical_input(row)

    assert result["canonical_status"] == "critical" == truth.status
    assert result["canonical_status"] != "normal"
    assert result["canonical_severity"] == "critical"
    assert result["doctor_review_required"] is True


# =========================================================================== #
# Site 4 — app/services/clinical_insight.py (_status, patient insight cards)
# =========================================================================== #


def test_clinical_insight_status_surfaces_fresh_status_over_stale_stored_column():
    """`_status()` drives abnormal_findings / risk escalation / the Meto AI
    context on the patient insight surface. Existing coverage
    (test_si_unit_lab_not_falsely_flagged in
    tests/domain/test_insight_content_safety.py) only exercises scenarios
    where fresh and stored status AGREE (both land on 'normal') — it never
    proves a disagreeing stored column gets overridden."""
    truth = _stale_hba1c_row()
    hm = HealthMetric(
        id="m1",
        patient_id="p1",
        metric_type="hba1c",
        value=12.0,
        unit="%",
        status="normal",  # <- STALE stored status
        measured_at=dt.datetime(2026, 6, 30, 8, 0),
        source="lab_result",
    )
    assert ci._status(hm) == truth.status == "critical"


# =========================================================================== #
# Site 5 — app/domain/clinical_rules.py (assess_biomarker CRITICAL gate)
# =========================================================================== #
#
# assess_biomarker has no stored-status input to go stale — the defect class
# here is a hand-typed threshold literal (e.g. `value >= 500`) that could
# silently drift out of sync with the canonical registry over time. These
# tests monkeypatch the resolver itself to simulate "the registry's rules
# changed since this literal was written" and assert the CRITICAL gate moves
# WITH the fresh resolver in both directions — proving there is no parallel
# hardcoded number left that could disagree with it.
# --------------------------------------------------------------------------- #


def _fake_semantics(status: str):
    def _resolve(canonical, value, unit, **kwargs):
        return LabSemantics(
            canonical_analyte=canonical,
            display_name=canonical,
            normalized_value=value,
            normalized_unit=unit,
            reference_low=None,
            reference_high=None,
            reference_unit=unit,
            reference_display=None,
            reference_source="canonical_fallback",
            status=status,
            severity=status,
            interpretation_state="confirmed",
            needs_review=False,
            clinical_message=None,
        )

    return _resolve


def test_assess_biomarker_escalates_when_fresh_resolver_says_critical(monkeypatch):
    """fasting_glucose=120 is comfortably non-critical under the real, hand-typed
    literal (`value >= 500 or value <= 54`) that used to gate this. Force the
    resolver to say 'critical' and assert the finding escalates anyway — the
    gate is driven by the resolver's live answer, not a baked-in number."""
    import app.domain.lab_semantics as lab_semantics_module

    baseline = assess_biomarker("fasting_glucose", 120.0)
    assert baseline is not None and baseline.severity != "critical"

    monkeypatch.setattr(
        lab_semantics_module, "resolve_lab_semantics", _fake_semantics("critical")
    )
    escalated = assess_biomarker("fasting_glucose", 120.0)

    assert escalated is not None
    assert escalated.status == "critical"
    assert escalated.severity == "critical"
    assert escalated.priority == 1
    assert escalated.doctor_review_required is True


def test_assess_biomarker_does_not_escalate_when_fresh_resolver_disagrees(monkeypatch):
    """fasting_glucose=502 WOULD have been critical under the old hardcoded
    `value >= 500` literal. Force the resolver to say 'high' (not critical)
    and assert the finding does NOT become critical — it falls through to the
    ordinary warning/normal bands, proving the old literal is gone, not just
    shadowed."""
    import app.domain.lab_semantics as lab_semantics_module

    monkeypatch.setattr(
        lab_semantics_module, "resolve_lab_semantics", _fake_semantics("high")
    )
    finding = assess_biomarker("fasting_glucose", 502.0)

    assert finding is not None
    assert finding.status != "critical"
    assert finding.severity != "critical"
    assert finding.priority != 1


def test_assess_biomarker_fails_closed_when_resolver_raises(monkeypatch):
    """A resolver exception must never silently fall through to the 'normal'
    catch-all at the bottom of assess_biomarker — that is the #153/#154
    hazard verbatim (a value this function could not classify presenting as
    reassuring)."""
    import app.domain.lab_semantics as lab_semantics_module

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated resolver failure")

    monkeypatch.setattr(lab_semantics_module, "resolve_lab_semantics", _boom)
    finding = assess_biomarker("fasting_glucose", 502.0)

    assert finding is not None
    assert finding.status == "unknown"
    assert finding.status != "normal"
    assert finding.doctor_review_required is True


@pytest.mark.parametrize(
    "canonical,value",
    [
        # LDL >130 mg/dL borderline-high (AHA) — explicitly left hand-typed;
        # not one of fasting_glucose/hba1c/creatinine/sodium/potassium/hemoglobin.
        ("ldl", 140.0),
        # ALT >3x ULN — also explicitly left hand-typed.
        ("alt", 1000.0),
    ],
)
def test_unmigrated_boundary_biomarkers_still_produce_a_sensible_finding(canonical, value):
    """Documents the intentional scope boundary: LDL's >130 borderline-high
    and ALT/AST's >3xULN bands were deliberately NOT migrated onto the
    registry's coarser 4-bucket classification (see clinical_rules.py's own
    migration-boundary comment). This must still produce a real, non-crashing,
    non-'normal' finding — proving the boundary is a documented scope cut,
    not a silent regression to 'normal'."""
    finding = assess_biomarker(canonical, value)

    assert finding is not None
    assert finding.status not in ("normal", "critical")
    assert finding.severity == "warning"
    assert finding.doctor_review_required is True


# =========================================================================== #
# Display-name consolidation — clinical_insight._label / patient_insight._display_vi
# now defer to the lab catalog for overlapping (lab-biomarker) keys, closing
# the three-way name drift the original audit found (catalog vs _LABELS vs
# _DISPLAY_VI could each say something different for the same canonical).
# =========================================================================== #


def test_clinical_insight_label_matches_catalog_for_a_migrated_lab_key():
    catalog_name = get_catalog()["biomarkers"]["ldl"]["name_vn"]
    assert ci._label("ldl") == catalog_name
    # And matches what the shared resolver itself would report for this
    # canonical — the third leg of the original three-way drift.
    semantics = resolve_lab_semantics("ldl", 100.0, "mg/dL")
    assert semantics is not None
    assert ci._label("ldl") == semantics.display_name


def test_patient_insight_display_vi_matches_catalog_for_a_migrated_lab_key():
    from app.domain import patient_insight as pi

    catalog_name = get_catalog()["biomarkers"]["ldl"]["name_vn"]
    assert pi._display_vi("ldl") == catalog_name
    semantics = resolve_lab_semantics("ldl", 100.0, "mg/dL")
    assert semantics is not None
    assert pi._display_vi("ldl") == semantics.display_name


def test_clinical_insight_and_patient_insight_agree_on_a_migrated_lab_key():
    """The original audit's exact finding: two independently-maintained
    display-name dicts could disagree for the same canonical. Both now read
    the same catalog entry, so they must agree."""
    from app.domain import patient_insight as pi

    assert ci._label("ldl") == pi._display_vi("ldl")


def test_clinical_insight_label_falls_back_to_local_dict_for_non_lab_key():
    """blood_pressure has no lab-catalog entry — _label must still resolve it
    from the local _LABELS dict, not degrade to the raw metric_type key."""
    assert get_catalog()["biomarkers"].get("blood_pressure") is None
    assert ci._label("blood_pressure") == "Huyết áp"


def test_patient_insight_display_vi_falls_back_to_local_dict_for_non_lab_key():
    """tyg_index is a derived metric with no lab-catalog entry — _display_vi
    must still resolve it from the local _DISPLAY_VI dict."""
    from app.domain import patient_insight as pi

    assert get_catalog()["biomarkers"].get("tyg_index") is None
    assert pi._display_vi("tyg_index") == "Chỉ số TyG"
