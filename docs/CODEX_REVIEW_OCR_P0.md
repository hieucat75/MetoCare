```
CODEX REVIEW: MetoCare OCR P0 — fix/ocr-p0-cobas-machine-id
Date: 2026-06-26
Reviewer: Codex

VERDICT: APPROVE_WITH_NOTES

P0 ISSUES: NONE
  — The root bug (Cobas C502 → value 502 auto-saved) is fully blocked.
    Suspect rows are excluded at Layer 1→4 boundary before they can reach
    interpret_panel(), LabResult creation, or health_metrics promotion.

P1 ISSUES:
  1. unverified rows promoted to health_metrics
     _promote_row() in lab.py does NOT check verified_by_user before writing
     to health_metrics. All new_rows (including requires_review=True rows) are
     passed to promote_lab_rows_to_metrics() after db.flush(). This means
     rows with LOW confidence (e.g. missing unit, low OCR score) are visible
     in the patient dashboard before explicit user confirmation.
     — NOTE: this does NOT affect the P0 (suspect_machine_id rows are excluded
       entirely from new_rows before they reach here). Impact is limited to
       low-confidence non-suspect rows. Pre-existing pattern; new in this fix
       is that requires_review=True rows are now explicitly constructed, making
       this gap visible. Recommend: add `if not lr.verified_by_user: continue`
       guard before promote_lab_rows_to_metrics, OR pass only verified rows.

  2. _is_instrument_cell() false-positive risk: test-code collision
     _MODEL_SUFFIX_RE = r'[A-Za-z]\s*(\d{3,4})' also matches lab billing codes
     like "B502" or short code strings "Xn502" in the test_name column.
     If a hospital uses test codes like "B502 - ALT" AND the result value is
     literally 502 (e.g. ALT=502 U/L in acute hepatitis), the row will be
     incorrectly flagged suspect_machine_id=True and silently dropped.
     — Impact is LOW in practice (extremely rare coincidence), but represents
       a silent data-loss risk without audit trail to the patient.
       Recommend: add WARNING log clearly stating the test_name that was
       matched (currently only the instrument cell is logged, not test_name).

NOTES:
  A. Vietnamese 'đ' (U+0111) is not NFD-decomposed — pre-existing bug in
     _strip_accents_lower(). The content-scan fallback compensates.
     Tracked separately. Low urgency for this fix.

  B. method_column_headers in HospitalProfile is declared but not yet consumed
     by lab_table_extractor at runtime. Declared for Phase 2 wiring.
     No impact on correctness of current fix.

  C. cortisol alias not found in _ALIAS_INDEX — 1 test skipped. Separate task.

  D. Frontend review UI for verified_by_user=False rows must be verified
     independently. lab.py schema includes verified_by_user in LabResultOut.
     Out of scope for this P0 fix.

ROOT CAUSE FIX: CONFIRMED
  — _detect_column_roles() correctly classifies col 5 ("Phương pháp / Máy")
    as "method" type via keyword match on "phuong phap / may".
  — Safety override: if value_col == method_col, last-resort positional
    fallback reassigns value_col to first non-excluded column.
  — Content-scan fallback: scans data rows for _is_instrument_cell() to
    detect method columns even when header is absent or non-standard.
  — Both primary (header keyword) and secondary (content scan) paths tested.

INSTRUMENT BLOCKLIST: ADEQUATE
  — Covers major Vietnamese hospital analyzers: Roche Cobas, Abbott Architect,
    Sysmex, Beckman Coulter, Siemens, Olympus, Hitachi.
  — Specific model numbers (C502, C702, E601, AU480, AU680) explicitly listed.
  — Generic model suffix pattern [A-Za-z]\d{3,4} catches unlisted models.
  — Gap: 4-digit all-numeric models like "8000" only covered by explicit entry
    "cobas 8000"; other vendors with digit-only models would miss the suffix RE.
    Not a gap for current production case (Medlatec uses C502).

METHOD COLUMN DETECTION: ROBUST
  — Dual-path: header keyword match + content-scan fallback.
  — Content-scan breaks on first hit (sufficient for single method column).
  — Safety override prevents value_col == method_col collision.
  — The one theoretical edge case (3-col table with method at col 1) is
    unrealistic: method column is always rightmost in Vietnamese lab reports.
  — Full test coverage via TestColumnRoleDetection class.

SUSPECT FLAG LOGIC: RISK_OF_FALSE_POSITIVE (minor, low probability)
  — Correct for the target scenario: bare integer 100–9999 with instrument
    cell in same row where model suffix matches the integer.
  — Risk: hospital test codes like "B502 - ALT" in test_name col + real value
    of 502 would trigger false positive → row silently dropped.
  — Mitigation: the test_name is NOT the value_col so it is scanned by the
    instrument check. For this to be a real problem, both conditions must
    coincide: (a) hospital uses 3-4 digit letter+number test codes, AND
    (b) that specific test has a result that is the same integer as the code.
    Probability is very low in current Vietnamese hospital data.

AUTO-SAVE GATE: EFFECTIVE
  — verified_by_user=not auto_save_blocked correctly applied at LabResult
    creation for all flagged rows.
  — suspect_machine_id rows are excluded entirely upstream (never reach
    LabResult), making the gate defence-in-depth for non-suspect rows.
  — Gap: _promote_row() does not check verified_by_user (P1 above).

UNIT PRESERVATION: CONFIRMED
  — original_unit and original_value always set from row data before any
    SI conversion in map_table_rows_to_raw_values().
  — Conversion result stored in value/unit; original never overwritten.
  — TestMmolNotConvertedSilently confirms mmol/L preserved for Medlatec data.
  — Live pipeline test: fasting_glucose original_value=5.73, original_unit=mmol/L
    correctly preserved; converted value=103.243 mg/dL separate field.

GOLDEN FIXTURE: PRESENT — 10/11 tests
  — 11 parametrized tests via @pytest.mark.parametrize on MEDLATEC_EXPECTED.
  — cortisol (1/11): SKIPPED — alias not in _ALIAS_INDEX. Not a P0 issue.
    Cortisol 2.50 nmol/L would need separate alias/catalog entry.
  — 10/11 biomarkers confirmed correct value + original_unit match.
  — No value==502 in any output row confirmed by test_no_value_502_in_output.

REGRESSION TESTS: PRESENT — 7/7 tests
  1. ✓ test_cobas_c502_never_result (TestCobasC502NeverResult)
  2. ✓ test_price_column_never_result (TestPriceColumnNeverResult)
  3. ✓ test_reference_range_never_result (TestReferenceRangeNeverResult)
  4. ✓ test_instrument_blocklist (TestInstrumentBlocklist)
  5. ✓ test_mmol_not_converted_silently (TestMmolNotConvertedSilently)
  6. ✓ test_row_with_missing_unit_flagged (TestRowWithMissingUnitFlagged)
  7. ✓ test_suspect_machine_id_blocked (TestSuspectMachineIdBlocked)

TEST RESULTS: 174 passed / 1 skipped (cortisol alias, expected)
  — backend/tests/test_lab_table_extractor.py: 58 passed, 1 skipped
  — backend/tests/test_lab_ocr.py: 116 passed
  — Zero failures. Zero regressions on pre-existing test suite.

RECOMMENDATION:
  MERGE APPROVED with two follow-up tickets before next sprint:

  FU-1 [P1, blocking for GA]: Fix promote_lab_rows_to_metrics() to skip rows
  where verified_by_user=False (or add filter in lab_pipeline.py before calling
  promote). Prevents unverified/low-confidence values appearing in patient
  dashboard before user confirmation. Suggested patch (lab_pipeline.py line 181):
    promote_lab_rows_to_metrics(db, patient_id=doc.patient_id,
        rows=[r for r in new_rows if r.verified_by_user], test_date=None)

  FU-2 [P2]: Add test_name to the WARNING log in extract_table_rows() when
  suspect_machine_id fires, so audit trail shows which test name triggered the
  model-suffix match. Aids debugging if false-positive occurs in production.

  NON-BLOCKING observations:
  - Fix _strip_accents_lower() for 'đ'/'Đ' (tracked separately)
  - Wire HospitalProfile.method_column_headers at runtime (Phase 2)
  - Add cortisol alias to catalog
  - Verify frontend "Needs Confirmation" UI for verified_by_user=False rows
```
