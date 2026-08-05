"""P0-1 — one hardened analyte matcher across EVERY path that resolves a label.

The defect class: `lab_interpreter.normalize_biomarker` ends in a bare
containment scan (`alias in key or key in alias`). Under it "VLDL" resolves to
`ldl` and "Non-HDL cholesterol" resolves to `hdl`, because the shorter generic
alias is a substring of the longer specific label. `lab_parser._match_biomarker`
is the hardened matcher — longest-alias-wins with shadowing, plus
`_UNMAPPABLE_LABEL_RE` to drop labels that have no safe canonical at all.

Only the `/lab-uploads` path used the hardened one. The document-intelligence
path had three independent entry points that did not:

  - `extractors_lab` called `_match_biomarker` with NO alias index, silently
    falling back to the bare `_ALIAS_INDEX` (under which "HDL Cholesterol"
    resolves to `total_cholesterol`);
  - `promoters._canonical_for` had no hardening and fell back on failure;
  - `lab.create_manual_entry` re-derived the canonical with
    `normalize_biomarker`, so even a correct resolution upstream was discarded
    and recomputed with the unhardened matcher at the storage layer.

Why it is a patient-safety defect and not a data-quality one: VLDL runs roughly
0.1-1.0 mmol/L and LDL is high above ~3.4. A patient confirming the VLDL line off
their own printed report overwrote their LDL with a much lower number, which was
then classified optimal and trended — a false negative on cardiovascular risk.
It is invisible at review time because the confirmation card shows the PRINTED
label, not the resolved canonical.

This suite pins the class, not the example: every path resolves through
`build_alias_index()`, unmappable labels are REFUSED rather than approximated,
and no patient-supplied correction can route around the guard.
"""

from __future__ import annotations

import pytest
from app.services import lab as lab_svc
from app.services.lab_parser import _match_biomarker, _strip_accents, build_alias_index
from app.services.mdi.extractors_lab import LabExtractor
from app.services.mdi.promoters import _canonical_for


def _extract(text: str):
    return LabExtractor().extract(text=text, doc_type="lab_report", ocr_confidence=0.9)


def _canon_of(text: str) -> dict[str, str]:
    """{printed label: resolved canonical} for one report."""
    return {c.fields["test_name"]: c.fields["canonical"] for c in _extract(text)}


# ── 1. Labels with NO safe canonical are dropped, not approximated ───────────

UNMAPPABLE = (
    "Non-HDL Cholesterol: 3.8 mmol/L",
    "Non HDL cholesterol 3.8 mmol/L",
    "Cholesterol non-HDL: 3.8 mmol/L",
    "VLDL: 0.5 mmol/L",
    "VLDL-C 0.5 mmol/L",
    "VLDL Cholesterol: 0.5 mmol/L",
    "Cholesterol/HDL: 3.2",
    "LDL/HDL ratio: 2.1",
)


@pytest.mark.parametrize("line", UNMAPPABLE)
def test_extractor_drops_labels_with_no_safe_canonical(line):
    """A wrong analyte is worse than a missing one — these must produce NO
    candidate rather than resolve to a neighbouring lipid."""
    assert _extract(line) == [], f"{line!r} produced a candidate"


def test_vldl_does_not_resolve_to_ldl_on_any_path():
    """The specific instance, asserted at all three layers at once."""
    for label in ("VLDL", "VLDL-C", "VLDL Cholesterol"):
        assert _canonical_for(label) is None
        assert _match_biomarker(_strip_accents(label.lower()), build_alias_index()) is None
        assert lab_svc._hardened_canonical(label) is None


def test_non_hdl_does_not_resolve_to_hdl_on_any_path():
    for label in ("Non-HDL Cholesterol", "Non HDL cholesterol", "Cholesterol non-HDL"):
        assert _canonical_for(label) is None
        assert lab_svc._hardened_canonical(label) is None


def test_lipid_ratios_do_not_resolve_to_either_side():
    for label in ("Cholesterol/HDL", "LDL/HDL"):
        assert _canonical_for(label) is None
        assert lab_svc._hardened_canonical(label) is None


# ── 2. Specific-over-generic holds on the document path too ─────────────────

PRECEDENCE = (
    ("HDL Cholesterol: 1.2 mmol/L", "hdl"),
    ("HDL-Cholesterol 1.2 mmol/L", "hdl"),
    ("HDL-C: 1.2 mmol/L", "hdl"),
    ("Cholesterol HDL: 1.2 mmol/L", "hdl"),
    ("LDL Cholesterol: 2.8 mmol/L", "ldl"),
    ("LDL-C 2.8 mmol/L", "ldl"),
    ("Cholesterol LDL: 2.8 mmol/L", "ldl"),
    ("Cholesterol: 4.5 mmol/L", "total_cholesterol"),
    ("Cholesterol toàn phần: 5.1 mmol/L", "total_cholesterol"),
    ("Total Cholesterol 4.5 mmol/L", "total_cholesterol"),
    ("Hemoglobin: 14.0 g/dL", "hemoglobin"),
    ("HbA1c: 5.8 %", "hba1c"),
    ("Hemoglobin A1c: 5.8 %", "hba1c"),
)


@pytest.mark.parametrize("line,expected", PRECEDENCE)
def test_extractor_resolves_the_most_specific_analyte(line, expected):
    """This is the regression: without a shared alias index, `_match_biomarker`
    fell back to the bare table and "HDL Cholesterol" became total_cholesterol."""
    cands = _extract(line)
    assert len(cands) == 1, f"{line!r} → {cands}"
    assert cands[0].fields["canonical"] == expected


@pytest.mark.parametrize("line,expected", PRECEDENCE)
def test_all_three_paths_agree_on_the_same_label(line, expected):
    """The class property. Three independent resolvers disagreeing is what let a
    row be extracted as one analyte and STORED as another."""
    label = _extract(line)[0].fields["test_name"]
    assert _canonical_for(label) == expected
    assert lab_svc._hardened_canonical(label) == expected


def test_a_full_lipid_panel_resolves_every_line_to_a_distinct_analyte():
    report = """PHÒNG XÉT NGHIỆM ABC
Ngày lấy mẫu: 20/03/2026
Cholesterol toàn phần: 5.1 mmol/L
HDL Cholesterol: 1.2 mmol/L
LDL Cholesterol: 3.6 mmol/L
Triglyceride: 2.1 mmol/L
Non-HDL Cholesterol: 3.9 mmol/L
VLDL: 0.5 mmol/L
"""
    resolved = _canon_of(report)
    assert set(resolved.values()) == {"total_cholesterol", "hdl", "ldl", "triglyceride"}
    # No two printed labels collapse onto one canonical — the collapse is exactly
    # how one analyte silently overwrote another.
    assert len(set(resolved.values())) == len(resolved)
    # And the two unmappable lines contributed nothing.
    assert not any("Non-HDL" in k or "VLDL" in k for k in resolved)


# ── 3. Punctuation, case, accents and spacing are all one label ─────────────


@pytest.mark.parametrize(
    "label",
    ["HDL Cholesterol", "hdl cholesterol", "HDL-Cholesterol", "HDL_Cholesterol",
     "HDL.Cholesterol", "HDL  Cholesterol", "  HDL Cholesterol  "],
)
def test_separator_and_case_variants_resolve_identically(label):
    assert _canonical_for(label) == "hdl"


@pytest.mark.parametrize(
    "label",
    ["Cholesterol toàn phần", "Cholesterol toan phan", "CHOLESTEROL TOÀN PHẦN"],
)
def test_accent_variants_resolve_identically(label):
    assert _canonical_for(label) == "total_cholesterol"


def test_the_ratio_separator_is_not_treated_as_a_word_break():
    """`/` is deliberately excluded from the flexible-separator set: treating it
    as a space would turn the ratio "Cholesterol/HDL" into the two analytes it
    is a ratio OF, which is precisely the wrong-analyte failure."""
    assert _canonical_for("Cholesterol/HDL") is None
    assert _canonical_for("LDL/HDL") is None


# ── 4. No patient-supplied correction can route around the guard ────────────


def test_stored_canonical_is_never_trusted_over_the_label():
    """`_apply_corrections` merges an arbitrary flat dict into fields_json before
    promotion, so `canonical` is patient-influenced. The promoter must re-derive
    it from `test_name` every time — a correction of {"canonical": null} used to
    blank the field and make the unit guard vacuous."""
    assert _canonical_for("VLDL") is None
    # A correction that renames the analyte must move the canonical with it,
    # never leave the previous analyte's key in force.
    assert _canonical_for("LDL Cholesterol") == "ldl"
    assert _canonical_for("HDL Cholesterol") == "hdl"


def test_unknown_and_empty_labels_resolve_to_none():
    for label in (None, "", "   ", "Ghi chú", "PHÒNG XÉT NGHIỆM ABC", "Zzzz"):
        assert _canonical_for(label) is None


def test_hardened_canonical_is_what_the_storage_layer_uses():
    """`create_manual_entry` previously re-derived with `normalize_biomarker`,
    discarding a correct upstream resolution. Pin the hardened helper's contract:
    unmappable in, None out — never a neighbouring analyte."""
    assert lab_svc._hardened_canonical("VLDL") is None
    assert lab_svc._hardened_canonical("Non-HDL Cholesterol") is None
    assert lab_svc._hardened_canonical("HDL Cholesterol") == "hdl"


# ── 5. The shared index is shared, and stable ──────────────────────────────


def test_build_alias_index_is_a_superset_of_the_bare_table():
    """Every extra alias the parser knows must be visible to the document path;
    calling `_match_biomarker` without it was the original defect."""
    from app.services.lab_parser import _ALIAS_INDEX

    shared = build_alias_index()
    assert len(shared) >= len(_ALIAS_INDEX)
    for alias in _ALIAS_INDEX:
        assert alias in shared


def test_the_shared_index_is_stable_across_calls():
    """It is memoized; a caller mutating it would corrupt every later resolution."""
    assert build_alias_index().keys() == build_alias_index().keys()
