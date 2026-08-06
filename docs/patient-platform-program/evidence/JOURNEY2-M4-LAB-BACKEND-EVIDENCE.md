# Journey 2 — M4 / sub-slice 2b Lab OCR — Backend Evidence

**Milestone:** M4 backend — VN lab-report extractor + lab promoter (BRD §E).
**Branch:** `feat/patient-platform-journey2` (continues from M3 `1aca416`).
**Date:** 2026-07-31
**Governance:** Charter 2/4/6/9. Mobile reuses the existing Journey-2 Add-Document/review UI
(doc-type = lab report); on-artifact DoD is part of the native-runtime session.

A photographed VN lab report now becomes **confirmed canonical LabResults + HealthMetrics**
(trend-visible) via the existing lab pipeline, one analyte at a time.

## Deliverables
- **`extractors_lab.py`** — deterministic VN lab parser (regex + `lab_interpreter.normalize_biomarker`
  to recognize analytes): one report → many `lab_result` candidates with analyte / original value /
  original unit / reference range / specimen date; HbA1c-style embedded-digit names handled;
  comma-decimals; stable numeric-normalized dedupe_key. **Original value/unit preserved verbatim (§E).**
- **`promoters.py::LabPromoter`** — confirmed candidate → `lab.create_manual_entry(commit=False)` →
  canonical `LabResult` (+`HealthMetric` promotion for trends), transaction-atomic; merge path with
  BOLA guard.
- **`lab.create_manual_entry`** — additive optional `commit=True` (commit=False flushes, for atomic promotion).
- **`bootstrap`** registers `LabExtractor` (doc_type=lab_report) + `LabPromoter` (candidate_type=lab_result).

## Independent review (§4) — healthcare-reviewer, verdict BLOCK → resolved
| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| P0 | **Patient safety** | An unknown/garbled/dropped unit on a spec'd analyte passed through `normalize_value_to_si` and was classified against canonical thresholds → silent false-normals / inverted messages | `LabPromoter` now refuses promotion when the unit isn't confidently convertible (`is_unit_convertible`, new) → **422**, patient corrects the unit and re-confirms; no canonical row written meanwhile. Original value/unit still preserved. |
| P1 | Clinical/data-integrity | `_parse_date` fabricated "today" on any unparseable/ISO/ambiguous date → corrupted trend chronology | `_parse_date` returns **None** on failure; the lab pipeline falls back to insert time + sorts undated last |
| P2 | Technical | dedupe_key used raw `str(value)` → reprocess could duplicate | numeric canonicalized (`{round(v,4):g}`) |

Reviewer-confirmed correct: no canonical write before confirmation; at-most-once promotion
(`uq_promotion_candidate_once`); transaction atomicity (commit=False flush + single route commit +
rollback on every error branch); BOLA self-access; HbA1c/comma parsing; no PHI in logs.
Deferred (tracked, non-safety): per-candidate creates its own LabDocument/batch (grouping — fast-follow
to share one batch per source document); VN thousand-separator; MDI OCR-feedback-loop (`ocr_case_id`).

## Test evidence
- **New:** `tests/test_mdi_lab.py` (extractor + is_unit_convertible + _parse_date units) +
  `tests/api/test_lab_ocr_api.py` (lab photo→confirm→real LabResult+HealthMetric; reject writes nothing;
  **unrecognized-unit blocks (422) then correction succeeds**).
- Full backend suite green (see commit); ruff clean.
