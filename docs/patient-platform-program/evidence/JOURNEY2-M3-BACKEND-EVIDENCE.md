# Journey 2 — M3 (sub-slice 2a) Prescription OCR — Backend Evidence

**Milestone:** M3 backend — real VN prescription extractor + medication promoter (BRD §D).
**Branch:** `feat/patient-platform-journey2` (continues from the M2 foundation `f5085cc`).
**Date:** 2026-07-31
**Governance:** Charter 2/4/6/9. Mobile Add-Document UI + on-artifact DoD = the next increment.

Turns the M2 foundation into a working confirm→promote: a photographed VN prescription now
becomes **real canonical `Medication` records** on per-candidate confirmation, statement-first,
with full provenance.

---

## What a patient can now do (Charter 1)

Backend end-to-end: prescription photo → OCR → **many independent medication candidates**
(one card per medicine, with strength/form/quantity/frequency/route/duration + facility/
prescriber/date/diagnosis context) → per-candidate **confirm** → a real `Medication` created via
`MedicationStatement`→canonical (stamped `ocr_confirmed`), or **merge** into an existing
medication → **reject**. No medication is written before confirmation; re-upload/reprocess never
double-promotes.

---

## Deliverables

- **`extractors_prescription.py`** — deterministic VN prescription parser (regex, no LLM/network):
  enumerated + strength-signal medicine detection; per-field extraction; header context; per-field
  confidence; stable `dedupe_key`. Registered for `doc_type=prescription`.
- **`promoters.py::MedicationPromoter`** — confirmed candidate → `medication.add_medication(...,
  source_type="ocr_confirmed", commit=False)` (statement-first, atomic with candidate status +
  `PromotionLink`). Merge path with a **cross-patient BOLA guard** + terminal-state guard.
- **`medication.add_medication`** — additive optional `source_type` (default `patient_manual`;
  backward-compatible) stamping statement + canonical row.
- **`bootstrap.register_defaults()`** — registers the prescription extractor + medication promoter
  at app startup; also invoked by an autouse test fixture so registry state is deterministic.

## Independent review (§4) — findings + resolutions

Fresh-context `ecc:security-reviewer` pass: **P0 none.** All P1 fixed in-slice; P2s addressed.

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| P1-1 | High | Two legit lines (same drug+strength+form, different regimen) silently deduped | dedupe_key now folds in frequency + instructions → distinct candidates |
| P1-2 | High | OCR whitespace jitter → unstable dedupe_key across reprocess | `make_dedupe_key` collapses internal whitespace |
| P1-3 | High | `register_defaults()` at import + per-test registry resets = order-dependent flake | autouse conftest fixture re-registers defaults before/after every test |
| P1-4 | High | `corrections` was an unconstrained dict (amplification/unvalidated) | bounded validator (≤20 flat scalar keys, value length cap, no nesting) → 422 |
| P2-5 | Med | merge target in terminal `entered_in_error` could be resurrected | `_merge` rejects `entered_in_error` targets |
| P2-6 | Med | `PromotionDenied` conflated BOLA (403) with invalid data | split `PromotionInvalid` → 422 for blank-name-after-correction |

Regression tests added for every fix (distinct-regimen candidates, whitespace-stable key,
nested/blanking corrections → 422, terminal-merge → 403).

Deferred (documented): a corroborating `MedicationStatement` on *merge* (P2-7 — currently only
`PromotionLink` records it); an ADR on whether extracted `diagnosis` warrants `EncryptedString`
(P2-8 — consistent with the existing plaintext medication-domain precedent, not a regression).

## Test evidence

- **New:** `tests/test_mdi_prescription.py` (extractor unit) + `tests/api/test_prescription_ocr_api.py`
  (photo→confirm→real `Medication`; reprocess no-double-promote; merge; cross-patient merge 403;
  corrections 422; terminal-merge 403).
- Full suite green (see commit); medication + MDI subset: 460+ passed / 0 failed. `ruff` clean.
