# Journey 2 — M7 / sub-slice 2c General-Report OCR — Backend Evidence

**Milestone:** M7 backend — general medical-report extractor + record-only promoter (BRD §F / §1.9).
**Branch:** `feat/patient-platform-journey2` (continues from 2b `fc4f90f`).
**Date:** 2026-07-31

Completes the **document-first core of Journey 2 at the backend level**: all three doc types
(prescription, lab, general report) now go photo → OCR → typed candidates → per-candidate confirm →
correct destination.

## Deliverables
- **`extractors_general.py`** — deterministic VN report parser: section-label heuristic → typed
  candidates (diagnosis / procedure / finding / recommendation / follow_up) + structured summary +
  report date. Multi-label lines split into separate candidates; label-on-own-line reads the content
  below; a **dose-bearing line is re-typed to `medication`** so it routes through the MedicationPromoter
  (reconciliation), never the record-only path (§1.9).
- **`promoters.py::RecordOnlyPromoter`** — for the 5 types with no separate canonical table: confirm
  marks the candidate confirmed + a `PromotionLink` back to the candidate (the confirmed candidate IS
  the record; the unified timeline reads it in Journey 3). A **diagnosis becomes a record only on
  explicit confirmation, never automatically** (§1.9); a **follow_up records intent only** (the reminder
  engine schedules it in Journey 3 — no auto-scheduling). Rejects merge + blank text.
- **`bootstrap`** registers `GeneralReportExtractor` (doc_type=general) + `RecordOnlyPromoter` for the 5 types.

## Independent review (§4) — code-reviewer, verdict WARNING → resolved
| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| P1-1 | High | Same-line multi-label bleed silently dropped a distinct entity (follow_up folded into diagnosis) | `_segments()` splits a line at each label position → separate candidates |
| P1-2 | High | "chỉ định" mis-typed a medication order as `procedure`, bypassing reconciliation | dose/strength `_MED_RE` re-types dose-bearing lines to `medication` (→ MedicationPromoter, statement-first) |
| P1-3 | High | `merge_candidate` hardcoded status="merged"; RecordOnlyPromoter ignored `merge_target_id` | merge sets status from the promoter outcome; RecordOnlyPromoter rejects merge (403) |
| P2-4 | Med | RecordOnlyPromoter allowed blank text | empty-text → PromotionInvalid (422) |
| P2-5 | Med | label-on-own-line under-extracted | one-line lookahead when post-label content is empty |

Reviewer-confirmed correct (P0=0): candidates-only invariant (no canonical Medication/LabResult written
by RecordOnlyPromoter); diagnosis never auto-canonical; no follow_up auto-scheduling; idempotency
(`uq_promotion_candidate_once`) holds for record-only; no ReDoS; no PHI logged; `canonical_id=candidate.id`
self-reference is sound (PromotionLink columns are unconstrained polymorphic strings, candidates never
hard-deleted).

## Test evidence
- **New:** `tests/test_mdi_general.py` (typed candidates, multi-label split, medication re-typing,
  own-line lookahead) + `tests/api/test_general_ocr_api.py` (report→typed candidates→confirm; diagnosis
  writes no canonical med/lab row; follow_up records intent; merge-on-record-only → 403; blank-text → 422).
  Also updated `test_confirm_without_registered_promoter_409` (all types now have promoters → clears the
  registry to test the 409 path).
- Full backend suite green (see commit); ruff clean.

## Journey 2 status after 2c
Document-first backend complete (2a rx + 2b lab + 2c general). **Remaining Journey 2:** on-artifact
Charter-7 DoD for all three (native-runtime session — Android emulator + expo-image-picker dev-client
rebuild) and enabling the `OCR` staging flag after M4 exit. Timeline unification (surfacing confirmed
general-report candidates) is Journey 3.
