"""P1-1 — record HOW a lab label resolved, not only what it resolved to.

A stored `LabResult` names a canonical analyte. Nothing recorded which of the
dozens of aliases bridged the printed label to that canonical, or which alias
layer supplied it. So the question P0-1 raised — "this row says `ldl`, the report
said VLDL, how did that happen?" — could not be answered from the data at all.
The investigation had to be run against the code as it exists *now*, which is
exactly the code that has since changed.

`resolve_with_provenance` records the original label, the canonical key, the
winning alias, the alias layer, the hospital profile in play, and the reason a
label produced nothing. It is captured twice, deliberately:

  - at EXTRACTION, describing the label the OCR read;
  - at PROMOTION, re-derived, describing the label AS CONFIRMED.

Those differ whenever the patient corrects the analyte name, and recording only
the first would attribute the stored analyte to an alias that never fired for it
— worse than recording nothing, because it reads as authoritative.

Both live inside `fields_json`, which SEC-F11 already encrypts, so provenance
travels with the candidate without opening a second PHI surface.
"""

from __future__ import annotations

import pytest
from app.services.lab_parser import resolve_with_provenance
from app.services.mdi.extractors_lab import LabExtractor
from app.services.mdi.promoters import _provenance_for


def _extract(text: str):
    return LabExtractor().extract(text=text, doc_type="lab_report", ocr_confidence=0.91)


# ── 1. A successful resolution is fully described ───────────────────────────


def test_a_match_records_every_field_needed_to_audit_it():
    p = resolve_with_provenance("HDL Cholesterol")

    assert p["original_label"] == "HDL Cholesterol"
    assert p["canonical"] == "hdl"
    assert p["matched_alias"], "the winning alias is the whole point"
    assert "hdl" in p["matched_alias"].lower()
    assert p["alias_source"] in ("base", "parser_extra", "profile")
    assert p["matcher"] == "hardened"
    assert p["reason"] == "matched"


def test_the_original_label_is_preserved_verbatim():
    """Accents and case must survive: the audit question is what the REPORT said,
    not what the normalizer made of it."""
    p = resolve_with_provenance("  Cholesterol toàn phần  ")
    assert p["original_label"] == "Cholesterol toàn phần"
    assert p["canonical"] == "total_cholesterol"


def test_the_alias_layer_is_reported_accurately():
    """Three layers merge into the index: the shared table, the parser's extra
    aliases, and hospital-profile aliases. Collapsing them to base-or-profile
    mislabels every parser-extra alias as profile-contributed, which sends an
    investigator to the wrong lab's configuration."""
    assert resolve_with_provenance("Cholesterol toàn phần")["alias_source"] == "base"
    assert resolve_with_provenance("HDL Cholesterol")["alias_source"] == "parser_extra"


def test_no_hospital_profile_is_reported_as_none_not_omitted():
    p = resolve_with_provenance("HbA1c")
    assert "hospital_profile" in p
    assert p["hospital_profile"] is None


# ── 2. A non-resolution says WHY ────────────────────────────────────────────


@pytest.mark.parametrize("label", ["VLDL", "Non-HDL Cholesterol", "Cholesterol/HDL"])
def test_a_deliberate_refusal_is_distinguishable_from_a_lookup_miss(label):
    """"We refused this label" and "we did not recognise this label" are different
    findings: the first is the safety rule working, the second is a coverage gap."""
    p = resolve_with_provenance(label)
    assert p["canonical"] is None
    assert p["reason"] == "unmappable_label"


def test_an_unrecognised_label_reports_a_lookup_miss():
    p = resolve_with_provenance("Zzzz Quux")
    assert p["canonical"] is None
    assert p["reason"] == "no_alias_matched"


@pytest.mark.parametrize("label", [None, "", "   "])
def test_an_empty_label_is_its_own_reason(label):
    p = resolve_with_provenance(label)
    assert p["canonical"] is None
    assert p["reason"] == "empty_label"


@pytest.mark.parametrize("weird", ["%%%", "1234", "—", "a" * 5000, "\n\t"])
def test_resolution_never_raises(weird):
    """Provenance is diagnostics; it must not be able to break extraction."""
    result = resolve_with_provenance(weird)
    assert "reason" in result
    assert "canonical" in result


# ── 3. The extractor attaches it ────────────────────────────────────────────


def test_extracted_candidates_carry_provenance():
    cand = _extract("HDL Cholesterol: 1.2 mmol/L")[0]
    p = cand.fields["resolution_provenance"]

    assert p["canonical"] == cand.fields["canonical"] == "hdl"
    assert p["original_label"] == cand.fields["test_name"]
    assert p["matched_alias"]
    assert p["ocr_confidence"] == 0.91


def test_provenance_canonical_always_agrees_with_the_stored_canonical():
    """If these two ever disagree, the audit trail describes a different row than
    the one stored — the failure mode provenance exists to prevent."""
    for cand in _extract(
        "Cholesterol toàn phần: 5.1 mmol/L\n"
        "HDL Cholesterol: 1.2 mmol/L\n"
        "LDL Cholesterol: 3.6 mmol/L\n"
        "HbA1c: 6.8 %\n"
    ):
        assert cand.fields["resolution_provenance"]["canonical"] == cand.fields["canonical"]


# ── 4. Promotion re-derives it from the CONFIRMED label ─────────────────────


def test_promotion_provenance_follows_a_corrected_label():
    """`_apply_corrections` can change test_name before promotion. Reusing the
    extractor's entry would attribute the stored analyte to an alias that never
    fired for it — authoritative-looking and wrong."""
    extracted = _extract("LDL Cholesterol: 3.6 mmol/L")[0]
    assert extracted.fields["resolution_provenance"]["canonical"] == "ldl"

    # The patient corrects the analyte name at review.
    corrected = _provenance_for("HDL Cholesterol")
    assert corrected["canonical"] == "hdl"
    assert corrected["original_label"] == "HDL Cholesterol"
    assert corrected["reason"] == "matched"


def test_promotion_provenance_records_a_refusal_too():
    p = _provenance_for("VLDL")
    assert p["canonical"] is None
    assert p["reason"] == "unmappable_label"
